import numpy as np, json
FPS = 60
import os
W_ = os.path.dirname(os.path.abspath(__file__)) + os.sep
grid = np.load(W_ + 'grid.npy'); hits = np.load(W_ + 'hits.npy')
TGT = np.where(abs(hits - grid) < 0.03, hits, grid)
BEAT = float(np.median(np.diff(grid)))
SONG_A0 = float(grid[16])          # la intro de la canción no tiene batería: el video arranca en el compás de 8 s
SONG_TITLE = "MY JEALOUSY"
IDX_DROP = int(np.argmin(abs(grid - 16.05)))      # primer drop (entra el bombo)
I_DROP2 = int(np.argmin(abs(grid - 112.06)))     # segundo drop, después del corte de batería de 110 s
MEGA_AT = float(TGT[int(np.argmin(abs(grid - 64.06)))])   # vuelve la batería completa a los 64 s
SHOTS = {int(k): v for k, v in json.load(open(W_ + 'shots.json')).items()}
def shot(c, j): return SHOTS[c][j]
CAM = {12: (0, 0, 461, 259), 30: (24, 18, 487, 288)}
OPEN_CLIP, END_CLIP, ACE_CLIP = 12, 30, 4
OPEN_END = 17.55                  # la apertura muestra las 3 kills seguidas de c12 en una sola toma
SLOWMO_SRC = {}
REVEAL = False                    # True: revelación de la play antes del drop (sin negro con luces)
ANY = None; DOWN = {0}; BACK = {1, 3}
VOC = 0.03                        # el ataque vocal detectado está ~30 ms antes del golpe que se oye
# c1 DEPRECADO (CS:GO): no se usa.

# Ráfagas solo en el primer y en el último drop: una kill de un clip distinto en cada sílaba de "jea-lou-sy".
B1 = [37.33, 37.74, 38.02, 38.39, 38.73, 39.27]
B2 = [120.99, 121.34, 121.75, 122.00, 122.36, 122.70, 123.25, 123.52]
# Golpes secos del drop después del negro (pico de onset de la pista sin voz): c4 corta en cada uno.
HITS2 = [112.06, 113.04, 114.04, 114.79, 116.05]

ACT1 = [
    dict(clip=16, hard=[0], segs=[(0, 6.85, 1.6, [0, 1])]),
    dict(clip=5, hard=[2], flash=[2], segs=[(0, 3.00, 1.6, [0]), (1, 7.00, 0.9, [1]), (2, 20.20, 1.8, [2])]),
    dict(clip=27, kill_at=32.06, segs=[(0, 13.85, 1.2, [0, 1, 2])]),                      # estribillo 1: kill en el downbeat
    dict(clip=23, segs=[(0, 6.70, 1.3, [0, 1])]),                                         # (antes: primera ráfaga, quitada)
    dict(clip=11, segs=[(0, 6.25, 1.2, [0, 1]), (2, 11.70, 0.9, [2])]),
    dict(clip=18, segs=[(0, 4.40, 1.6, [0]), (1, 8.60, 1.0, [1, 2])]),
    dict(clip=13, cap=('4K', 'AK-47'), hard=[0, 1, 2], segs=[(0, 6.10, 1.9, [0, 1]), (2, 13.55, 1.6, [2, 3])]),
    dict(clip=29, cap=('ACE', 'USP-S'), kill_at=64.06, segs=[(3, 19.10, 2.6, [0, 1, 2, 3, 4])]),   # "stop" (63.0) + drop (64.06)
    dict(clip=21, cap=('4K', 'AK-47'), hard=[0, 2], segs=[(0, 4.40, 1.2, [0]), (1, 19.20, 0.9, [1, 2]), (3, 24.30, 0.9, [3])]),
    dict(clip=17, segs=[(0, 4.85, 1.3, [0])]),
    dict(clip=28, tin='mega', kill_at=80.06, segs=[(0, 7.95, 1.2, [0, 1, 2])]),            # estribillo 2: ráfaga de 3 en 0.7 s
    dict(clip=2, cap=('ACE', 'M4A1-S'), flash=[4], segs=[(1, 4.55, 3.1, [0, 1]), (2, 27.15, 1.3, [2]), (3, 29.65, 1.3, [3]), (4, 34.40, 1.3, [4])]),
    dict(clip=8, cap=('ACE', 'AK-47'), kill_at=96.06, segs=[(0, 6.10, 1.2, [0, 1]), (2, 12.75, 1.4, [2]), (3, 18.05, 1.4, [3]), (4, 34.95, 1.4, [4])]),
]
ACT2 = [
    dict(burst=[(4, 0), (4, 1), (4, 2), (4, 3), (4, 4)], at=HITS2, pre=0.25, sync=0.0, fx=False, tail=0.9, cap=('ACE', 'M4A1-S')),
    dict(clip=22, segs=[(0, 6.80, 1.2, [0])]),
    dict(burst=[(9, 1), (20, 0), (25, 0), (14, 0), (24, 2), (10, 2), (26, 2), (25, 3)], at=B2, pre=0.14),   # arranca con la kill de c9
    dict(clip=3, cap=('CLUTCH 1v4', 'MIRAGE'), flash=[3], segs=[(0, 2.15, 1.0, [0]), (1, 30.75, 0.6, [1, 2]), (3, 33.60, 0.7, [3])]),
    dict(clip=30, cap=('4K', 'AWP'), beats=[ANY, ANY, ANY, BACK], segs=[(0, 3.60, 1.4, [0]), (1, 23.45, 0.9, [1]), (2, 30.15, 0.9, [2]), (3, 34.10, 0.9, [3])]),
]
segments, kills, kill_play, captions, PHRASES = [], [], [], [], []
kill_id, kill_flash = [], []
def so(song_time): return song_time - SONG_A0
def hit_after(t, allowed=None):
    for i, h in enumerate(TGT):
        o = so(h)
        if o >= t and (allowed is None or (i - IDX_DROP) % 4 in allowed): return o, i
    raise ValueError

def place_seg(P, pi, si, kj, e, lead, kjs, cursor, play_base, first_on=None):
    c = P['clip']; S = shot(c, kj)
    allowed = P['beats'][si] if 'beats' in P else None
    if si in P.get('smax', {}): lead = S - P['smax'][si]
    if first_on is not None: B = first_on
    elif si == 0 and 'kill_at' in P: B = so(P['kill_at'])
    elif si in P.get('kill_at_seg', {}): B = so(P['kill_at_seg'][si])
    else: B = hit_after(cursor + lead, allowed)[0]
    if B - cursor < 0.35: print('WARN tight lead', c, si, round(B - cursor, 2))
    s0 = max(0.0, S - (B - cursor)); o1 = cursor + (e - s0)
    segments.append(dict(clip=c, s0=s0, s1=e, o0=cursor, o1=o1, play=play_base + pi, first=(si == 0), kind='play',
                         tin=P.get('tin') if si == 0 else None))
    for j in kjs: kills.append(cursor + shot(c, j) - s0); kill_play.append(c); kill_id.append((c, j)); kill_flash.append(j in P.get('flash', []))
    if si == 0 and P.get('cap'): captions.append((cursor + 0.1, P['cap']))
    if 'phrase' in P and P['phrase'][0] == si:
        words = P['phrase'][1]
        offs = [4, 3.5, 2, 1.5]
        PHRASES.append(dict(words=[(B - BEAT * offs[k], w, l) for k, (w, l) in enumerate(words)],
                            vanish=(B - BEAT + 0.33, B - 0.06), start=B - BEAT * 4 - 0.3, inplay=True))
    return o1

LEAD_PLUS = 0.0
RESID = {}
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
                    if s0 < 0: print('WARN burst lead', c, j, round(S, 2), round(o - cursor, 2))
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
            if B - cursor < 0.4: print('WARN bang lead', c, round(B - cursor, 2))
            RESID['bang%d' % c] = B - cursor
            segments.append(dict(clip=c, s0=sA - (B - cursor), s1=sA + (TB - TA), o0=cursor, o1=so(TB), play=play_base + pi, first=True, kind='play', tin=P.get('tin')))
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

# ---- logo + opening (unchanged) ----
o_drop1 = so(TGT[IDX_DROP]); o_logo_end = so(TGT[IDX_DROP - 4])
segments.append(dict(clip=0, s0=0, s1=0, o0=0.0, o1=o_logo_end, play=-2, first=True, kind='logo'))
s_k0 = shot(OPEN_CLIP, 0); s0 = max(0.0, s_k0 - (o_drop1 - o_logo_end))
segments.append(dict(clip=OPEN_CLIP, s0=s0, s1=OPEN_END, o0=o_logo_end, o1=o_logo_end + OPEN_END - s0, play=0, first=False, kind='zoom_out'))
for j_, s_ in enumerate(SHOTS[OPEN_CLIP]):
    if s0 <= s_ <= OPEN_END: kills.append(o_logo_end + s_ - s0); kill_play.append(OPEN_CLIP); kill_id.append((OPEN_CLIP, j_)); kill_flash.append(False)
LEAD_PLUS = 0.0
cursor = schedule(ACT1, segments[-1]['o1'], 0)
LEAD_PLUS = 0.0
ACT1_END_SONG = cursor + SONG_A0
# interlude starts at the next downbeat (song keeps playing, no jumps)
LA = so(grid[I_DROP2 - 8]); RESID['interlude'] = LA - cursor
segments[-1]['o1'] = LA; segments[-1]['s1'] = segments[-1]['s0'] + (LA - segments[-1]['o0'])
O_DROP2 = so(TGT[I_DROP2]); REV0 = so(grid[I_DROP2 - 4])
if REVEAL:      # revelación: sin negro con luces; la mejor play se acerca y se ilumina durante 8 beats hasta el drop
    INTER = (LA, LA); REV0 = LA
else:
    segments.append(dict(clip=0, s0=0, s1=0, o0=LA, o1=REV0, play=-1, first=True, kind='interlude'))
    INTER = (LA, REV0)
g = lambda k: so(grid[I_DROP2 - k])
WORDS_OFF = [(g(7), 'UNA', 0), ((g(7) + g(6)) / 2, 'M4', 0), (g(5), 'CINCO', 1), ((g(5) + g(4)) / 2, 'BAJAS', 1),
         (g(2), 'CERO', 2), ((g(2) + g(1)) / 2, 'DUDAS', 2)]
VANISH = (g(1) + 0.12, O_DROP2 - 0.12)
WORDS = []
n_act2 = len(segments)
cursor = schedule(ACT2, REV0, 100, first_on=O_DROP2)
if REVEAL:
    segments[n_act2]['tin'] = 'black_in'      # el primer acto se funde a negro y de ahí sale la revelación
    captions[:] = [((O_DROP2 + 0.05) if abs(o - (REV0 + 0.1)) < 1e-6 else o, c) for o, c in captions]   # título en el drop
last = segments[-1]
END_LEN = 6.0
segments.append(dict(clip=END_CLIP, s0=last['s1'], s1=last['s1'] + END_LEN, o0=cursor, o1=cursor + END_LEN, play=last['play'], first=False, kind='face_out'))
cursor += END_LEN
OUTRO_LEN = 4.4
segments.append(dict(clip=0, s0=0, s1=0, o0=cursor, o1=cursor + OUTRO_LEN, play=-3, first=False, kind='outro'))
OUTRO0 = cursor; TOTAL = cursor + OUTRO_LEN
song_map = [(0.0, 1e9, SONG_A0)]
def out_hits(lo, hi):
    return sorted([(so(h), i) for i, h in enumerate(TGT) if lo <= so(h) < hi])

boundaries = []
BT = ['whip_lr', 'light', 'whip_lr', 'zoom', 'light', 'whip_lr', 'light', 'whip_rl']
bi = 0
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
KILL_FX = ['bloom', 'chroma_zoom', 'shake_blur', 'flash', 'radial_zoom', 'pop']

if __name__ == '__main__':
    for s in segments: print({k: (round(float(v), 2) if isinstance(v, (float, np.floating)) else v) for k, v in s.items() if k not in ('first',)})
    allh = np.array([so(h) for h in TGT])
    print('kill offsets (ms):', [int(round(1000 * min(abs(allh - k)))) for k in kills])
    print('RESID', {k: round(v, 2) for k, v in RESID.items()}); print('act1 end song', round(ACT1_END_SONG, 2), 'LA song', round(LA + SONG_A0, 2), 'interlude len', round(REV0 - LA, 2))
    print('captions', [(round(o, 2), c) for o, c in captions]); print('phrases', [[(round(t, 2), w) for t, w, l in p['words']] for p in PHRASES])
    print('TOTAL', round(TOTAL, 2), 'song at outro', round(OUTRO0 + SONG_A0, 1), 'song end', round(TOTAL + SONG_A0, 1))
