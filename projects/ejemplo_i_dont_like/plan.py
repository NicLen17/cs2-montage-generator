import numpy as np, json
FPS = 60
import os
W_ = os.path.dirname(os.path.abspath(__file__)) + os.sep
grid = np.load(W_ + 'grid.npy'); hits = np.load(W_ + 'hits.npy')
TGT = np.where(abs(hits - grid) < 0.03, hits, grid)
IDX_DROP = int(np.argmin(abs(grid - 11.44)))
BEAT = float(np.median(np.diff(grid)))
SONG_A0 = 3.0
SONG_TITLE = "I DON'T LIKE"
I_DROP2 = int(np.argmin(abs(grid - 142.22)))
MEGA_AT = float(TGT[int(np.argmin(abs(grid - 116.06)))])
SHOTS = {int(k): v for k, v in json.load(open(W_ + 'shots.json')).items()}
SHOTS[13] = [SHOTS[13][0], 9.83, SHOTS[13][2]]
SHOTS[15] = [SHOTS[15][0], SHOTS[15][1], 12.906, SHOTS[15][2]]
SHOTS[26] = [SHOTS[26][0], SHOTS[26][1], 9.80, SHOTS[26][2]]
SHOTS[3] = [SHOTS[3][0], 6.879, SHOTS[3][2], SHOTS[3][3]]
SHOTS[2] = [SHOTS[2][0], SHOTS[2][1], 15.65]
SHOTS[16] = [SHOTS[16][0], 19.50, 20.85]
def shot(c, j): return SHOTS[c][j]
CAM = {24: (24, 20, 490, 280), 20: (24, 20, 490, 290)}
OPEN_CLIP, END_CLIP, ACE_CLIP = 24, 20, 6
SLOWMO_SRC = {1: ('slow_c1.mp4', 24.80), 18: ('slow_c18.mp4', 8.25)}
ANY = None; DOWN = {0}; BACK = {1, 3}

ACT1 = [
    dict(clip=24, segs=[(1, 9.35, 0.4, [1, 2])]),
    dict(clip=9, segs=[(0, 7.05, 1.3, [0, 1])]),
    dict(clip=8, segs=[(0, 9.00, 1.4, [0, 1])]),
    dict(clip=27, segs=[(0, 12.75, 1.3, [0, 1, 2])]),
    dict(clip=10, segs=[(0, 11.25, 1.3, [0, 1, 2])]),
    dict(clip=16, bang=(35.40, 35.57, 1, 2, 21.70, [])),
    dict(clip=12, bang=(39.28, 39.44, 0, 1, 7.30, [2])),
    dict(clip=25, bang=(42.62, 42.85, 0, 1, 6.40, [2])),
    dict(clip=5, segs=[(0, 7.60, 1.3, [0]), (1, 14.90, 0.6, [1])]),
    dict(clip=11, segs=[(0, 7.15, 1.3, [0]), (1, 11.95, 0.6, [1]), (2, 20.35, 0.6, [2])]),
    dict(clip=1, flash=[2], segs=[(0, 5.75, 1.4, [0]), (1, 21.05, 0.7, [1]), (2, 24.85, 0.6, [2])], slowmo=(24.85, 25.40, 1.6)),
    dict(clip=2, flash=[2], segs=[(0, 10.25, 1.3, [0]), (1, 11.95, 0.5, [1]), (2, 16.30, 2.0, [2])]),
    dict(clip=13, flash=[2], segs=[(0, 10.35, 1.3, [0, 1]), (2, 40.15, 1.2, [2])]),
    dict(clip=7, segs=[(0, 5.55, 1.3, [0, 1]), (2, 9.15, 0.6, [2]), (3, 25.05, 0.6, [3])]),
    dict(clip=14, segs=[(0, 3.20, 1.3, [0]), (1, 17.00, 0.8, [1]), (2, 19.75, 0.5, [2]), (3, 29.70, 0.6, [3])]),
    dict(clip=15, segs=[(0, 6.20, 1.3, [0]), (1, 8.25, 0.5, [1]), (2, 14.70, 0.7, [2, 3])]),
    dict(clip=26, noplus=True, flash=[3], segs=[(0, 2.15, 0.9, [0]), (1, 6.15, 0.6, [1]), (2, 10.30, 0.6, [2]), (3, 15.20, 0.6, [3])]),
    dict(clip=3, segs=[(0, 4.40, 1.3, [0]), (1, 7.40, 0.6, [1]), (2, 15.55, 0.6, [2]), (3, 25.15, 0.6, [3])]),
    dict(clip=18, flash=[0], segs=[(0, 8.30, 3.8, [0])], slowmo=(8.30, 8.70, 1.6)),
    dict(clip=4, cap=('ACE', 'AK-47'), start_at=MEGA_AT, tin='mega', segs=[(0, 5.25, 0.9, [0]), (1, 16.50, 0.6, [1]), (2, 20.30, 0.6, [2]), (3, 30.60, 0.6, [3]), (4, 46.50, 0.6, [4])]),
    dict(clip=17, cap=('4K', 'AWP'), segs=[(0, 4.45, 0.3, [0]), (1, 11.75, 0.6, [1, 2]), (3, 15.35, 0.6, [3])]),
    dict(clip=23, cap=('4K', 'GLOCK'), segs=[(0, 7.60, 1.4, [0, 1]), (2, 20.00, 1.4, [2]), (3, 24.60, 0.3, [3])]),
]
ACT2 = [
    dict(clip=6, segs=[(0, 7.50, 0.0, [0, 1, 2]), (3, 13.90, 0.6, [3]), (4, 23.40, 0.6, [4])]),
    dict(clip=19, cap=('4K', 'USP-S'), segs=[(0, 4.30, 1.3, [0]), (1, 8.65, 0.6, [1, 2]), (3, 15.35, 0.6, [3])]),
    dict(clip=20, cap=('ACE', 'M4A4'), beats=[DOWN, BACK, BACK], flash=[4], segs=[(0, 6.10, 1.3, [0]), (1, 12.15, 0.6, [1, 2, 3]), (4, 19.40, 0.6, [4])]),
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
segments.append(dict(clip=OPEN_CLIP, s0=s0, s1=6.10, o0=o_logo_end, o1=o_logo_end + 6.10 - s0, play=0, first=False, kind='zoom_out'))
kills.append(o_logo_end + s_k0 - s0); kill_play.append(OPEN_CLIP); kill_id.append((OPEN_CLIP, 0)); kill_flash.append(False)
LEAD_PLUS = 0.75
cursor = schedule(ACT1, segments[-1]['o1'], 0)
LEAD_PLUS = 0.0
ACT1_END_SONG = cursor + SONG_A0
# interlude starts at the next downbeat (song keeps playing, no jumps)
LA = so(grid[I_DROP2 - 8]); RESID['interlude'] = LA - cursor
segments[-1]['o1'] = LA; segments[-1]['s1'] = segments[-1]['s0'] + (LA - segments[-1]['o0'])
O_DROP2 = so(TGT[I_DROP2]); REV0 = so(grid[I_DROP2 - 4])
segments.append(dict(clip=0, s0=0, s1=0, o0=LA, o1=REV0, play=-1, first=True, kind='interlude'))
INTER = (LA, REV0)
g = lambda k: so(grid[I_DROP2 - k])
WORDS_OFF = [(g(7), 'UNA', 0), ((g(7) + g(6)) / 2, 'M4', 0), (g(5), 'CINCO', 1), ((g(5) + g(4)) / 2, 'BAJAS', 1),
         (g(2), 'CERO', 2), ((g(2) + g(1)) / 2, 'DUDAS', 2)]
VANISH = (g(1) + 0.12, O_DROP2 - 0.12)
WORDS = []
cursor = schedule(ACT2, REV0, 100, first_on=O_DROP2)
last = segments[-1]
END_LEN = 3.6
segments.append(dict(clip=END_CLIP, s0=last['s1'], s1=last['s1'] + END_LEN, o0=cursor, o1=cursor + END_LEN, play=last['play'], first=False, kind='face_out'))
cursor += END_LEN
OUTRO_LEN = 5.4
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
