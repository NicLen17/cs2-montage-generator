"""Motor de imagen en la GPU (OpenGL 4.3 vía ModernGL): AMD, NVIDIA e Intel, Windows y Linux.

render.py tiene una sola copia de la lógica del edit (qué efecto, cuánto, cuándo). Con WAKO_DEVICE=gpu reemplaza sus
operaciones de imagen por las de este módulo: el cuadro sube una vez a la VRAM, todos los efectos corren ahí como shaders
y baja terminado en 8 bits. Las cuentas imitan a OpenCV (curva de color, HSV de 8 bits, desenfoques gaussianos con sus
mismos tamaños de kernel, warpAffine cúbico con coordenadas de 1/32 de píxel, bordes reflejados) para que el resultado
sea el mismo que en CPU (se compara con PSNR, ver references/motor.md).

G es una imagen en la GPU (textura RGBA float32, canales en orden BGR como en OpenCV) que se usa como un array de numpy:
G + G, G * 0.5, 255 - G, G * np.array([b, g, r]), máscara (1 canal) * G. Cada operación es una pasada de shader.
"""
import math
import numpy as np
import cv2
import moderngl

ctx = None
W = H = 0
_pool, _fbos, _progs, _vaos, _sprites = {}, {}, {}, {}, {}
_u8 = None
_upl = {}
_dummy = None

VS = """#version 430
void main(){ vec2 p = vec2((gl_VertexID << 1) & 2, gl_VertexID & 2); gl_Position = vec4(p * 2.0 - 1.0, 0.0, 1.0); }"""
HEAD = """#version 430
out vec4 o;
ivec2 P(){ return ivec2(gl_FragCoord.xy); }
int r101(int i, int n){ if (n == 1) return 0; int p = 2 * n - 2; i = ((i % p) + p) % p; return i >= n ? p - i : i; }
int r1(int i, int n){ int p = 2 * n; i = ((i % p) + p) % p; return i >= n ? p - 1 - i : i; }
"""
SRC = {
    # a (op) b, con a y b textura de 3 canales (m=0), máscara de 1 canal (m=1) o constante (m=2)
    'bin': """
uniform sampler2D A; uniform sampler2D B; uniform int am; uniform int bm; uniform vec3 ac; uniform vec3 bc;
uniform int op; uniform vec2 k;
vec3 g(sampler2D t, int m, vec3 c, ivec2 p){ if (m == 0) return texelFetch(t, p, 0).rgb; if (m == 1) return texelFetch(t, p, 0).rrr; return c; }
void main(){ ivec2 p = P(); vec3 a = g(A, am, ac, p), b = g(B, bm, bc, p), r;
  if (op == 0) r = a + b; else if (op == 1) r = a - b; else if (op == 2) r = a * b; else if (op == 3) r = a / b;
  else r = clamp(roundEven(a * k.x + b * k.y), 0.0, 255.0);      // addWeighted en 8 bits
  o = vec4(r, 0.0); }""",
    'un': """
uniform sampler2D A; uniform int am; uniform int op; uniform vec2 k;
void main(){ vec3 a = am == 1 ? texelFetch(A, P(), 0).rrr : texelFetch(A, P(), 0).rgb; vec3 r;
  if (op == 0) r = clamp(a, k.x, k.y);
  else if (op == 1) r = vec3((a.r + a.g + a.b) / 3.0);
  else if (op == 2) r = vec3(max(max(a.r, a.g), a.b));
  else r = floor(clamp(a, 0.0, 255.0)) / 255.0;                    // astype(uint8) después de clip
  o = vec4(r, 0.0); }""",
    # curva (LUT) + saturación x1.15 en HSV de 8 bits, igual que cv2.LUT + cvtColor + convertScaleAbs
    'grade': """
uniform sampler2D U; uniform sampler2D Yt; uniform sampler2D UVt; uniform int nv12;
uniform sampler2D L; uniform int sdiv[256]; uniform int hdiv[256]; uniform float sat;
ivec3 src(){ ivec2 p = P();
  if (nv12 == 0) return ivec3(roundEven(texelFetch(U, p, 0).rgb * 255.0));
  // YUV 4:2:0 -> BGR como swscale (lo que usa OpenCV): BT.601 rango limitado, croma del vecino, punto fijo
  int Y = int(roundEven(texelFetch(Yt, p, 0).r * 255.0)); vec2 uv = texelFetch(UVt, p / 2, 0).rg;
  int u8 = int(roundEven(uv.x * 255.0)) * 8 - 1024, v8 = int(roundEven(uv.y * 255.0)) * 8 - 1024;
  int yv = ((Y * 8 - 128) * 9539) >> 16;
  return clamp(ivec3(yv + ((u8 * 16525) >> 16), yv + ((u8 * -3209) >> 16) + ((v8 * -6660) >> 16), yv + ((v8 * 13074) >> 16)), 0, 255); }
void main(){ ivec3 c = src();
  int b = int(roundEven(texelFetch(L, ivec2(c.x, 0), 0).r)), g = int(roundEven(texelFetch(L, ivec2(c.y, 0), 0).g)),
      r = int(roundEven(texelFetch(L, ivec2(c.z, 0), 0).b));
  int v = max(b, max(g, r)), vmin = min(b, min(g, r)), diff = v - vmin;
  int vr = v == r ? -1 : 0, vg = v == g ? -1 : 0;
  int s = (diff * sdiv[v] + (1 << 11)) >> 12;
  int h = (vr & (g - b)) + (~vr & ((vg & (b - r + 2 * diff)) + ((~vg) & (r - g + 4 * diff))));
  h = (h * hdiv[diff] + (1 << 11)) >> 12; h += h < 0 ? 180 : 0;
  s = int(clamp(roundEven(float(s) * sat), 0.0, 255.0));
  float S = float(s) * (1.0 / 255.0), V = float(v) * (1.0 / 255.0), fb, fg, fr;
  if (s == 0) { fb = fg = fr = V; }
  else { float hh = float(h) * (6.0 / 180.0); if (hh >= 6.0) hh -= 6.0; int sec = int(floor(hh)); hh -= float(sec);
    float t0 = V, t1 = V * (1.0 - S), t2 = V * (1.0 - S * hh), t3 = V * (1.0 - S * (1.0 - hh));
    float tab[4] = float[4](t0, t1, t2, t3);
    ivec3 sd[6] = ivec3[6](ivec3(1,3,0), ivec3(1,0,2), ivec3(3,0,1), ivec3(0,2,1), ivec3(0,1,3), ivec3(2,1,0));
    fb = tab[sd[sec].x]; fg = tab[sd[sec].y]; fr = tab[sd[sec].z]; }
  o = vec4(clamp(roundEven(vec3(fb, fg, fr) * 255.0), 0.0, 255.0), 0.0); }""",
    # filtro separable (gaussiano o caja) con los bordes de OpenCV
    'sep': """
uniform sampler2D A; uniform int horiz; uniform int n; uniform int anchor; uniform int border; uniform int round8;
uniform float w[256];
void main(){ ivec2 p = P(); ivec2 sz = textureSize(A, 0); vec3 s = vec3(0.0);
  for (int i = 0; i < n; i++) {
    int q = (horiz == 1 ? p.x : p.y) - anchor + i; int N = horiz == 1 ? sz.x : sz.y;
    q = border == 0 ? r101(q, N) : r1(q, N);
    s += w[i] * texelFetch(A, horiz == 1 ? ivec2(q, p.y) : ivec2(p.x, q), 0).rgb; }
  if (round8 == 1) s = clamp(roundEven(s), 0.0, 255.0);
  o = vec4(s, 0.0); }""",
    'area': """
uniform sampler2D A; uniform int f;
void main(){ ivec2 p = P() * f; vec3 s = vec3(0.0);
  for (int j = 0; j < f; j++) for (int i = 0; i < f; i++) s += texelFetch(A, p + ivec2(i, j), 0).rgb;
  o = vec4(s / float(f * f), 0.0); }""",
    # resize INTER_LINEAR de OpenCV; opcional: base + k * resize
    'lin': """
uniform sampler2D A; uniform sampler2D Bt; uniform vec2 sc; uniform int hasb; uniform float k;
void main(){ ivec2 p = P(); ivec2 sz = textureSize(A, 0);
  float fx = (float(p.x) + 0.5) * sc.x - 0.5, fy = (float(p.y) + 0.5) * sc.y - 0.5;
  int x = int(floor(fx)), y = int(floor(fy)); fx -= float(x); fy -= float(y);
  if (x < 0) { x = 0; fx = 0.0; } if (x >= sz.x - 1) { x = sz.x - 1; fx = 0.0; }
  if (y < 0) { y = 0; fy = 0.0; } if (y >= sz.y - 1) { y = sz.y - 1; fy = 0.0; }
  int x1 = min(x + 1, sz.x - 1), y1 = min(y + 1, sz.y - 1);
  vec3 r = (texelFetch(A, ivec2(x, y), 0).rgb * (1.0 - fx) + texelFetch(A, ivec2(x1, y), 0).rgb * fx) * (1.0 - fy)
         + (texelFetch(A, ivec2(x, y1), 0).rgb * (1.0 - fx) + texelFetch(A, ivec2(x1, y1), 0).rgb * fx) * fy;
  vec3 b = hasb == 1 ? texelFetch(Bt, p, 0).rgb : vec3(0.0);
  o = vec4(b + k * r, 0.0); }""",
    # warpAffine (mapa inverso), coordenadas cuantizadas a 1/32 de píxel, borde BORDER_REFLECT
    'warp': """
uniform sampler2D A; uniform vec3 m0; uniform vec3 m1; uniform int cubic; uniform int zero;
vec3 F(int x, int y, ivec2 sz){
  if (zero == 1 && (x < 0 || y < 0 || x >= sz.x || y >= sz.y)) return vec3(0.0);      // BORDER_CONSTANT 0
  return texelFetch(A, ivec2(r1(x, sz.x), r1(y, sz.y)), 0).rgb; }
vec4 cw(float x){ const float A_ = -0.75;
  float c0 = ((A_ * (x + 1.0) - 5.0 * A_) * (x + 1.0) + 8.0 * A_) * (x + 1.0) - 4.0 * A_;
  float c1 = ((A_ + 2.0) * x - (A_ + 3.0)) * x * x + 1.0;
  float c2 = ((A_ + 2.0) * (1.0 - x) - (A_ + 3.0)) * (1.0 - x) * (1.0 - x) + 1.0;
  return vec4(c0, c1, c2, 1.0 - c0 - c1 - c2); }
void main(){ ivec2 p = P(); ivec2 sz = textureSize(A, 0); vec2 q = vec2(p);
  float sx = m0.x * q.x + m0.y * q.y + m0.z, sy = m1.x * q.x + m1.y * q.y + m1.z;
  int X = int(floor(sx * 32.0 + 0.5)), Y = int(floor(sy * 32.0 + 0.5));
  int ix = X >> 5, iy = Y >> 5; float fx = float(X & 31) / 32.0, fy = float(Y & 31) / 32.0; vec3 r = vec3(0.0);
  if (cubic == 1) { vec4 cx = cw(fx), cy = cw(fy);
    for (int j = 0; j < 4; j++) { vec3 row = vec3(0.0);
      for (int i = 0; i < 4; i++) row += cx[i] * F(ix - 1 + i, iy - 1 + j, sz);
      r += cy[j] * row; } }
  else r = (F(ix, iy, sz) * (1.0 - fx) + F(ix + 1, iy, sz) * fx) * (1.0 - fy) + (F(ix, iy + 1, sz) * (1.0 - fx) + F(ix + 1, iy + 1, sz) * fx) * fy;
  o = vec4(r, 0.0); }""",
    # separación RGB: canal 0 desde x+px, canal 2 desde x-px (warpAffine lineal por canal)
    'split': """
uniform sampler2D A; uniform float px;
float ch(int c, float sx, int y, ivec2 sz){ int X = int(floor(sx * 32.0 + 0.5)); int ix = X >> 5; float fx = float(X & 31) / 32.0;
  return texelFetch(A, ivec2(r1(ix, sz.x), y), 0)[c] * (1.0 - fx) + texelFetch(A, ivec2(r1(ix + 1, sz.x), y), 0)[c] * fx; }
void main(){ ivec2 p = P(); ivec2 sz = textureSize(A, 0);
  o = vec4(ch(0, float(p.x) + px, p.y, sz), texelFetch(A, p, 0).g, ch(2, float(p.x) - px, p.y, sz), 0.0); }""",
    'leak': """
uniform sampler2D Bt; uniform int hasb; uniform float lx; uniform float inten; uniform vec3 col; uniform vec2 wh;
void main(){ vec2 q = vec2(P()); float dx = (q.x - lx * wh.x) / (wh.x * 0.45), dy = (q.y - wh.y * 0.45) / (wh.y * 0.9);
  float d2 = dx * dx + dy * dy; vec3 b = hasb == 1 ? texelFetch(Bt, P(), 0).rgb : vec3(0.0);
  o = vec4(b + exp(-d2 * 2.2) * inten * col, 0.0); }""",
    'ring': """
uniform sampler2D A; uniform float rad; uniform float th; uniform float amp; uniform vec3 col; uniform vec2 wh;
void main(){ vec2 q = vec2(P()) - wh * 0.5; float d = sqrt(dot(q, q)); float e = (d - rad) / th;
  float a = exp(-e * e) * amp; o = vec4(texelFetch(A, P(), 0).rgb * (1.0 - a) + col * a, 0.0); }""",
    # sprite (texto, logo) sobre una región; mode 0: suma col*a*al, 1: oscurece, 2: pega imagen con máscara
    'sprite': """
uniform sampler2D S; uniform sampler2D M; uniform ivec2 org; uniform vec2 inv; uniform vec2 minv;
uniform int mode; uniform vec3 col; uniform float al;
vec3 bl(sampler2D t, vec2 iv, ivec2 j){ ivec2 sz = textureSize(t, 0);
  float fx = (float(j.x) + 0.5) * iv.x - 0.5, fy = (float(j.y) + 0.5) * iv.y - 0.5;
  int x = int(floor(fx)), y = int(floor(fy)); fx -= float(x); fy -= float(y);
  if (x < 0) { x = 0; fx = 0.0; } if (x >= sz.x - 1) { x = sz.x - 1; fx = 0.0; }
  if (y < 0) { y = 0; fy = 0.0; } if (y >= sz.y - 1) { y = sz.y - 1; fy = 0.0; }
  int x1 = min(x + 1, sz.x - 1), y1 = min(y + 1, sz.y - 1);
  return (texelFetch(t, ivec2(x, y), 0).rgb * (1.0 - fx) + texelFetch(t, ivec2(x1, y), 0).rgb * fx) * (1.0 - fy)
       + (texelFetch(t, ivec2(x, y1), 0).rgb * (1.0 - fx) + texelFetch(t, ivec2(x1, y1), 0).rgb * fx) * fy; }
void main(){ ivec2 j = P() - org;
  if (mode == 0) { float a = bl(S, inv, j).r; o = vec4(col * a * al, 0.0); }
  else if (mode == 1) { float a = bl(S, inv, j).r; o = vec4(0.0, 0.0, 0.0, clamp(a * 1.6, 0.0, 1.0) * al); }
  else { vec3 img = bl(S, inv, j); float m = bl(M, minv, j).r; o = vec4(img * al, m * al); } }""",
    'logo_ring': """
uniform sampler2D Bt; uniform vec2 c; uniform float lr; uniform float sweep; uniform float t; uniform float gk;
uniform vec3 c1; uniform vec3 c2; uniform vec3 c3;
void main(){ vec2 q = vec2(P()) - c; float ang = atan(q.y, q.x), dl = sqrt(dot(q, q));
  float e1 = (dl - (lr + 14.0)) / 7.0, e2 = (dl - (lr + 14.0)) / 38.0;
  float rel = mod(ang + 1.5707963267948966, 6.283185307179586); float on = rel <= sweep ? 1.0 : 0.0;
  float u = sin(ang + t * 1.6) * 0.5 + 0.5;
  vec3 col = u < 0.5 ? c1 + (c2 - c1) * (u * 2.0) : c2 + (c3 - c2) * ((u - 0.5) * 2.0);
  o = vec4(texelFetch(Bt, P(), 0).rgb + exp(-e1 * e1) * on * col + exp(-e2 * e2) * on * col * gk, 0.0); }""",
    # círculo suavizado (cv2.circle LINE_AA, relleno) pintado encima con su cobertura
    'nv12y': """
uniform sampler2D A;
void main(){ vec3 c = floor(clamp(texelFetch(A, P(), 0).rgb, 0.0, 255.0));
  o = vec4(clamp(roundEven(16.0 + (24.966 * c.x + 128.553 * c.y + 65.481 * c.z) / 255.0), 0.0, 255.0) / 255.0, 0.0, 0.0, 0.0); }""",
    'nv12uv': """
uniform sampler2D A;
void main(){ ivec2 p = P() * 2; vec3 c = vec3(0.0);
  for (int j = 0; j < 2; j++) for (int i = 0; i < 2; i++) c += floor(clamp(texelFetch(A, p + ivec2(i, j), 0).rgb, 0.0, 255.0));
  c *= 0.25;
  float u = 128.0 + (112.0 * c.x - 74.203 * c.y - 37.797 * c.z) / 255.0, v = 128.0 + (-18.214 * c.x - 93.786 * c.y + 112.0 * c.z) / 255.0;
  o = vec4(clamp(roundEven(vec2(u, v)), 0.0, 255.0) / 255.0, 0.0, 0.0); }""",
    'circle': """
uniform vec2 c; uniform float r; uniform vec3 col;
void main(){ vec2 q = vec2(P()) - c; float cov = clamp(r + 0.5 - sqrt(dot(q, q)), 0.0, 1.0); o = vec4(col, cov); }""",
}


# ---------------------------------------------------------------- base
def init(w, h):
    """Crea el contexto OpenGL sin ventana. Falla (RuntimeError) si no hay GPU con OpenGL 4.3.
    En Linux sin pantalla (servidor, contenedor, sesión por SSH) el contexto por X11 no existe: se prueba EGL."""
    global ctx, W, H, _u8, _dummy
    try:
        ctx = moderngl.create_standalone_context(require=430)
    except Exception as e:
        import sys
        if not sys.platform.startswith('linux'):
            raise
        try:
            ctx = moderngl.create_standalone_context(require=430, backend='egl')
        except Exception as e2:
            raise RuntimeError(f'sin contexto OpenGL 4.3 (X11: {e}; EGL: {e2})') from e2
    W, H = w, h
    for k, s in SRC.items():
        _progs[k] = ctx.program(vertex_shader=VS, fragment_shader=HEAD + s)
        _vaos[k] = ctx.vertex_array(_progs[k], [])
    _u8 = ctx.texture((W, H), 4, dtype='f1')
    _dummy = ctx.texture((1, 1), 4, dtype='f4')
    return ctx.info['GL_RENDERER']


def _tex(w, h):
    lst = _pool.get((w, h))
    if lst:
        return lst.pop()
    t = ctx.texture((w, h), 4, dtype='f4')
    t.filter = (moderngl.NEAREST, moderngl.NEAREST)
    return t


def _fbo(t):
    f = _fbos.get(t.glo)
    if f is None:
        f = _fbos[t.glo] = ctx.framebuffer([t])
    return f


def _set(p, **kw):
    for k, v in kw.items():
        if k in p:
            p[k].value = v


def _run(prog, size, tex=(), out=None, blend=None, scissor=None, **uni):
    """Una pasada de shader sobre toda la imagen (o la región scissor) de 'out' (nueva si no se da)."""
    dst = out if out is not None else _tex(*size)
    fbo = _fbo(dst)
    fbo.use()
    fbo.scissor = scissor
    p = _progs[prog]
    for i, (name, t) in enumerate(tex):
        (t if t is not None else _dummy).use(i)
        if name in p:
            p[name].value = i
    _set(p, **uni)
    if blend:
        ctx.enable(moderngl.BLEND)
        ctx.blend_func = blend
    _vaos[prog].render(moderngl.TRIANGLES, vertices=3)
    if blend:
        ctx.disable(moderngl.BLEND)
    fbo.scissor = None
    return dst


class G:
    """Imagen en la GPU que se usa como un array de numpy (ver el docstring del módulo)."""
    __array_ufunc__ = None          # numpy deja que G resuelva  np.float64 * G,  np.array(...) * G
    __slots__ = ('t', 'ch')

    def __init__(self, t, ch=3):
        self.t, self.ch = t, ch

    def __del__(self):
        try:
            _pool.setdefault(self.t.size, []).append(self.t)
        except Exception:
            pass

    @property
    def shape(self):
        return (self.t.size[1], self.t.size[0], self.ch)

    def __add__(s, o): return _bin(s, o, 0)
    def __radd__(s, o): return _bin(o, s, 0)
    def __sub__(s, o): return _bin(s, o, 1)
    def __rsub__(s, o): return _bin(o, s, 1)
    def __mul__(s, o): return _bin(s, o, 2)
    def __rmul__(s, o): return _bin(o, s, 2)
    def __truediv__(s, o): return _bin(s, o, 3)
    def __rtruediv__(s, o): return _bin(o, s, 3)
    def __neg__(s): return _bin(-1.0, s, 2)


def _operand(x):
    if isinstance(x, G):
        return (0 if x.ch == 3 else 1), x.t, (0.0, 0.0, 0.0), x.ch
    v = np.asarray(x, np.float64).reshape(-1)
    if v.size == 1:
        return 2, None, (float(v[0]),) * 3, 0
    return 2, None, tuple(float(c) for c in v[:3]), 3


def _bin(a, b, op, k=(0.0, 0.0)):
    am, at, ac, ach = _operand(a)
    bm, bt, bc, bch = _operand(b)
    ref = at or bt
    return G(_run('bin', ref.size, (('A', at), ('B', bt)), am=am, bm=bm, ac=ac, bc=bc, op=op, k=k),
             3 if 3 in (ach, bch) else 1)


def _un(a, op, k=(0.0, 0.0)):
    return _run('un', a.t.size, (('A', a.t),), am=0 if a.ch == 3 else 1, op=op, k=k)


# ---------------------------------------------------------------- ayudas que render.py usa en los dos modos
def zeros():
    t = _tex(W, H)
    f = _fbo(t)
    f.use()
    f.clear(0.0, 0.0, 0.0, 0.0)
    return G(t)


def clip(f, lo, hi):
    if not isinstance(f, G):
        return np.clip(f, lo, hi)
    return G(_un(f, 0, (float(lo), float(hi) if hi is not None else 3.0e38)), f.ch)


def chmean(f):
    return G(_un(f, 1), 1)


def chmax(f):
    return G(_un(f, 2), 1)


def center_mean(f):
    """Brillo medio del centro del cuadro (mismas muestras que f[h/4:3h/4:6, w/4:3w/4:6].mean())."""
    fb = _fbo(f.t)
    a = np.frombuffer(fb.read(viewport=(W // 4, H // 4, W // 2, H // 2), components=4, dtype='f4'), np.float32)
    a = a.reshape(H // 2, W // 2, 4)[::6, ::6, :3]
    return float(a.mean())


def to_u8(f):
    """Cuadro terminado: clip a 0-255, trunca como astype(uint8) y baja de la GPU (BGR)."""
    _run('un', (W, H), (('A', f.t),), out=_u8, am=0, op=3)
    b = _fbo(_u8).read(components=3, dtype='f1', alignment=1)
    return np.frombuffer(b, np.uint8).reshape(H, W, 3)


class NV12:
    """Cuadro tal como sale del decodificador de la placa (Y de w*h bytes + UV intercalado de w*h/2)."""
    __slots__ = ('b', 'w', 'h')

    def __init__(self, b, w, h):
        self.b, self.w, self.h = b, w, h


def _utex(key, w, h, comps):
    t = _upl.get(key)
    if t is None:
        t = _upl[key] = ctx.texture((w, h), comps, dtype='f1', alignment=1)
    return t


def upload(f):
    """Sube un cuadro del lector de clips: NV12 (modo GPU) o uint8 BGR. Devuelve los uniformes para 'grade'."""
    if isinstance(f, NV12):
        w, h = f.w, f.h
        ty, tuv = _utex(('y', w, h), w, h, 1), _utex(('uv', w, h), w // 2, h // 2, 2)
        mv = memoryview(f.b)
        ty.write(mv[:w * h])
        tuv.write(mv[w * h:])
        return (('U', None), ('Yt', ty), ('UVt', tuv)), 1
    h, w = f.shape[:2]
    t = _utex(('bgr', w, h), w, h, 3)
    t.write(np.ascontiguousarray(f))
    return (('U', t), ('Yt', None), ('UVt', None)), 0


_ny = _nuv = None


def to_nv12(f):
    """Cuadro terminado en NV12 para el codificador (clip y truncado a 8 bits como en CPU, BT.601 rango limitado,
    croma promedio de 2x2): el codificador de la placa lo toma directo y ffmpeg no convierte nada en la CPU."""
    global _ny, _nuv
    w, h = f.t.size
    if _ny is None or _ny.size != (w, h):
        _ny = ctx.texture((w, h), 1, dtype='f1')
        _nuv = ctx.texture((w // 2, h // 2), 2, dtype='f1')
    _run('nv12y', (w, h), (('A', f.t),), out=_ny)
    _run('nv12uv', (w // 2, h // 2), (('A', f.t),), out=_nuv)
    return _fbo(_ny).read(components=1, dtype='f1', alignment=1) + _fbo(_nuv).read(components=2, dtype='f1', alignment=1)


def area2(f):
    return G(_run('area', (f.t.size[0] // 2, f.t.size[1] // 2), (('A', f.t),), f=2), f.ch)


def sprite_tex(a):
    """Textura (cacheada) de una máscara de texto o imagen de numpy."""
    key = id(a)
    t = _sprites.get(key)
    if t is None:
        arr = np.ascontiguousarray(a, np.float32)
        if arr.ndim == 2:
            arr = arr[..., None]
        h, w, c = arr.shape
        rgba = np.zeros((h, w, 4), np.float32)
        rgba[..., :c] = arr
        if c == 1:
            rgba[..., 1] = rgba[..., 2] = arr[..., 0]
        t = ctx.texture((w, h), 4, rgba.tobytes(), dtype='f4')
        _sprites[key] = (t, a)      # se guarda 'a' para que el id no se reuse
        return t
    return t[0]


# ---------------------------------------------------------------- filtros
def _gauss_k(sigma, u8=False):
    n = int(round(sigma * (3 if u8 else 4) * 2 + 1)) | 1
    return cv2.getGaussianKernel(n, sigma, cv2.CV_32F).ravel()


def _sep(t, wts, horiz, border=0, round8=False, anchor=None):
    w = np.zeros(256, np.float32)
    w[:len(wts)] = wts
    p = _progs['sep']
    p['w'].write(w.tobytes())
    return _run('sep', t.size, (('A', t),), horiz=1 if horiz else 0, n=len(wts),
                anchor=len(wts) // 2 if anchor is None else anchor, border=border, round8=1 if round8 else 0)


def gauss(f, sigma, u8=False):
    k = _gauss_k(sigma, u8)
    t = f.t if isinstance(f, G) else f
    a = _sep(t, k, True)
    b = _sep(a, k, False, round8=u8)
    _pool.setdefault(a.size, []).append(a)
    return G(b, f.ch if isinstance(f, G) else 3)


def box_h(f, L, border):
    return G(_sep(f.t, np.full(L, 1.0 / L, np.float32), True, border=border, anchor=L // 2), f.ch)


def area4(f):
    return G(_run('area', (f.t.size[0] // 4, f.t.size[1] // 4), (('A', f.t),), f=4), f.ch)


def resize_lin(f, w, h, base=None, k=1.0):
    sw, sh = f.t.size
    return G(_run('lin', (w, h), (('A', f.t), ('Bt', base.t if base is not None else None)),
                  sc=(sw / w, sh / h), hasb=1 if base is not None else 0, k=float(k)), 3)


def _warp(f, M, cubic, zero=False):
    iM = cv2.invertAffineTransform(np.asarray(M, np.float64))
    return G(_run('warp', f.t.size, (('A', f.t),), m0=tuple(iM[0]), m1=tuple(iM[1]), cubic=1 if cubic else 0,
                  zero=1 if zero else 0), 3)


# ---------------------------------------------------------------- versiones GPU de las funciones de render.py
LUT_T = None
VIGN_G = None
LOOK = None
_SDIV = [0] + [int(round((255 << 12) / i)) for i in range(1, 256)]
_HDIV = [0] + [int(round((180 << 12) / (6.0 * i))) for i in range(1, 256)]


def setup(R):
    """Sube las tablas fijas de render.py (curva de color, viñeta)."""
    global LUT_T, VIGN_G, LOOK
    LOOK = R['LOOK']
    lut = R['LUT'].reshape(256, 3).astype(np.float32)
    rgba = np.zeros((1, 256, 4), np.float32)
    rgba[0, :, :3] = lut
    LUT_T = ctx.texture((256, 1), 4, rgba.tobytes(), dtype='f4')
    v = R['VIGN'][..., 0].astype(np.float32)
    rgba = np.zeros((H, W, 4), np.float32)
    rgba[..., 0] = v
    VIGN_G = G(ctx.texture((W, H), 4, rgba.tobytes(), dtype='f4'), 1)
    p = _progs['grade']
    p['sdiv'].value = _SDIV
    p['hdiv'].value = _HDIV


def bloom(f, amount, thresh=185):
    sm = area4(f)
    hi = clip(sm - float(thresh), 0.0, None) * (255.0 / (255.0 - thresh))
    g = gauss(hi, 8) + gauss(hi, 26) * 0.8
    return resize_lin(g, W, H, base=f, k=amount)


def streak(f, amount, tint):
    sm = area4(f)
    hi = clip(chmax(sm) - 225.0, 0.0, None) / 30.0
    s1 = box_h(box_h(hi, 161, 0), 161, 0)
    s1 = gauss(s1, 1.5)
    a = np.frombuffer(_fbo(s1.t).read(components=1, dtype='f4'), np.float32)
    s1 = s1 * (1.0 / max(1.0, float(a.max()) * 1.6))
    return resize_lin(s1 * np.asarray(tint, np.float32), W, H, base=f, k=amount * 120)


def grade(f8):
    tex, nv = upload(f8)
    c = G(_run('grade', (W, H), tex + (('L', LUT_T),), nv12=nv, sat=float(LOOK['saturation'])))
    sh = gauss(c, 1.2, u8=True)
    f = G(_run('bin', (W, H), (('A', c.t), ('B', sh.t)), am=0, bm=0, op=4, k=(1 + LOOK['sharpen'], -LOOK['sharpen'])))
    return bloom(f, LOOK['bloom'], LOOK['bloom_threshold']) * VIGN_G


def affine(f, s, cx, cy, dx=0.0, dy=0.0, clamp=True):
    if clamp:
        hw, hh = W / (2 * s), H / (2 * s)
        cx = min(max(cx, hw), W - hw)
        cy = min(max(cy, hh), H - hh)
    if abs(s - 1) < 1e-4 and abs(cx - W / 2) < .5 and abs(cy - H / 2) < .5 and dx == 0 and dy == 0:
        return f
    return _warp(f, [[s, 0, W / 2 - s * cx + dx], [0, s, H / 2 - s * cy + dy]], True)


def zoom(f, z, dx=0, dy=0):
    return affine(f, z, W / 2, H / 2, dx, dy, clamp=False)


def shift(f, dx):
    return _warp(f, [[1, 0, dx], [0, 1, 0]], False)


def shrink(f, z, ang=0.0):
    if z >= 0.9999 and abs(ang) < 1e-3:
        return f
    return _warp(f, cv2.getRotationMatrix2D((W / 2, H / 2), ang, z), False, zero=True)


def hblur(f, L):
    L = int(L)
    if L < 3:
        return f
    return box_h(f, L, 1)


def radial_blur(f, strength, n=5):
    if strength < 0.004:
        return f
    acc = f
    for i in range(1, n):
        acc = acc + zoom(f, 1 + strength * i / (n - 1))
    return acc / n


def rgb_split(f, px):
    if px < 0.6:
        return f
    return G(_run('split', f.t.size, (('A', f.t),), px=float(px)))


def leak(px, inten=1.0, col=(150, 205, 255)):
    return G(_run('leak', (W, H), (('Bt', None),), hasb=0, lx=float(px), inten=float(inten),
                  col=tuple(float(c) for c in col), wh=(float(W), float(H))))


def ring(f, te, dur=0.45, strength=1.0, col=(255, 240, 225)):
    if te < 0 or te > dur:
        return f
    x = te / dur
    eo = 1 - (1 - min(max(x, 0), 1)) ** 3
    return G(_run('ring', f.t.size, (('A', f.t),), rad=60 + 1000 * eo, th=22 * (1 - x) + 3, amp=(1 - x) * 0.55 * strength,
                  col=tuple(float(c) for c in col), wh=(float(W), float(H))))


def _sprite_draw(f, a, cx, cy, mode, col=(0, 0, 0), al=1.0, scale=1.0, mask=None):
    st = sprite_tex(a)
    h0, w0 = a.shape[:2]
    if abs(scale - 1) > 1e-3:
        w, h = int(round(w0 * scale)), int(round(h0 * scale))
        inv = (1.0 / scale, 1.0 / scale)
    else:
        w, h, inv = w0, h0, (1.0, 1.0)
    x0, y0 = int(cx - w / 2), int(cy - h / 2)
    xa, ya, xb, yb = max(0, x0), max(0, y0), min(W, x0 + w), min(H, y0 + h)
    if xa >= xb or ya >= yb:
        return f
    minv = (1.0, 1.0)
    mt = None
    if mask is not None:
        mt = sprite_tex(mask)
        mh, mw = mask.shape[:2]
        minv = (mw / w, mh / h)
    blend = {0: (moderngl.ONE, moderngl.ONE), 1: (moderngl.ONE, moderngl.ONE_MINUS_SRC_ALPHA),
             2: (moderngl.ONE, moderngl.ONE_MINUS_SRC_ALPHA)}[mode]
    _run('sprite', f.t.size, (('S', st), ('M', mt)), out=f.t, blend=blend, scissor=(xa, ya, xb - xa, yb - ya),
         org=(x0, y0), inv=inv, minv=minv, mode=mode, col=tuple(float(c) for c in col), al=float(al))
    return f


def blit(f, a, cx, cy, col, al, scale=1.0):
    if al <= 0.002:
        return
    _sprite_draw(f, a, cx, cy, 0, col, al, scale)


def darken(f, a, cx, cy, al, scale=1.0):
    if al <= 0.002:
        return
    _sprite_draw(f, a, cx, cy, 1, al=al, scale=scale)


def paste_avatar(f, R, sc, al):
    img, m = R['LG_M'], R['LMASK']
    cx, cy = R['LOGO_C']
    return _sprite_draw(f, img, cx, cy, 2, al=al, scale=sc, mask=m)


def logo_ring(f, t, sweep, pulse, R):
    cx, cy = R['LOGO_C']
    return G(_run('logo_ring', (W, H), (('Bt', f.t),), c=(float(cx), float(cy)), lr=float(R['LR']), sweep=float(sweep),
                  t=float(t), gk=0.35 + 0.35 * pulse, c1=tuple(map(float, R['RING_COLS'][0])),
                  c2=tuple(map(float, R['RING_COLS'][1])), c3=tuple(map(float, R['RING_COLS'][2]))))


def orbs(t, R):
    w4, h4 = W // 4, H // 4
    sm = _tex(w4, h4)
    fb = _fbo(sm)
    fb.use()
    fb.clear(0.0, 0.0, 0.0, 0.0)
    for ob in R['ORBS']:
        te = t - ob['t']
        if te < 0 or te > 1.2:
            continue
        al = math.exp(-te / 0.35) * min(1, te / 0.03)
        cx = (ob['x'] + ob['vx'] * te) / 4
        cy = (ob['y'] + ob['vy'] * te) / 4
        r = ob['r'] / 4 * (1 + 0.4 * te)
        _run('circle', (w4, h4), out=sm, blend=(moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA),
             c=(float(int(cx)), float(int(cy))), r=float(int(r)), col=tuple(float(c) for c in ob['col'] * al))
    g = G(sm)
    s = gauss(g, 6) * 0.5 + gauss(g, 18) * 0.4
    return resize_lin(s, W, H)
