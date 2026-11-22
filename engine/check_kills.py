"""Chequeo de visibilidad de kills (skill cs2-edit §3). Correr después de cada cambio del plan y antes de renderizar.

    python engine/check_kills.py projects/<nombre>            -> tabla + avisos (sale con código 1 si hay problemas)
    python engine/check_kills.py projects/<nombre> --times    -> además, tiempos de preview (disparo + 0.2 s) de las plays con título

Recorre TODAS las kills de kf.json/shots.json de cada clip usado en el plan y mide:
  pre  = segundos de la misma toma continua antes del disparo
  post = segundos de la misma toma continua después del disparo (incluye cámara lenta y cierre)
  trans = distancia del disparo a la transición más cercana
Mínimos (pisos):  normal 0.8/0.6 · primera de la play 1.2/0.6 · poco visible (hard=[i]) 1.2/1.2 ·
                  movimiento técnico (tech={i: inicio}) inicio+0.3 / 0.8 · última de la play 0.8 / 0.7 + media transición.
Ninguna kill a menos de (media transición + 0.15 s) del centro de un corte. Excepción: el corte seco del bang bang.
Avisa de CORTES QUE SOBRAN: cortes dentro de una play que saltean 1 s o menos del clip (van unidos).
Al final cruza kf.json con el killfeed (kf_conf.json de analyze_clips.py): avisa de kills del jugador que el killfeed
muestra y no están en kf.json (esas no aparecen en la tabla, así que nadie controla que se vean) y de kills de kf.json
sin entrada en el killfeed.
"""
import json, os, sys, importlib.util

ENGINE = os.path.dirname(os.path.abspath(__file__))
HALF = {'mega': 0.30, 'whip_lr': 0.13, 'whip_rl': 0.13, 'light': 0.17, 'zoom': 0.13, 'whip_short': 0.075,
        'light_short': 0.085, 'black_in': 0.70, 'cut': 0.0}
VIS = ('play', 'zoom_out', 'face_out', 'slowmo')


def load_plan(project):
    spec = importlib.util.spec_from_file_location('plan', os.path.join(project, 'plan.py'))
    cwd = os.getcwd(); os.chdir(project); sys.path.insert(0, project)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    os.chdir(cwd)
    return m


# Máximos de tiempo muerto (skill cs2-edit §3, "Tiempos muertos"). Son techos: más que esto, sin una razón en la ronda, se siente lento.
PRE_MAX = {'primera': 1.6, 'normal': 1.3, 'poco visible': 1.8}      # desde el inicio de la toma hasta la 1.ª kill de la toma
POST_MAX = {'normal': 0.9, 'poco visible': 1.6}                      # después de la última kill de la toma (+ media transición)
GAP_MAX = 3.5                                                        # entre dos kills de la misma toma continua (SKILL §3: con 3.5 s o menos va de corrido)
# Cortes que saltean casi nada (pedido del 20/11/2026, ACE de Mirage en paparazzi_v2 1:35): los cortes entre kills
# salteaban 0.45 y 0.62 s del clip y cada uno llevaba su transición; no ahorraban nada y cortaban la inmersión.
# Un corte dentro de una misma play tiene que saltear MÁS de MIN_SKIP del clip; si no, los tramos van unidos.
# Los cortes largos (ACE que saltean varios segundos de viaje, cortes para caer en un beat) no se tocan.
MIN_SKIP = 1.0
ROUND_PAD = 0.2                                                      # lo que suele sumar el redondeo al beat en un tramo nuevo
FRANTIC_K = 0.75                                                     # en tramos frenéticos (FRANTIC del plan) todo se achica


def dead_time(p, segs, plays, bound_at, chain):
    """Avisos de tiempo muerto: toma que arranca mucho antes de la acción, que sigue mirando la nada después de la
    última kill, o huecos largos entre kills dentro de una misma toma. Usa ctx={kill: (pre_max, post_max)} del plan
    para justificar excepciones (contexto que hace falta: humo, pared, rotación, enemigo que se acerca)."""
    out = []
    frantic = [(a - p.SONG_A0, b - p.SONG_A0) for a, b in getattr(p, 'FRANTIC', [])]
    seen = set()
    bursts = {(c, j) for P in list(p.ACT1) + list(p.ACT2) if 'burst' in P for c, j in P['burst']}
    for i, g in enumerate(segs):
        if g['kind'] in ('slowmo', 'face_out'): continue
        a, b = chain(i)
        if (a, b) in seen: continue
        seen.add((a, b))
        c = g['clip']; P = plays.get(c, {})
        if g.get('burst') and i > a: continue
        t0, t1 = segs[a]['o0'], segs[b]['o1']
        ks = []
        for j, s in enumerate(p.SHOTS.get(c, [])):
            for k in range(a, b + 1):
                h = segs[k]
                if h['kind'] != 'slowmo' and h['s0'] - 1e-3 <= s <= h['s1'] + 1e-3:
                    ks.append((h['o0'] + s - h['s0'], j)); break
        if not ks: continue
        ks.sort()
        hard = set(P.get('hard', [])); tech = P.get('tech', {}); ctx = P.get('ctx', {})
        if g.get('burst'):                      # ráfaga: solo importa cuánto tarda en llegar la 1.ª kill
            ks = [x for x in ks if (c, x[1]) in bursts or x[1] not in [jj for cc, jj in bursts if cc == c]][:1] or ks[:1]
        def k_(o): return FRANTIC_K if any(fa <= o <= fb for fa, fb in frantic) else 1.0
        # antes de la primera kill de la toma
        o, j = ks[0]
        if not (c == getattr(p, 'OPEN_CLIP', None) and segs[a]['kind'] == 'zoom_out'):
            kind = 'poco visible' if j in hard else ('primera' if j == 0 or g.get('burst') else 'normal')
            lim = PRE_MAX[kind] * k_(o)
            if j in tech: lim = max(lim, s_ - tech[j] + 0.5) if (s_ := p.SHOTS[c][j]) else lim
            if j in ctx: lim = ctx[j][0]
            if o - t0 > lim + 1e-3:
                out.append(f'c{c} toma en {t0:.2f}s: {o - t0:.2f}s antes de la 1.ª kill (máx {lim:.2f}) → arrancá más cerca de la acción')
        # huecos entre kills de la misma toma
        for (o1, j1), (o2, j2) in zip(ks, ks[1:]):
            lim = ctx.get(j2, (GAP_MAX, 0))[0] if j2 in ctx else GAP_MAX * k_(o2)
            # partir la toma solo sirve si el corte saltearía más de MIN_SKIP después de dejar los mínimos de las dos kills
            post_n = 1.2 if j1 in hard else 0.6
            pre_n = 1.2 if j2 in hard else 0.8
            if j2 in tech: pre_n = max(pre_n, p.SHOTS[c][j2] - tech[j2] + 0.3)
            if o2 - o1 - post_n - pre_n - ROUND_PAD <= MIN_SKIP: continue
            if o2 - o1 > lim + 1e-3:
                out.append(f'c{c} kills {j1}→{j2} (video {o1:.2f}→{o2:.2f}s): {o2 - o1:.2f}s sin kills en la misma toma → cortá el medio si no aporta')
        # después de la última kill de la toma
        if g.get('burst') or segs[b]['kind'] == 'face_out' or (b + 1 < len(segs) and segs[b + 1]['kind'] == 'face_out'):
            continue
        o, j = ks[-1]
        typ = bound_at(t1)
        if typ == 'black_in': continue          # el fundido a negro del interludio ya tapa la cola
        kind = 'poco visible' if j in hard else 'normal'
        lim = (POST_MAX[kind] + HALF.get(typ, 0.0)) * k_(o)
        if j in ctx: lim = ctx[j][1]
        # una reacción (grito, festejo) justo después de la kill que cierra la play justifica la cola: se deja oír
        for e in getattr(p, '_RX', {}).get(c, []):
            if e.get('j') == j and e.get('kind') in getattr(p, 'REACT_KINDS', ('grupal',)) and e['t0'] - e['kill'] <= 1.8 and j < len(p.SHOTS.get(c, [])):
                lim = max(lim, e['t0'] - p.SHOTS[c][j] + min(0.9, e['t1'] - e['t0']) + HALF.get(typ, 0.0))
        if t1 - o > lim + 1e-3:
            out.append(f'c{c} video {o:.2f}s: {t1 - o:.2f}s después de la última kill de la toma (máx {lim:.2f}) → cortá antes, que no quede mirando la nada')
    return out


def needless_cuts(p, plays):
    """Cortes dentro de una misma play que saltean MIN_SKIP o menos del clip: no ahorran tiempo y cortan la play con
    una transición. Esos tramos van unidos en uno continuo. Un corte así que sí hace falta (por ejemplo para que una
    kill caiga en un momento de SYNC) se justifica con keep_cut=[i] en la play (i = tramo que arranca después del corte)."""
    out = []; prev = None; si = 0
    for g in p.segments:
        if g['kind'] not in ('play', 'zoom_out'): prev = None; continue
        same = prev is not None and prev['clip'] == g['clip'] and prev['play'] == g['play'] and g['kind'] == 'play'
        si = si + 1 if same else 0
        if same and not g.get('burst') and not g.get('bang') and abs(prev['s1'] - g['s0']) > 0.03:
            c = g['clip']; P = plays.get(c, {})
            skip = g['s0'] - prev['s1']
            if skip <= MIN_SKIP + 1e-3 and si not in P.get('keep_cut', []):
                out.append(f'c{c} corte en video {g["o0"]:.2f}s (tramo {si}): saltea solo {skip:.2f}s del clip '
                           f'→ uní los tramos en uno continuo (o justificalo con keep_cut=[{si}])')
        prev = g
    return out


def killfeed_check(project, plays):
    """Cruce con el killfeed (kf_conf.json de analyze_clips.py): kills del jugador que el killfeed muestra y no están
    en kf.json (si faltan en kf.json, la tabla de arriba nunca las controla: era el error más repetido, plays de 4
    kills mostradas como 3) y kills de kf.json sin ninguna entrada propia en el killfeed."""
    cf, kp = os.path.join(project, 'kf_conf.json'), os.path.join(project, 'kf.json')
    if not os.path.exists(cf) or not os.path.exists(kp): return None
    conf = json.load(open(cf, encoding='utf-8')); kf = json.load(open(kp))
    out = []
    for c in sorted(plays):
        info = conf.get(str(c))
        if not info or info.get('sin_killfeed'): continue        # clip del catálogo (no se escaneó) o killfeed tapado
        mine = kf.get(str(c), [])
        for e in info['kills']:
            if not any(abs(e['t'] - k) <= KF_TOL for k in mine):
                tag = 'kill segura' if e['conf'] >= 0.6 else 'posible kill (dudosa)'
                out.append(f'c{c} {e["t"]:.2f}s: el killfeed muestra una {tag} del jugador que NO está en kf.json '
                           f'({e["why"]}) → si es real, agregala a kf.json y corré analyze_clips.py --shots')
        for k in mine:
            if not any(abs(e['t'] - k) <= KF_TOL for e in info['kills']):
                out.append(f'c{c} kill {k:.2f}s de kf.json: no hay entrada nueva del jugador en el killfeed cerca → confirmala a ojo')
    return out


KF_TOL = 0.7     # s: el killfeed aparece 0.1-0.45 s después del disparo; las listas a ojo a veces se corren un poco más


def main():
    try: sys.stdout.reconfigure(encoding='utf-8')
    except Exception: pass
    project = os.path.abspath(sys.argv[1])
    p = load_plan(project)
    rxp = os.path.join(project, 'reactions.json')
    p._RX = {int(k): v for k, v in json.load(open(rxp)).items()} if os.path.exists(rxp) and getattr(p, 'REACTIONS', True) is not False else {}
    segs = [s for s in p.segments if s['kind'] in VIS]
    allp = list(p.ACT1) + list(p.ACT2)
    plays = {P['clip']: P for P in allp if 'clip' in P}
    if getattr(p, 'OPEN_CLIP', None) is not None and p.OPEN_CLIP not in plays: plays[p.OPEN_CLIP] = {'clip': p.OPEN_CLIP}
    bursts = [P for P in allp if 'burst' in P]
    bounds = [(float(o), t) for o, t, _ in p.boundaries]
    # el corte que cierra cada tramo (para la media transición de la última kill)
    def bound_at(t):
        for o, typ in bounds:
            if abs(o - t) < 0.02: return typ
        return None

    def chain(i):
        """Índices de la toma continua que contiene al segmento i (mismo clip, tiempo de origen contiguo)."""
        a = b = i
        while a > 0 and segs[a - 1]['clip'] == segs[i]['clip'] and abs(segs[a - 1]['s1'] - segs[a]['s0']) < 0.03 \
                and abs(segs[a - 1]['o1'] - segs[a]['o0']) < 0.03:
            a -= 1
        while b < len(segs) - 1 and segs[b + 1]['clip'] == segs[i]['clip'] and abs(segs[b]['s1'] - segs[b + 1]['s0']) < 0.03 \
                and abs(segs[b]['o1'] - segs[b + 1]['o0']) < 0.03:
            b += 1
        return a, b

    rows, problems, previews = [], [], []
    for c in sorted(plays):
        P = plays[c]; shots = p.SHOTS.get(c, [])
        hard = set(P.get('hard', [])); tech = P.get('tech', {})
        bang = P.get('bang')
        n = len(shots)
        for j, s in enumerate(shots):
            hit = [i for i, g in enumerate(segs) if g['clip'] == c and g['kind'] != 'slowmo' and not g.get('burst') and g['s0'] - 1e-3 <= s <= g['s1'] + 1e-3]
            if not hit:
                if any(g.get('burst') and g['clip'] == c and g['s0'] - 1e-3 <= s <= g['s1'] + 1e-3 for g in segs):
                    continue                     # se ve en una ráfaga (se lista abajo)
                rows.append((c, j, s, None, None, None, None, 'FALTA')); problems.append(f'c{c} kill {j} ({s:.2f}s) NO aparece en el video')
                continue
            i = hit[0]; g = segs[i]; o = g['o0'] + (s - g['s0'])
            a, b = chain(i)
            pre = o - segs[a]['o0']
            post = segs[b]['o1'] - o
            if segs[b]['kind'] in ('face_out',) or (b + 1 < len(segs) and segs[b + 1]['kind'] == 'face_out'):
                post = max(post, 9.9)
            first, last = j == 0, j == n - 1
            need_pre, need_post, kind = 0.8, 0.6, 'normal'
            if first: need_pre, kind = 1.2, 'primera'
            if j in hard: need_pre, need_post, kind = max(need_pre, 1.2), 1.2, 'poco visible'
            if j in tech: need_pre, need_post, kind = max(need_pre, s - tech[j] + 0.3), 0.8, 'técnica'
            if last:
                typ = bound_at(segs[b]['o1'])
                need_post = max(need_post, 0.7 + HALF.get(typ, 0.0) if typ else need_post)
                kind += ' / última'
            in_bang = bool(bang) and j in (bang[2], bang[3])
            if in_bang:
                need_pre, need_post, kind = 0.0, 0.0, 'bang'
            dist = min([abs(o - bo) - HALF.get(bt, 0.0) for bo, bt in bounds if HALF.get(bt, 0.0) > 0] or [99])
            flag = []
            if pre + 1e-3 < need_pre: flag.append(f'pre {pre:.2f}<{need_pre:.2f}')
            if post + 1e-3 < need_post: flag.append(f'post {post:.2f}<{need_post:.2f}')
            if dist < 0.15 and not in_bang: flag.append(f'cerca de transición ({dist + 0.15:.2f}s del borde)')
            rows.append((c, j, s, o, pre, post, dist, kind if not flag else kind + ' → ' + '; '.join(flag)))
            if flag: problems.append(f'c{c} kill {j} (video {o:.2f}s): ' + '; '.join(flag))
            if P.get('cap'): previews.append(round(o + 0.2, 2))

    # ráfagas (excepción como el bang bang): cada kill tiene que aparecer, sin mínimos de pre/post
    for P in bursts:
        for c, j in P['burst']:
            s = p.SHOTS[c][j]
            hit = [g for g in segs if g.get('burst') and g['clip'] == c and g['s0'] - 1e-3 <= s <= g['s1'] + 1e-3]
            if not hit:
                rows.append((c, j, s, None, None, None, None, 'FALTA (ráfaga)')); problems.append(f'c{c} kill {j} de la ráfaga no aparece'); continue
            g = hit[0]; o = g['o0'] + (s - g['s0'])
            rows.append((c, j, s, o, s - g['s0'], g['s1'] - s, 0.0, 'ráfaga (excepción)'))
    dead = dead_time(p, segs, plays, bound_at, chain)
    print(f'{"clip":>5} {"k":>2} {"disparo":>8} {"video":>8} {"pre":>6} {"post":>6} {"trans":>6}  tipo')
    for c, j, s, o, pre, post, dist, k in rows:
        if o is None:
            print(f'{"c" + str(c):>5} {j:>2} {s:8.2f} {"—":>8} {"—":>6} {"—":>6} {"—":>6}  {k}')
        else:
            print(f'{"c" + str(c):>5} {j:>2} {s:8.2f} {o:8.2f} {pre:6.2f} {min(post, 9.9):6.2f} {dist + 0.15:6.2f}  {k}')
    print()
    # SYNC del plan (momentos de la canción con buen ritmo: drops, vuelta del bombo, estribillos; analyze_song.py los
    # propone): cada uno tiene que tener una kill exacta. En "Faster N Harder" el drop de 1:12 quedó sonando sin nada.
    for st in getattr(p, 'SYNC', []):
        o = st - p.SONG_A0
        d = min((abs(k - o) for k in p.kills), default=99.0)
        if d > 0.035:
            problems.append(f'SINCRONÍA: el momento {st:.2f}s de la canción (video {o:.2f}s) no tiene una kill exacta '
                            f'(la más cercana está a {d:.2f}s) → anclá una buena kill ahí con kill_at / kill_at_seg')
    if getattr(p, 'SYNC', None):
        print(f"Momentos de sincronía del plan: {len(p.SYNC)} ({', '.join(f'{x:.2f}' for x in p.SYNC)})")
    if problems:
        print(f'{len(problems)} problema(s):'); [print('  -', x) for x in problems]
    else:
        print('Tabla limpia: todas las kills aparecen y cumplen los mínimos.')
    if dead:
        print(f'\n{len(dead)} aviso(s) de TIEMPO MUERTO (recortá, o justificá con ctx={{kill: (pre_max, post_max)}} en el plan):')
        for x in dead: print('  -', x)
    else:
        print('Sin tiempos muertos: cada toma arranca cerca de la acción y corta después de la última kill.')
    cuts = needless_cuts(p, plays)
    if cuts:
        print(f'\n{len(cuts)} CORTE(S) QUE SOBRAN dentro de una play (saltean {MIN_SKIP:.1f}s o menos del clip: van en un tramo continuo):')
        for x in cuts: print('  -', x)
    else:
        print('Sin cortes que sobren: ningún corte dentro de una play saltea 1 s o menos.')
    # reacciones (engine/reactions.py): la del cierre de cada play se oye solo si el tramo la incluye
    kfp = os.path.join(project, 'kf.json')
    KF = {int(k): sorted(v) for k, v in json.load(open(kfp)).items()} if os.path.exists(kfp) else {}
    rx_lines = []
    for c, evs in sorted(p._RX.items()):
        sc = [g for g in p.segments if g['clip'] == c and g['kind'] in ('play', 'face_out', 'zoom_out')]
        shown = [k for k in KF.get(c, []) if any(g['s0'] - 0.3 <= k <= g['s1'] + 0.3 for g in sc)]
        if not sc or not shown: continue
        for e in evs:
            if abs(e['kill'] - max(shown)) > 0.05 or e.get('kind') not in getattr(p, 'REACT_KINDS', ('grupal',)): continue
            end = max(g['s1'] for g in sc)
            if end >= e['t0'] + 0.3: rx_lines.append(f"c{c} {e['kind']} en {e['t0']:.2f}s: entra ({min(end, e['t1']) - e['t0']:.2f}s se resaltan)")
            elif e['t0'] - e['kill'] <= 1.8:
                rx_lines.append(f"c{c} {e['kind']} en {e['t0']:.2f}s: queda AFUERA (el tramo termina en {end:.2f}s) → "
                                f"fin de tramo {min(e['t0'] + 0.9, e['t1']):.2f}s para que se oiga (la cola queda justificada)")
            else:
                rx_lines.append(f"c{c} {e['kind']} en {e['t0']:.2f}s: llega {e['t0'] - e['kill']:.1f}s después de la kill, demasiado tarde (se deja afuera)")
    if rx_lines:
        print('\nReacciones al cierre de las plays:'); [print('  -', x) for x in rx_lines]
    kfc = killfeed_check(project, plays)
    if kfc is None:
        print('\n(Sin kf_conf.json: corré analyze_clips.py para cruzar kf.json con el killfeed.)')
    elif kfc:
        print(f'\n{len(kfc)} aviso(s) del KILLFEED (la lista de kills de los clips usados no coincide con lo que muestra el killfeed):')
        for x in kfc: print('  -', x)
    else:
        print('\nKillfeed: las kills de kf.json coinciden con las entradas del jugador en el killfeed.')
    if '--times' in sys.argv:
        print('\nPreviews (un cuadro por kill de las plays con título):'); print(','.join(f'{t:.2f}' for t in previews))
    sys.exit(1 if problems else 0)


if __name__ == '__main__':
    main()
