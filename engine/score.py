"""Puntaje automático de una play (0-100), para ordenar el catálogo y elegir plays sin mirarlas una por una.

No reemplaza al `rating` (1-5) puesto a mano: ese no se toca. El puntaje se calcula cada vez a partir de lo que el
catálogo ya sabe del clip, así que nunca queda viejo:

  cantidad   cuántas kills tiene la play (lo que más pesa: un ACE vale más que un 2K)
  ritmo      qué tan seguidas son (kills a menos de ~1.5 s suman todo; a más de GAP_MAX, nada)
  tipo       headshots, kills a través de pared o de humo (kill_types, leído de los íconos del killfeed)
  reacción   festejo después de la play (reactions.json): grupal > grito > reacción
  muerto     tiempo muerto entre kills por encima de GAP_MAX (resta)

    python engine/score.py                 -> los 20 mejores del catálogo y la relación con los rating a mano
    python engine/score.py <parte_nombre>  -> el desglose de un clip
    python engine/score.py --fill          -> completa kill_types y reaction de los clips verificados (lee el killfeed
                                              guardado en catalog/kf_cache/ y los reactions.json de los proyectos)
    python engine/catalog.py list --sort score
"""
import os, sys, json

ENGINE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(ENGINE)
sys.path.insert(0, ENGINE)

GAP_MAX = 3.5                    # s entre kills de una misma toma (el mismo límite que check_kills.py)
QTY = {0: 0, 1: 12, 2: 26, 3: 40, 4: 52, 5: 62}          # puntos por cantidad de kills (5 o más = 62)
W_PACE, W_TYPE, W_REACT, W_DEAD = 14, 10, 14, 15         # máximo de cada parte


def play(kills):
    """La racha más larga de kills seguidas del clip (sin huecos de más de 3 x GAP_MAX): un clip largo con dos rondas
    no es una play de 8 kills."""
    best, cur = [], []
    for k in sorted(kills):
        cur = cur + [k] if cur and k - cur[-1] <= 3 * GAP_MAX else [k]
        if len(cur) > len(best): best = cur
    return best


def score(e):
    """Puntaje de una entrada del catálogo: dict(score, n, cantidad, ritmo, tipo, reaccion, muerto)."""
    kills = e.get('kills') or []
    pl = play(kills); n = len(pl)
    gaps = [b - a for a, b in zip(pl, pl[1:])]
    qty = QTY[min(n, 5)]
    pace = W_PACE * sum(max(0.0, min(1.0, (GAP_MAX - g) / (GAP_MAX - 1.5))) for g in gaps) / len(gaps) if gaps else 0.0
    dead = min(W_DEAD, 1.5 * sum(max(0.0, g - GAP_MAX) for g in gaps))
    tipo = 0.0
    kt = e.get('kill_types')
    if kt and len(kt) == len(kills) and n:
        mine = [kt[kills.index(k)] for k in pl]
        hs = sum('headshot' in t for t in mine) / n
        rare = sum(('pared' in t) + ('humo' in t) for t in mine)
        tipo = min(W_TYPE, 6 * hs + 2.5 * rare)
    r = e.get('reaction') or {}
    react = W_REACT if r.get('group') else {'grito': 9, 'reaccion': 5}.get(r.get('loud'), 0)
    total = max(0.0, min(100.0, qty + pace + tipo + react - dead))
    return dict(score=round(total), n=n, cantidad=qty, ritmo=round(pace, 1), tipo=round(tipo, 1), reaccion=react, muerto=round(dead, 1))


def best_reaction(rs):
    """De la lista de reacciones de un clip (reactions.json), la que más vale: dict(group, loud, db) o None."""
    if not rs: return None
    r = max(rs, key=lambda r: (bool(r.get('group')), r.get('loud') == 'grito', r.get('db', 0)))
    return dict(group=bool(r.get('group')), loud=r.get('loud'), db=r.get('db'))


def types_for(kills, events, tol=0.35):
    """Tipo de cada kill verificada: el del evento del killfeed más cercano (a ±tol s), [] si no hay ninguno."""
    out = []
    for k in kills:
        near = [ev for ev in events if abs(ev['t'] - k) <= tol]
        out.append(list(min(near, key=lambda ev: abs(ev['t'] - k)).get('tipo') or []) if near else [])
    return out


def fill():
    """Completa kill_types y reaction en los clips verificados del catálogo. No toca nada más."""
    import re, pickle
    import catalog as C, eval_kills as E, killfeed as K
    db = C.load(); cache = os.path.join(ROOT, 'catalog', 'kf_cache'); os.makedirs(cache, exist_ok=True)
    nt = 0
    for d in E.dataset(ROOT):
        fr = E.cached_scan((d['slug'], d['video'], cache))[1]
        trs = K._live(fr)
        evs = [dict(t=t['start'] / fr['fps'], tipo=sorted(K.kill_type(t['sig']))) for t in trs if t['sig'] is not None]
        db[d['slug']]['kill_types'] = types_for(db[d['slug']]['kills'], evs); nt += 1
    nr = 0
    pj = os.path.join(ROOT, 'projects')
    for p in sorted(os.listdir(pj)):
        rf, cm = os.path.join(pj, p, 'reactions.json'), os.path.join(pj, p, 'clips_map.txt')
        if not (os.path.exists(rf) and os.path.exists(cm)): continue
        rs = json.load(open(rf, encoding='utf-8'))
        for line in open(cm, encoding='utf-8', errors='replace'):
            m = re.match(r'\s*c(\d+)\s*<-\s*(.+?\.mp4)', line)
            k = C.slug(m.group(2)) if m else None
            if k in db and m.group(1) in rs:
                b = best_reaction(rs[m.group(1)])
                old = db[k].get('reaction')
                if b and (not old or (b['group'], b['loud'] == 'grito') > (old.get('group'), old.get('loud') == 'grito')):
                    db[k]['reaction'] = b; nr += 1
    C.save(db)
    print(f'kill_types en {nt} clips verificados; reaction en {nr} (de los reactions.json de los proyectos).')


def main():
    try: sys.stdout.reconfigure(encoding='utf-8')
    except Exception: pass
    import catalog as C
    a = sys.argv[1:]
    if a[:1] == ['--fill']: return fill()
    db = C.load()
    if a:
        for k in C.find(db, a[0]): print(k, score(db[k]), '· rating a mano:', db[k].get('rating') or '-')
        return
    rows = sorted(((score(e), k, e) for k, e in db.items() if e.get('era') != 'csgo' and e.get('kills')), key=lambda r: -r[0]['score'])
    print(f'{"pts":>3} {"K":>2} {"cant":>4} {"ritmo":>5} {"tipo":>4} {"reac":>4} {"muerto":>6} {"★":>2}  clip')
    for s, k, e in rows[:20]:
        print(f'{s["score"]:>3} {s["n"]:>2} {s["cantidad"]:>4} {s["ritmo"]:>5} {s["tipo"]:>4} {s["reaccion"]:>4} {s["muerto"]:>6} {e.get("rating") or "-":>2}  {k[:52]}')
    rated = [(s['score'], e['rating']) for s, k, e in rows if e.get('rating')]
    if len(rated) >= 5:
        from scipy.stats import spearmanr
        by = {}
        for sc, r in rated: by.setdefault(r, []).append(sc)
        print(f'\n{len(rated)} clips con rating a mano. Puntaje medio por rating: '
              + ', '.join(f'{r}★ {sum(v) / len(v):.0f}' for r, v in sorted(by.items()))
              + f'. Correlación (Spearman): {spearmanr([x for x, _ in rated], [y for _, y in rated])[0]:.2f}')


if __name__ == '__main__':
    main()
