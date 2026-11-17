"""Catálogo de clips: cada clip original se verifica UNA vez y sus kills se reusan en todos los edits.

    python engine/catalog.py scan [carpeta]              -> agrega los .mp4 nuevos (por defecto entrada/): fecha, duración, fps, era
    python engine/catalog.py import projects/<nombre>    -> guarda kills y disparos verificados (kf.json + shots.json) y en qué edit se usó
    python engine/catalog.py prefill projects/<nombre>   -> escribe en kf.json/shots.json los clips ya verificados y verified.json
    python engine/catalog.py set <parte_del_nombre|cN@proyecto> clave=valor ...
            claves: weapon, map, rating (1-5), tags (coma), notes, cam (x0,y0,x1,y1), verified (si/no)
    python engine/catalog.py list [--unused] [--min-rating 4] [--tag ace] [--weapon awp] [--map mirage] [--all]
    python engine/catalog.py show <parte_del_nombre>

El catálogo vive en catalog/clips.json. La clave de cada clip es el slug de Twitch (el nombre sin "_source", sin " (1)"),
así que el mismo clip descargado dos veces es la misma entrada.
Clips de antes del 27/09/2023 se marcan era=csgo (HUD viejo de CS:GO): no se usan en los edits.
"""
import os, sys, re, json, subprocess, importlib.util, io, contextlib

ENGINE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(ENGINE)
CAT = os.path.join(ROOT, 'catalog', 'clips.json')
CS2_FROM = '20230927'


def load():
    if os.path.exists(CAT):
        return json.load(open(CAT, encoding='utf-8'))
    return {}


def save(db):
    os.makedirs(os.path.dirname(CAT), exist_ok=True)
    tmp = CAT + '.tmp'
    json.dump(db, open(tmp, 'w', encoding='utf-8'), indent=1, ensure_ascii=False, sort_keys=True)
    os.replace(tmp, CAT)


def slug(fname):
    b = os.path.basename(fname)
    b = re.sub(r'\s*\(\d+\)', '', b)
    b = re.sub(r'\.mp4$', '', b, flags=re.I)
    return re.sub(r'_source$', '', b)


def probe(path):
    r = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=r_frame_rate,width,height:format=duration',
                        '-of', 'json', path], capture_output=True, text=True)
    try:
        j = json.loads(r.stdout); s = j['streams'][0]; n, d = s['r_frame_rate'].split('/')
        return dict(fps=round(float(n) / float(d), 2), w=s['width'], h=s['height'], duration=round(float(j['format']['duration']), 2))
    except Exception:
        return {}


def new_entry(fname):
    k = slug(fname); m = re.match(r'(\d{8})_', k); date = m.group(1) if m else ''
    return dict(file=os.path.basename(fname), date=date, era=('csgo' if date and date < CS2_FROM else 'cs2'),
                kills=None, shots=None, verified=False, weapon='', map='', rating=0, tags=[], notes='', cam=None, used_in=[])


def clip_map(project):
    out = {}
    p = os.path.join(project, 'clips_map.txt')
    if not os.path.exists(p):
        raise SystemExit(f'No existe {p}: copiá los clips y escribí clips_map.txt primero ("c3 <- archivo.mp4").')
    for line in open(p, encoding='utf-8', errors='replace'):
        m = re.match(r'\s*c(\d+)\s*<-\s*(.+?\.mp4)', line)
        if m: out[int(m.group(1))] = m.group(2).strip()
    return out


MAPS = {'MIRAGE', 'DUST2', 'DUST 2', 'INFERNO', 'NUKE', 'ANCIENT', 'ANUBIS', 'VERTIGO', 'OVERPASS', 'TRAIN', 'OFFICE', 'ITALY'}


def plan_info(project):
    """(clips usados, {clip: (título, subtítulo)}) leídos del plan, si hay plan."""
    p = os.path.join(project, 'plan.py')
    if not os.path.exists(p): return set(), {}
    try:
        spec = importlib.util.spec_from_file_location('plan_cat', p)
        cwd = os.getcwd(); os.chdir(project); sys.path.insert(0, project)
        m = importlib.util.module_from_spec(spec)
        with contextlib.redirect_stdout(io.StringIO()):
            spec.loader.exec_module(m)
        os.chdir(cwd)
        caps = {}
        for P in list(m.ACT1) + list(m.ACT2):
            if not P.get('cap'): continue
            c = P.get('clip') or (P['burst'][0][0] if P.get('burst') else None)
            if c: caps[c] = P['cap']
        return {s['clip'] for s in m.segments if s.get('clip')}, caps
    except Exception as e:
        print('  (no se pudo leer el plan para marcar los clips usados:', e, ')')
        return set(), {}


def cmd_scan(folder):
    db = load(); added = 0
    folder = os.path.abspath(folder)
    for f in sorted(os.listdir(folder)):
        if not f.lower().endswith('.mp4'): continue
        k = slug(f)
        if k in db: continue
        e = new_entry(f); e.update(probe(os.path.join(folder, f))); db[k] = e; added += 1
        print(f'  + {k}  {e.get("duration", "?")} s  {e.get("fps", "?")} fps  {e["era"]}')
    save(db)
    print(f'{added} clips nuevos; {len(db)} en el catálogo.')


def cmd_import(project):
    project = os.path.abspath(project); name = os.path.basename(project)
    db = load(); cm = clip_map(project)
    kf = json.load(open(os.path.join(project, 'kf.json')))
    shp = os.path.join(project, 'shots.json')
    sh = json.load(open(shp)) if os.path.exists(shp) else {}
    used, caps = plan_info(project); n = 0
    for c, f in cm.items():
        k = slug(f)
        e = db.setdefault(k, new_entry(f))
        if str(c) in kf:
            e['kills'] = kf[str(c)]; e['shots'] = sh.get(str(c)); e['verified'] = True; n += 1
        if c in used and name not in [u['project'] for u in e['used_in']]:
            e['used_in'].append(dict(project=name, clip=f'c{c}'))
        if c in caps:                     # el título de la play ya dice qué es: ACE/4K/clutch y arma o mapa
            big, small = caps[c][0], (caps[c][1] if len(caps[c]) > 1 else '') or ''
            tag = big.lower().split()[0]
            if tag not in e['tags']: e['tags'].append(tag)
            if small.upper() in MAPS: e['map'] = e['map'] or small.title()
            elif small: e['weapon'] = e['weapon'] or small
            if not e.get('rating'): e['rating'] = {'ace': 5, 'clutch': 5, 'casi': 4, '4k': 4}.get(tag, 3)
    save(db)
    print(f'Importados {n} clips verificados de {name}; {len(used)} marcados como usados en el edit.')
    missing = [slug(cm[c]) for c in cm if not db[slug(cm[c])].get('weapon') and db[slug(cm[c])]['era'] == 'cs2']
    if missing:
        print(f'Faltan arma/mapa/puntaje en {len(missing)} clips. Completalos con:  python engine/catalog.py set <nombre> weapon=AK-47 map=Mirage rating=4 tags=ace')


def cmd_prefill(project):
    project = os.path.abspath(project)
    db = load(); cm = clip_map(project)
    kfp, shp = os.path.join(project, 'kf.json'), os.path.join(project, 'shots.json')
    kf = json.load(open(kfp)) if os.path.exists(kfp) else {}
    sh = json.load(open(shp)) if os.path.exists(shp) else {}
    ver, todo, old = [], [], []
    for c, f in sorted(cm.items()):
        e = db.get(slug(f))
        if e and e['era'] == 'csgo': old.append(c); continue
        if e and e.get('verified') and e.get('kills') is not None:
            if str(c) not in kf: kf[str(c)] = e['kills']
            if e.get('shots') and str(c) not in sh: sh[str(c)] = e['shots']
            ver.append(c)
        else:
            todo.append(c)
    json.dump(kf, open(kfp, 'w'), indent=1); json.dump(sh, open(shp, 'w'), indent=1)
    json.dump(ver, open(os.path.join(project, 'verified.json'), 'w'))
    print(f'Verificados del catálogo (no hace falta revisarlos): {["c%d" % c for c in ver]}')
    print(f'A verificar a ojo: {["c%d" % c for c in todo]}')
    if old: print(f'CS:GO (marcalos DEPRECADO, no se usan): {["c%d" % c for c in old]}')


def find(db, q):
    m = re.match(r'c(\d+)@(.+)$', q)
    if m:
        cm = clip_map(os.path.join(ROOT, 'projects', m.group(2)))
        k = slug(cm[int(m.group(1))]); return [k] if k in db else []
    return [k for k in db if q.lower() in k.lower()]


def cmd_set(q, pairs):
    db = load(); ks = find(db, q)
    if len(ks) != 1: raise SystemExit(f'"{q}" coincide con {len(ks)} clips: {ks[:5]}')
    e = db[ks[0]]
    for p in pairs:
        key, val = p.split('=', 1)
        if key == 'rating': e[key] = int(val)
        elif key == 'tags': e[key] = [t.strip().lower() for t in val.split(',') if t.strip()]
        elif key == 'cam': e[key] = [int(x) for x in val.split(',')]
        elif key == 'verified': e[key] = val.lower() in ('si', 'sí', 'yes', 'true', '1')
        elif key in ('weapon', 'map', 'notes'): e[key] = val
        else: raise SystemExit(f'clave desconocida: {key}')
    save(db); print(ks[0], {k: e[k] for k in ('weapon', 'map', 'rating', 'tags', 'notes', 'cam', 'verified')})


def cmd_list(args):
    db = load(); rows = []
    def opt(name):
        return args[args.index(name) + 1].lower() if name in args else None
    minr = int(opt('--min-rating') or 0); tag = opt('--tag'); wp = opt('--weapon'); mp = opt('--map')
    for k, e in sorted(db.items(), key=lambda kv: (-kv[1].get('rating', 0), kv[0])):
        if e['era'] == 'csgo' and '--all' not in args: continue
        if '--unused' in args and e['used_in']: continue
        if e.get('rating', 0) < minr: continue
        if tag and tag not in e.get('tags', []): continue
        if wp and wp not in e.get('weapon', '').lower(): continue
        if mp and mp not in e.get('map', '').lower(): continue
        nk = len(e['kills']) if e.get('kills') is not None else '?'
        rows.append((e.get('rating', 0), nk, 'sí' if e.get('verified') else 'no', e.get('weapon', ''), e.get('map', ''),
                     ','.join(e.get('tags', [])), ','.join(u['project'] for u in e['used_in']), k[:48]))
    print(f'{"★":>2} {"K":>2} {"verif":5} {"arma":10} {"mapa":9} {"tags":18} {"usado en":28} clip')
    for r in rows:
        print(f'{r[0]:>2} {r[1]:>2} {r[2]:5} {r[3][:10]:10} {r[4][:9]:9} {r[5][:18]:18} {r[6][:28]:28} {r[7]}')
    print(f'{len(rows)} clips')


def cmd_show(q):
    db = load()
    for k in find(db, q): print(k, json.dumps(db[k], indent=1, ensure_ascii=False))


def main():
    try: sys.stdout.reconfigure(encoding='utf-8')
    except Exception: pass
    a = sys.argv[1:]
    if not a: print(__doc__); return
    c = a[0]
    if c == 'scan': cmd_scan(a[1] if len(a) > 1 else os.path.join(ROOT, 'entrada'))
    elif c == 'import': cmd_import(a[1])
    elif c == 'prefill': cmd_prefill(a[1])
    elif c == 'set': cmd_set(a[1], a[2:])
    elif c == 'list': cmd_list(a[1:])
    elif c == 'show': cmd_show(a[1])
    else: print(__doc__)


if __name__ == '__main__':
    main()
