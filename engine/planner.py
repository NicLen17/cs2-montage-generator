"""Arma el timeline de un edit a partir de sus datos (projects/<nombre>/edit.json).

Antes cada proyecto traía esta lógica copiada dentro de su plan.py. Ahora el proyecto guarda solo los datos
(qué clips, qué kills, dónde corta, qué título) y acá se calcula dónde cae cada cosa: cada kill clave en un golpe de la
canción, la intro con el logo, la revelación antes del drop, el cierre y las transiciones.

    python engine/planner.py projects/<nombre>            diagnóstico (tramos, desfase de cada kill, avisos, TOTAL)
    python engine/planner.py projects/<nombre> --json     escribe projects/<nombre>/timeline.json

build(edit, project) devuelve un objeto con los mismos nombres que dejaba plan.py (segments, kills, captions,
boundaries, TOTAL, ACT1, ACT2, ...): el resto del motor no distingue un proyecto nuevo de uno viejo.
Formato de edit.json: docs/edit-json.md.
"""
import json, os, sys, types

import numpy as np

VERSION = 1
BT_DEFAULT = ['whip_lr', 'light', 'whip_lr', 'zoom', 'light', 'whip_lr', 'light', 'whip_rl']
KILL_FX_DEFAULT = ['bloom', 'chroma_zoom', 'shake_blur', 'flash', 'radial_zoom', 'pop']
HALF_T = {'mega': 0.30, 'whip_lr': 0.13, 'whip_rl': 0.13, 'light': 0.17, 'zoom': 0.13, 'black_in': 0.70}
BRIGHT_SWAP = {'bloom': 'pop', 'flash': 'chroma_zoom'}      # en cuadros claros estos dos efectos queman la kill
INT_KEYED = ('ctx', 'smax', 'kill_at_seg', 'tech')           # campos de una play con clave = número de tramo o de kill
AUDIO_KEYS = ('AUDIO_MIX', 'GAME_GAIN', 'GAME_EMPH', 'MUSIC_DUCK', 'MUSIC_BED', 'GAME_PRESENCE', 'MUSIC_CARVE',
              'REACT_GAIN', 'REACT_DUCK', 'REACT_HOLD', 'REACT_RELEASE', 'REACT_KINDS', 'GAME_VS_MUSIC', 'REACTIONS')


class EditError(ValueError):
    """edit.json mal armado: el mensaje dice qué play y qué campo."""


# ---------- edit.json <-> plays como las usa el motor ----------
def play_from_json(d, where='play'):
    """Una play de edit.json -> el dict que usan schedule(), check_kills, locate y catalog (tuplas y claves enteras)."""
    P = dict(d)
    if 'segs' in P:
        P['segs'] = [_seg(s, where) for s in P['segs']]
    if 'segs2' in P:
        P['segs2'] = [_seg(s, where) for s in P['segs2']]
    for k in INT_KEYED:
        if k in P:
            P[k] = {int(a): (tuple(b) if isinstance(b, list) else b) for a, b in P[k].items()}
    if P.get('cap') is not None:
        P['cap'] = tuple(P['cap'])
    if 'beats' in P:
        P['beats'] = [None if b is None else set(b) for b in P['beats']]
    if 'burst' in P:
        P['burst'] = [tuple(x) for x in P['burst']]
        if 'at' not in P or len(P['at']) != len(P['burst']):
            raise EditError(f'{where}: una ráfaga necesita un tiempo de canción ("at") por cada kill')
    if 'bang' in P: P['bang'] = tuple(P['bang'])
    if 'slowmo' in P: P['slowmo'] = tuple(P['slowmo'])
    if 'phrase' in P: P['phrase'] = (P['phrase'][0], [tuple(w) for w in P['phrase'][1]])
    if 'clip' not in P and 'burst' not in P:
        raise EditError(f'{where}: falta "clip" (o "burst" si es una ráfaga)')
    if 'clip' in P and 'segs' not in P and 'bang' not in P:
        raise EditError(f'{where} (clip {P["clip"]}): falta "segs"')
    return P


def _seg(s, where):
    if isinstance(s, dict):
        try: return (s['kill'], s['end'], s['lead'], list(s['kills']))
        except KeyError as e: raise EditError(f'{where}: a un tramo le falta {e}') from None
    return (s[0], s[1], s[2], list(s[3]))


def play_to_json(P):
    """Lo inverso (para migrar un plan.py viejo): todo en tipos de JSON."""
    d = {}
    for k, v in P.items():
        if k in ('segs', 'segs2'):
            v = [dict(kill=a, end=b, lead=c, kills=list(e)) for a, b, c, e in v]
        elif k == 'beats':
            v = [None if b is None else sorted(b) for b in v]
        elif k in INT_KEYED:
            v = {str(a): (list(b) if isinstance(b, (tuple, list)) else b) for a, b in v.items()}
        elif k == 'phrase':
            v = [v[0], [list(w) for w in v[1]]]
        elif isinstance(v, (set, frozenset)):
            v = sorted(v)
        d[k] = _plain(v)
    return d


def _plain(x):
    if isinstance(x, (np.floating,)): return float(x)
    if isinstance(x, (np.integer,)): return int(x)
    if isinstance(x, np.ndarray): return [_plain(v) for v in x.tolist()]
    if isinstance(x, dict): return {str(k): _plain(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)): return [_plain(v) for v in x]
    if isinstance(x, (set, frozenset)): return sorted(_plain(v) for v in x)
    return x


# ---------- el planificador ----------
def build(edit, project):
    """edit: dict de edit.json. project: carpeta del proyecto (grid.npy, hits.npy, shots.json). Devuelve el plan."""
    if edit.get('version', 1) > VERSION:
        raise EditError(f'edit.json es de una versión más nueva ({edit["version"]}): actualizá el motor')
    ns = types.ModuleType('plan')
    ns.__file__ = os.path.join(project, 'edit.json')
    J = lambda f: os.path.join(project, f)
    for f in ('grid.npy', 'hits.npy', 'shots.json'):
        if not os.path.exists(J(f)):
            raise EditError(f'falta {f} en el proyecto: corré antes analyze_song.py y analyze_clips.py --shots')
    song = edit.get('song', {})
    FPS = int(edit.get('fps', 60))
    grid = np.load(J('grid.npy')); hits = np.load(J('hits.npy'))
    TGT = np.where(abs(hits - grid) < 0.03, hits, grid)
    BEAT = float(np.median(np.diff(grid)))
    for k in ('start', 'drop1', 'drop2'):
        if k not in song: raise EditError(f'song: falta "{k}" (segundos de la canción)')
    SONG_A0 = float(song['start'])
    IDX_DROP = int(np.argmin(abs(grid - song['drop1'])))
    I_DROP2 = int(np.argmin(abs(grid - song['drop2'])))
    SHOTS = {int(k): v for k, v in json.load(open(J('shots.json'))).items()}
    warnings = []

    def shot(c, j):
        try: return SHOTS[c][j]
        except (KeyError, IndexError):
            raise EditError(f'el clip c{c} no tiene la kill {j} en shots.json') from None

    CAM = {int(k): tuple(v) for k, v in edit.get('cam', {}).items()}
    OPEN_CLIP, OPEN_END = edit['open']['clip'], edit['open']['end']
    END_CLIP, END_LEN = edit['close']['clip'], float(edit['close'].get('len', 6.0))
    ACE_CLIP = edit.get('ace_clip')
    OUTRO_LEN = float(edit.get('outro_len', 4.4))
    REVEAL = bool(edit.get('reveal', True))
    REV_SHIFT = float(edit.get('rev_shift', 0.0))
    VOC = float(edit.get('voc', 0.03))
    LEAD_PLUS = float(edit.get('lead_plus', 0.0))
    BT = list(edit.get('transitions') or BT_DEFAULT)
    tail = edit.get('tail_fill')              # pasa el sobrante del redondeo al beat a la cola de la toma anterior
    if tail is True: tail = {}
    TAIL_MAX = tail.get('max', 0.89) if tail is not None and tail is not False else None
    TAIL_MAX_IN = tail.get('max_in', 0.89) if TAIL_MAX is not None else None
    BI = [0]
    ACT1 = [play_from_json(p, f'act1[{i}]') for i, p in enumerate(edit.get('act1', []))]
    ACT2 = [play_from_json(p, f'act2[{i}]') for i, p in enumerate(edit.get('act2', []))]
    if not ACT2:
        raise EditError('act2 está vacío: hace falta al menos una play después del drop principal')

    segments, kills, kill_play, captions, PHRASES = [], [], [], [], []
    kill_id, kill_flash = [], []
    RESID = {}

    def so(song_time): return song_time - SONG_A0

    def hit_after(t, allowed=None):
        for i, h in enumerate(TGT):
            o = so(h)
            if o >= t and (allowed is None or (i - IDX_DROP) % 4 in allowed): return o, i
        raise EditError(f'no quedan golpes de la canción después de {t + SONG_A0:.1f} s: el edit es más largo que la canción')

    def place_seg(P, pi, si, kj, e, lead, kjs, cursor, play_base, first_on=None):
        c = P['clip']; S = shot(c, kj)
        allowed = P['beats'][si] if 'beats' in P else None
        if si in P.get('smax', {}): lead = S - P['smax'][si]
        if first_on is not None: B = first_on
        elif si == 0 and 'kill_at' in P: B = so(P['kill_at'])
        elif si in P.get('kill_at_seg', {}): B = so(P['kill_at_seg'][si])
        else: B = hit_after(cursor + lead, allowed)[0]
        if TAIL_MAX is not None and first_on is None and segments and segments[-1]['kind'] == 'play' \
                and segments[-1].get('lastk') is not None:
            prev = segments[-1]
            if prev['play'] != play_base + pi:     # cambio de play: la cola puede llegar a 0.9 s + media transición
                typ = P.get('tin') or BT[BI[0] % len(BT)]
                room = TAIL_MAX + HALF_T.get(typ, 0.13) - (prev['s1'] - prev['lastk'])
            else:
                room = TAIL_MAX_IN - (prev['s1'] - prev['lastk'])
            d = min(max(0.0, room), max(0.0, B - cursor - lead))
            prev['s1'] += d; prev['o1'] += d; cursor += d
        if B - cursor < 0.35: warnings.append(('tight lead', c, si, round(B - cursor, 2)))
        s0 = max(0.0, S - (B - cursor)); o1 = cursor + (e - s0)
        seg = dict(clip=c, s0=s0, s1=e, o0=cursor, o1=o1, play=play_base + pi, first=(si == 0), kind='play',
                   tin=P.get('tin') if si == 0 else None)
        if TAIL_MAX is not None:
            seg['lastk'] = max(shot(c, j) for j in kjs)
            if si == 0 and not (play_base == 0 and pi == 0): BI[0] += 1
        segments.append(seg)
        for j in kjs:
            kills.append(cursor + shot(c, j) - s0); kill_play.append(c); kill_id.append((c, j))
            kill_flash.append(j in P.get('flash', []))
        if si == 0 and P.get('cap'): captions.append((cursor + 0.1, P['cap']))
        if 'phrase' in P and P['phrase'][0] == si:
            words = P['phrase'][1]
            offs = [4, 3.5, 2, 1.5]
            PHRASES.append(dict(words=[(B - BEAT * offs[k], w, l) for k, (w, l) in enumerate(words)],
                                vanish=(B - BEAT + 0.33, B - 0.06), start=B - BEAT * 4 - 0.3, inplay=True))
        return o1

    def schedule(plays, cursor, play_base, first_on=None):
        for pi, P in enumerate(plays):
            if 'start_at' in P:
                T = so(P['start_at']); r = T - cursor; RESID[P['clip']] = r
                segments[-1]['o1'] += r; segments[-1]['s1'] += r; cursor = T
            if 'burst' in P:
                items, ats = P['burst'], P['at']; PRE = P.get('pre', 0.14); TAIL = P.get('tail', 0.95); SY = P.get('sync', VOC)
                FX = P.get('fx', 'burst')
                if P.get('cap'): captions.append((cursor + 0.1, P['cap']))
                for k, ((c, j), T) in enumerate(zip(items, ats)):
                    S = shot(c, j); o = so(T) + SY
                    if k == 0:
                        o0 = cursor; s0 = S - (o - cursor)
                        if s0 < 0: warnings.append(('burst lead', c, j, round(S, 2), round(o - cursor, 2)))
                    else:
                        o0 = o - PRE; s0 = S - PRE
                    o1 = (so(ats[k + 1]) + SY - PRE) if k < len(items) - 1 else o + TAIL
                    segments.append(dict(clip=c, s0=s0, s1=s0 + (o1 - o0), o0=o0, o1=o1, play=play_base + pi, first=(k == 0),
                                         kind='play', bang=(k > 0), burst=True, tin=P.get('tin') if k == 0 else None))
                    kills.append(o); kill_play.append(c); kill_id.append((c, j)); kill_flash.append(FX)
                RESID['burst%d' % (play_base + pi)] = so(ats[0]) + SY - cursor
                cursor = o1; continue
            if 'bang' in P:
                TA, TB, kA, kB, end, extra = P['bang']; c = P['clip']
                B = so(TA); sA = shot(c, kA); sB = shot(c, kB)
                if B - cursor < 0.4: warnings.append(('bang lead', c, round(B - cursor, 2)))
                RESID['bang%d' % c] = B - cursor
                segments.append(dict(clip=c, s0=sA - (B - cursor), s1=sA + (TB - TA), o0=cursor, o1=so(TB), play=play_base + pi,
                                     first=True, kind='play', tin=P.get('tin')))
                o0 = so(TB); o1 = o0 + (end - sB)
                segments.append(dict(clip=c, s0=sB, s1=end, o0=o0, o1=o1, play=play_base + pi, first=False, kind='play', bang=True))
                for j, ot in ((kA, B), (kB, o0)):
                    kills.append(ot); kill_play.append(c); kill_id.append((c, j)); kill_flash.append('bang')
                for j in extra:
                    kills.append(o0 + shot(c, j) - sB); kill_play.append(c); kill_id.append((c, j)); kill_flash.append(False)
                cursor = o1; continue
            for si, (kj, e, lead, kjs) in enumerate(P['segs']):
                if si == 0 and play_base == 0 and 'phrase' not in P and not P.get('noplus'): lead += LEAD_PLUS
                cursor = place_seg(P, pi, si, kj, e, lead, kjs, cursor, play_base, first_on if (pi == 0 and si == 0) else None)
            if 'slowmo' in P:
                a, b, D = P['slowmo']
                segments.append(dict(clip=P['clip'], s0=a, s1=b, o0=cursor, o1=cursor + D, play=play_base + pi, first=False, kind='slowmo'))
                cursor += D
                for kj, e, lead, kjs in P.get('segs2', []):
                    cursor = place_seg(P, pi, 99, kj, e, lead, kjs, cursor, play_base)
        return cursor

    # ---- logo y apertura: la primera kill de la apertura cae en el primer drop ----
    o_drop1 = so(TGT[IDX_DROP]); o_logo_end = so(TGT[IDX_DROP - 4])
    if o_logo_end <= 0.5:
        raise EditError('song.start está demasiado cerca de song.drop1: el logo necesita al menos 4 golpes antes del drop')
    segments.append(dict(clip=0, s0=0, s1=0, o0=0.0, o1=o_logo_end, play=-2, first=True, kind='logo'))
    s_k0 = shot(OPEN_CLIP, 0); s0 = max(0.0, s_k0 - (o_drop1 - o_logo_end))
    segments.append(dict(clip=OPEN_CLIP, s0=s0, s1=OPEN_END, o0=o_logo_end, o1=o_logo_end + OPEN_END - s0, play=0, first=False, kind='zoom_out'))
    for j_, s_ in enumerate(SHOTS[OPEN_CLIP]):
        if s0 <= s_ <= OPEN_END:
            kills.append(o_logo_end + s_ - s0); kill_play.append(OPEN_CLIP); kill_id.append((OPEN_CLIP, j_)); kill_flash.append(False)
    cursor = schedule(ACT1, segments[-1]['o1'], 0)
    ACT1_END_SONG = cursor + SONG_A0
    # ---- interludio / revelación: arranca 8 golpes antes del drop principal (la canción sigue, sin saltos) ----
    LA = so(grid[I_DROP2 - 8]) + REV_SHIFT; RESID['interlude'] = LA - cursor
    segments[-1]['o1'] = LA; segments[-1]['s1'] = segments[-1]['s0'] + (LA - segments[-1]['o0'])
    O_DROP2 = so(TGT[I_DROP2]); REV0 = so(grid[I_DROP2 - 4])
    if REVEAL:      # la mejor play se acerca y se ilumina durante 8 golpes hasta el drop
        INTER = (LA, LA); REV0 = LA
    else:           # (viejo) negro con luces
        segments.append(dict(clip=0, s0=0, s1=0, o0=LA, o1=REV0, play=-1, first=True, kind='interlude'))
        INTER = (LA, REV0)
    g = lambda k: so(grid[I_DROP2 - k])
    VANISH = tuple(edit['vanish']) if edit.get('vanish') else (g(1) + 0.12, O_DROP2 - 0.12)
    WORDS = [tuple(w) for w in edit.get('words', [])]
    n_act2 = len(segments)
    cursor = schedule(ACT2, REV0, 100, first_on=O_DROP2)
    if REVEAL:
        segments[n_act2]['tin'] = 'black_in'      # el primer acto se funde a negro y de ahí sale la revelación
        captions[:] = [((O_DROP2 + 0.05) if abs(o - (REV0 + 0.1)) < 1e-6 else o, c) for o, c in captions]   # título en el drop
    # ---- cierre con la cámara y outro ----
    last = segments[-1]
    segments.append(dict(clip=END_CLIP, s0=last['s1'], s1=last['s1'] + END_LEN, o0=cursor, o1=cursor + END_LEN, play=last['play'], first=False, kind='face_out'))
    cursor += END_LEN
    segments.append(dict(clip=0, s0=0, s1=0, o0=cursor, o1=cursor + OUTRO_LEN, play=-3, first=False, kind='outro'))
    OUTRO0 = cursor; TOTAL = cursor + OUTRO_LEN
    song_map = [(0.0, 1e9, SONG_A0)]

    def out_hits(lo, hi):
        return sorted([(so(h), i) for i, h in enumerate(TGT) if lo <= so(h) < hi])

    # ---- transiciones ----
    boundaries = []; bi = 0
    for i in range(1, len(segments)):
        a, b = segments[i - 1], segments[i]
        if b['kind'] in ('zoom_out', 'face_out', 'slowmo', 'outro') or a['kind'] in ('logo', 'interlude'): continue
        if b['kind'] == 'interlude': boundaries.append((b['o0'], 'black_in', i)); continue
        if b.get('bang'): boundaries.append((b['o0'], 'cut', i)); continue
        if a['play'] != b['play']:
            typ = b.get('tin') or ('light' if a['kind'] == 'slowmo' else BT[bi % len(BT)])
            boundaries.append((b['o0'], typ, i)); bi += 1
        else:
            boundaries.append((b['o0'], 'whip_short' if i % 2 else 'light_short', i))

    # ---- efecto de cada kill ----
    base = list(edit.get('kill_fx') or KILL_FX_DEFAULT)
    if edit.get('kill_fx_explicit'):
        KILL_FX = list(edit['kill_fx_explicit'])
    elif edit.get('kill_fx_bright', True):
        bright = json.load(open(J('kill_bright.json'))) if os.path.exists(J('kill_bright.json')) else {}
        KILL_FX = []
        for ki, (c, j) in enumerate(kill_id):
            fx = base[ki % len(base)]
            if fx in BRIGHT_SWAP and bright.get('%d:%d' % (c, j), 0) > 0.35: fx = BRIGHT_SWAP[fx]
            KILL_FX.append(fx)
    else:
        KILL_FX = base

    loc = dict(locals())
    for k in ('FPS', 'grid', 'hits', 'TGT', 'BEAT', 'SONG_A0', 'IDX_DROP', 'I_DROP2', 'SHOTS', 'shot', 'CAM', 'OPEN_CLIP',
              'OPEN_END', 'END_CLIP', 'END_LEN', 'ACE_CLIP', 'OUTRO_LEN', 'REVEAL', 'VOC', 'BT', 'ACT1', 'ACT2', 'segments',
              'kills', 'kill_play', 'kill_id', 'kill_flash', 'captions', 'PHRASES', 'RESID', 'so', 'hit_after', 'LA',
              'O_DROP2', 'REV0', 'INTER', 'VANISH', 'WORDS', 'ACT1_END_SONG', 'OUTRO0', 'TOTAL', 'song_map', 'out_hits',
              'boundaries', 'KILL_FX'):
        setattr(ns, k, loc[k])
    ns.SONG_TITLE = str(song.get('title', '')).upper()
    ns.SYNC = list(song.get('sync', []))
    ns.FRANTIC = [tuple(x) for x in song.get('frantic', [])]
    ns.SLOWMO_SRC = {int(k): tuple(v) for k, v in edit.get('slowmo_src', {}).items()}
    for k, v in edit.get('audio', {}).items():
        if k not in AUDIO_KEYS:
            raise EditError(f'audio: "{k}" no existe. Opciones: {", ".join(AUDIO_KEYS)}')
        if k == 'REACTIONS' and isinstance(v, dict): v = {int(a): b for a, b in v.items()}
        setattr(ns, k, tuple(v) if k == 'REACT_KINDS' else v)
    for k, v in edit.get('vars', {}).items():
        setattr(ns, k, v)
    ns.WARNINGS = warnings
    ns.EDIT = edit
    return ns


def timeline(ns):
    """Lo que el render y el audio necesitan del plan, en tipos de JSON (projects/<nombre>/timeline.json)."""
    keys = ('FPS', 'TOTAL', 'SONG_A0', 'SONG_TITLE', 'segments', 'kills', 'kill_play', 'kill_id', 'kill_flash', 'captions',
            'boundaries', 'KILL_FX', 'WORDS', 'VANISH', 'INTER', 'O_DROP2', 'REV0', 'OUTRO0', 'END_LEN', 'OUTRO_LEN',
            'REVEAL', 'SYNC', 'song_map', 'CAM', 'OPEN_CLIP', 'END_CLIP', 'ACE_CLIP', 'SLOWMO_SRC')
    d = {k: _plain(getattr(ns, k)) for k in keys if hasattr(ns, k)}
    d['beats'] = [[round(float(o), 4), int(i)] for o, i in ns.out_hits(0, ns.TOTAL)]
    d['warnings'] = _plain(getattr(ns, 'WARNINGS', []))
    return d


def diagnose(ns):
    for s in ns.segments:
        print({k: (round(float(v), 2) if isinstance(v, (float, np.floating)) else v) for k, v in s.items() if k not in ('first',)})
    allh = np.array([ns.so(h) for h in ns.TGT])
    print('desfase de cada kill con el golpe más cercano (ms):', [int(round(1000 * min(abs(allh - k)))) for k in ns.kills])
    print('RESID', {k: round(float(v), 2) for k, v in ns.RESID.items()})
    print('fin del acto 1 (canción)', round(ns.ACT1_END_SONG, 2), '· revelación', round(ns.LA + ns.SONG_A0, 2))
    print('títulos', [(round(float(o), 2), c) for o, c in ns.captions])
    for w in getattr(ns, 'WARNINGS', []): print('AVISO', *w)
    print('TOTAL', round(ns.TOTAL, 2), '· canción al empezar el outro', round(ns.OUTRO0 + ns.SONG_A0, 1))


if __name__ == '__main__':
    try: sys.stdout.reconfigure(encoding='utf-8')
    except Exception: pass
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from project import load_plan
    proj = os.path.abspath(sys.argv[1])
    try:
        p = load_plan(proj)
    except EditError as e:
        raise SystemExit(f'edit.json: {e}')
    if '--json' in sys.argv:
        out = os.path.join(proj, 'timeline.json')
        json.dump(timeline(p), open(out, 'w', encoding='utf-8'), indent=1)
        print('Escrito', out)
    else:
        diagnose(p)
