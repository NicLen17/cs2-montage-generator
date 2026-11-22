"""Edit rápido de un comando: clips + canción -> video, sin escribir un plan a mano.

    python engine/auto.py <carpeta con clips y una canción>      crea projects/<nombre>/ y arma un borrador
    python engine/auto.py projects/<nombre>                      lo mismo sobre un proyecto que ya existe
    opciones:  --name mi_edit     nombre del proyecto (por defecto, el de la canción)
               --final            render final 1080p60 en vez del borrador
               --plan-only        solo analiza y escribe edit.json (para retocarlo a mano o en la interfaz)
               --force            vuelve a armar edit.json aunque ya exista
               --reactions        busca festejos al final de cada play (Demucs por clip: varios minutos)

Qué hace: analiza la canción y los clips, puntúa cada play (engine/score.py), elige y ordena las mejores para que
entren en la canción (la mejor en el drop principal, una buena de apertura, las más flojas primero), escribe edit.json,
lo controla con check_kills.py y renderiza. Usa solo las kills que el detector da por seguras; lo dudoso queda listado
al final para revisar. El resultado es un punto de partida prolijo: los títulos, los momentos de sincronía y las tomas
se afinan después en edit.json (docs/edit-json.md) o en la interfaz web.
"""
import argparse, json, os, re, shutil, subprocess, sys

import numpy as np

ENGINE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(ENGINE)
sys.path.insert(0, ENGINE)
import planner, preset, project as proj, score

PY = sys.executable
SONG_EXT = ('.mp3', '.wav', '.m4a', '.flac')
CONF_OK = 0.6            # confianza desde la que una kill del detector se usa sin que nadie la mire
TITLES = {4: '4K', 5: 'ACE'}


def say(*a):
    print(*a, flush=True)


def run(script, *args, quiet=False):
    r = subprocess.run([PY, os.path.join(ENGINE, script), *args], capture_output=quiet, text=True, encoding='utf-8',
                       errors='replace', env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
    if r.returncode != 0 and not quiet:
        raise SystemExit(f'Falló {script}')
    return r


def probe(path):
    r = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=r_frame_rate:format=duration',
                        '-of', 'json', path], capture_output=True, text=True)
    d = json.loads(r.stdout or '{}')
    num, den = (d.get('streams') or [{}])[0].get('r_frame_rate', '60/1').split('/')
    return float(num) / max(1.0, float(den)), float(d.get('format', {}).get('duration', 0) or 0)


def slugify(s):
    s = re.sub(r'[^a-z0-9]+', '_', os.path.splitext(os.path.basename(s))[0].lower()).strip('_')
    return s or 'edit'


def create_project(src, name=None):
    """Arma projects/<nombre>/ a partir de una carpeta con clips (.mp4) y una canción. Los originales no se tocan."""
    files = sorted(os.listdir(src))
    clips = [f for f in files if f.lower().endswith('.mp4')]
    songs = [f for f in files if f.lower().endswith(SONG_EXT)]
    if not clips: raise SystemExit(f'No hay clips .mp4 en {src}')
    if not songs: raise SystemExit(f'No hay canción ({", ".join(SONG_EXT)}) en {src}')
    name = name or slugify(songs[0])
    dst = os.path.join(ROOT, 'projects', name)
    if os.path.exists(os.path.join(dst, 'clips')):
        say(f'El proyecto {name} ya existe: se usa como está.'); return dst
    os.makedirs(os.path.join(dst, 'clips'))
    lines = []
    for i, f in enumerate(clips, 1):
        out = os.path.join(dst, 'clips', f'c{i}.mp4'); fps, _ = probe(os.path.join(src, f))
        if abs(fps - 60) < 0.5:
            shutil.copy2(os.path.join(src, f), out); note = ''
        else:           # el motor trabaja a 60 fps: los demás se pasan (repitiendo cuadros, sin inventar movimiento)
            subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', os.path.join(src, f), '-vf', 'fps=60', '-c:v', 'libx264', '-crf', '14',
                            '-preset', 'fast', '-c:a', 'aac', '-b:a', '256k', out], check=True)
            note = f'   (original a {fps:.0f} fps, pasado a 60)'
        lines.append(f'c{i} <- {f}{note}')
    open(os.path.join(dst, 'clips_map.txt'), 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
    song = songs[0]
    if song.lower().endswith('.mp3'):
        shutil.copy2(os.path.join(src, song), os.path.join(dst, 'song.mp3'))
    else:
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', os.path.join(src, song), '-b:a', '320k', os.path.join(dst, 'song.mp3')], check=True)
    say(f'Proyecto {name}: {len(clips)} clips, canción {song}')
    return dst


def analyze(project, reactions=False):
    J = lambda f: os.path.join(project, f)
    if not os.path.exists(J('song.json')):
        say('\n[1/4] Canción: beats, drops y energía...'); run('analyze_song.py', project, quiet=True)
    else:
        say('\n[1/4] Canción: ya analizada')
    if os.path.exists(os.path.join(ROOT, 'catalog', 'clips.json')) and not os.path.exists(J('kf.json')):
        run('catalog.py', 'prefill', project, quiet=True)          # los clips ya verificados traen sus kills
    if not os.path.exists(J('shots.json')) or not os.path.exists(J('kf_conf.json')):
        say('[2/4] Clips: leyendo el killfeed y los disparos...'); run('analyze_clips.py', project, quiet=True)
    else:
        say('[2/4] Clips: ya analizados')
    if reactions and not os.path.exists(J('reactions.json')):
        say('      Festejos al final de cada play (Demucs)...'); run('reactions.py', project, '--all', quiet=True)


# ---------- del análisis a las plays ----------
def load_plays(project, st):
    """Una play por clip: sus tomas (kills seguidas), su puntaje y lo que quedó dudoso."""
    J = lambda f: os.path.join(project, f)
    shots = {int(k): v for k, v in json.load(open(J('shots.json'))).items()}
    kf = {int(k): v for k, v in json.load(open(J('kf.json'))).items()} if os.path.exists(J('kf.json')) else {}
    conf = json.load(open(J('kf_conf.json'), encoding='utf-8')) if os.path.exists(J('kf_conf.json')) else {}
    verified = set(json.load(open(J('verified.json')))) if os.path.exists(J('verified.json')) else set()
    rx = json.load(open(J('reactions.json'))) if os.path.exists(J('reactions.json')) else {}
    cuts = st['cuts']; gap_max = cuts['gap_max']; post = cuts['post_max']['normal']
    plays, doubts = [], []
    for c in sorted(shots):
        path = J(f'clips/c{c}.mp4')
        if not shots[c] or not os.path.exists(path): continue
        _, dur = probe(path)
        evs = (conf.get(str(c)) or {}).get('kills', [])
        ok = []
        for j, s in enumerate(shots[c]):
            k = kf.get(c, shots[c])[j] if j < len(kf.get(c, [])) else s
            near = min(evs, key=lambda e: abs(e['t'] - k), default=None)
            sure = c in verified or str(c) in verified or near is None or abs(near['t'] - k) > 0.7 or near['conf'] >= CONF_OK
            if sure: ok.append(j)
            else: doubts.append((c, j, round(k, 2), near.get('why', '')))
        if not ok: continue
        takes = [[ok[0]]]
        for j in ok[1:]:
            (takes[-1].append(j) if shots[c][j] - shots[c][takes[-1][-1]] <= gap_max else takes.append([j]))
        segs = []
        for i, t in enumerate(takes):
            first, last = shots[c][t[0]], shots[c][t[-1]]
            end = round(min(dur - 0.05, last + post), 2)
            lead = round(min(cuts['pre_min']['primera'] if i == 0 else cuts['pre_min']['normal'], max(0.4, first - 0.05)), 2)
            if end - last < 0.5: continue                       # el clip se corta encima de la kill: no se ve caer
            segs.append(dict(kill=t[0], end=end, lead=lead, kills=t))
        if not segs: continue
        ks = [shots[c][j] for s in segs for j in s['kills']]
        types = [(near.get('tipo') or []) for near in (min(evs, key=lambda e: abs(e['t'] - k), default={}) for k in ks)] if evs else None
        sc = score.score(dict(kills=ks, kill_types=types, reaction=score.best_reaction(rx.get(str(c)))))
        length = sum(s['lead'] + (s['end'] - shots[c][s['kill']]) + 0.25 for s in segs)
        plays.append(dict(clip=c, segs=segs, score=sc['score'], n=len(ks), length=length, dur=dur, shots=shots[c],
                          tail=dur - segs[-1]['end']))
    return plays, doubts


def to_play(p, title=True):
    d = dict(clip=p['clip'], segs=p['segs'])
    if title and p['n'] in TITLES: d['cap'] = [TITLES[p['n']], '']
    return d


def make_edit(project, st=None):
    """Elige y ordena las plays para que entren en la canción. Devuelve (edit, resumen)."""
    st = st or preset.load()
    J = lambda f: os.path.join(project, f)
    info = json.load(open(J('song.json'), encoding='utf-8'))
    grid = np.load(J('grid.npy')); beat = float(np.median(np.diff(grid)))
    sg = info['suggest']; dur = info['duration']
    plays, doubts = load_plays(project, st)
    if len(plays) < 4:
        raise SystemExit(f'Hacen falta al menos 4 plays con kills seguras y se encontraron {len(plays)}. '
                         f'Revisá sheets/kf_dudosos.jpg y corregí kf.json, o sumá clips.')
    plays.sort(key=lambda p: -p['score'])
    close_len, outro_len = st['cuts']['close_len'], st['cuts']['outro_len']
    cam = st['camera']['rect']

    # mejor play: en el drop principal. Cierre: una buena play con cola de clip para el zoom a la cámara.
    best = plays[0]
    closers = [p for p in plays[1:] if p['tail'] >= close_len + 0.2]
    closer = closers[0] if closers else None
    # apertura: una play de una sola toma con lugar antes de la primera kill (sale del logo 4 beats antes del drop)
    rest = [p for p in plays[1:] if p is not closer]
    openers = [p for p in rest if len(p['segs']) == 1 and p['shots'][p['segs'][0]['kill']] >= 4 * beat + 0.2]
    opener = openers[0] if openers else max(rest, key=lambda p: p['shots'][p['segs'][0]['kill']])
    pool = [p for p in rest if p is not opener]

    open_end = opener['segs'][0]['end']
    a1_room = (sg['drop2'] - 8 * beat) - (sg['drop1'] + (open_end - opener['shots'][opener['segs'][0]['kill']]))
    a2_room = dur - sg['drop2'] - close_len - outro_len - 2.0 - best['length'] - (closer['length'] if closer else 0)
    act2_mid = []
    for p in pool[:]:                               # después del drop, las mejores que queden
        if p['length'] <= a2_room and len(act2_mid) < 6:
            act2_mid.append(p); a2_room -= p['length']; pool.remove(p)
        if len(act2_mid) >= 2 and a2_room < 6: break
    act1 = []
    for p in pool[:]:
        if sum(q['length'] for q in act1) + p['length'] <= a1_room + 1.0:
            act1.append(p); pool.remove(p)
    act1.sort(key=lambda p: p['score'])             # de menos a más: el acto 1 va creciendo hasta el drop

    def build(a1, a2mid):
        edit = dict(version=planner.VERSION,
                    song=dict(title=os.path.basename(project).replace('_', ' ').upper(), start=sg['start'], drop1=sg['drop1'],
                              drop2=sg['drop2']),
                    open=dict(clip=opener['clip'], end=open_end),
                    close=dict(clip=(closer or (a2mid[-1] if a2mid else best))['clip'], len=close_len),
                    ace_clip=next((p['clip'] for p in [best] + a1 + a2mid if p['n'] >= 5), None),
                    cam={str(opener['clip']): cam, str((closer or (a2mid[-1] if a2mid else best))['clip']): cam},
                    reveal=True,
                    act1=[to_play(p) for p in a1],
                    act2=[to_play(best)] + [to_play(p) for p in a2mid] + ([to_play(closer)] if closer else []))
        return edit

    # ajuste fino con el planificador real: que el acto 1 termine justo antes de la revelación y el video no pase la canción
    edit = None
    for _ in range(40):
        edit = build(act1, act2_mid)
        try:
            ns = planner.build(edit, project)
        except planner.EditError:
            if act2_mid: pool.append(act2_mid.pop())
            elif len(act1) > 1: pool.append(act1.pop(0))
            else: raise
            continue
        resid = ns.RESID['interlude']
        over = ns.TOTAL + ns.SONG_A0 - (dur - 0.5)
        if over > 0 and act2_mid:
            pool.append(act2_mid.pop()); continue
        if resid < 0:                               # el acto 1 se pasa del drop: sale la play que mejor lo ajusta
            fits = [p for p in act1 if p['length'] >= -resid] or act1
            out = min(fits, key=lambda p: (p['length'], p['score'])); act1.remove(out); pool.append(out); continue
        if resid > 2.0:                             # sobra lugar: entra la que mejor lo llena
            fits = [p for p in pool if p['length'] <= resid + 0.3]
            if fits:
                add = max(fits, key=lambda p: p['length']); pool.remove(add); act1.append(add)
                act1.sort(key=lambda p: p['score']); continue
        break
    ns = planner.build(edit, project)
    used = {s['clip'] for s in ns.segments if s['clip']}
    summary = dict(plays=len(plays), used=len(used), kills=len(ns.kills), total=round(float(ns.TOTAL), 1),
                   resid=round(float(ns.RESID['interlude']), 2), doubts=doubts, unused=sorted(p['clip'] for p in plays if p['clip'] not in used),
                   best=best['clip'], opener=opener['clip'], closer=closer['clip'] if closer else None)
    return edit, summary


def main():
    try: sys.stdout.reconfigure(encoding='utf-8')
    except Exception: pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('path'); ap.add_argument('--name'); ap.add_argument('--final', action='store_true')
    ap.add_argument('--plan-only', action='store_true'); ap.add_argument('--force', action='store_true')
    ap.add_argument('--reactions', action='store_true')
    a = ap.parse_args()
    path = os.path.abspath(a.path)
    project = path if os.path.isdir(os.path.join(path, 'clips')) else create_project(path, a.name)
    analyze(project, a.reactions)
    if proj.has_plan(project) and not a.force:
        say('[3/4] El proyecto ya tiene un plan (edit.json o plan.py): se usa ese. Con --force se arma de nuevo.')
    else:
        say('[3/4] Eligiendo y ordenando las plays...')
        edit, s = make_edit(project)
        if os.path.exists(proj.plan_path(project)):
            os.replace(proj.plan_path(project), os.path.join(project, 'plan_viejo.py'))
        proj.save_edit(project, edit)
        say(f"      {s['used']} de {s['plays']} plays, {s['kills']} kills, {int(s['total'] // 60)}:{s['total'] % 60:04.1f} de video. "
            f"Apertura c{s['opener']}, drop principal c{s['best']}" + (f", cierre c{s['closer']}" if s['closer'] else ''))
        if s['resid'] > 2.0:
            say(f"      Aviso: quedan {s['resid']:.1f} s de más antes del drop principal (faltan plays cortas para llenarlo).")
        if s['doubts']:
            say(f"      {len(s['doubts'])} kills dudosas quedaron afuera (miralas en sheets/kf_dudosos.jpg y, si valen, corregí kf.json):")
            for c, j, t, why in s['doubts'][:12]: say(f'        c{c} kill {j} en {t:.2f}s  ({why})')
    r = run('check_kills.py', project, quiet=True)
    probs = re.search(r'(\d+) problema', r.stdout or '')
    open(os.path.join(project, 'check_kills.txt'), 'w', encoding='utf-8').write(r.stdout or '')
    say(f"      check_kills: {'sin problemas' if not probs else probs.group(1) + ' problema(s)'} (detalle en check_kills.txt)")
    if a.plan_only:
        say(f'\nPlan listo: {proj.edit_path(project)}'); return 0
    say('[4/4] Render ' + ('final...' if a.final else 'del borrador...'))
    run('build.py', project, *([] if a.final else ['--draft']))
    return 0


if __name__ == '__main__':
    sys.exit(main())
