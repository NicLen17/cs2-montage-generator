"""Palabras de la canción con su tiempo exacto (opcional, con faster-whisper).

    python engine/words.py projects/<nombre>                 -> projects/<nombre>/words.json
    python engine/words.py projects/<nombre> --model small   (tiny, base, small, medium; por defecto base)

Sirve SOLO para sincronizar: saber en qué instante cae cada palabra permite poner una kill en un golpe de voz aislado
(un "stop", un grito) o repartir una ráfaga en sílabas repetidas. El motor nunca escribe la letra en pantalla.

Usa la voz ya separada por Demucs (stems/htdemucs/song/vocals.wav) si existe; si no, la canción entera (peor). Guarda:
    words.json = {"model": ..., "words": [{"t0", "t1", "w", "p"}], "accents": [{"t", "w", "gap", "why"}]}
"accents" son los golpes de voz que vale la pena mirar: una palabra corta después de un silencio de la voz, o la misma
sílaba repetida varias veces seguidas. Son candidatos: confirmalos a oído antes de anclar una kill.

Si faster-whisper no está instalado (pip install faster-whisper) avisa y sale sin error: el resto del flujo no lo necesita.
"""
import json, os, sys


def vocals_path(project):
    for p in (os.path.join(project, 'stems', 'htdemucs', 'song', 'vocals.wav'),
              os.path.join(project, 'stems', 'vocals.wav')):
        if os.path.exists(p): return p, True
    for f in sorted(os.listdir(project)):
        if f.lower().endswith(('.mp3', '.wav', '.m4a', '.flac')) and f.lower().startswith('song'):
            return os.path.join(project, f), False
    raise SystemExit('No hay canción en el proyecto (song.mp3)')


def accents(words, min_gap=0.6, max_len=0.45):
    """Golpes de voz para sincronizar, a partir de las palabras con tiempo."""
    out = []
    for i, w in enumerate(words):
        gap = w['t0'] - words[i - 1]['t1'] if i else w['t0']
        nxt = words[i + 1]['t0'] - w['t1'] if i + 1 < len(words) else 9.0
        if gap >= min_gap and (w['t1'] - w['t0']) <= max_len and nxt >= 0.25:
            out.append(dict(t=round(w['t0'], 3), w=w['w'], gap=round(gap, 2), why='palabra aislada'))
    # la misma palabra (o sílaba) 3 o más veces seguidas, a ritmo parejo: candidata a ráfaga
    i = 0
    while i < len(words):
        j = i
        while j + 1 < len(words) and _norm(words[j + 1]['w']) == _norm(words[i]['w']) and words[j + 1]['t0'] - words[j]['t0'] < 0.8:
            j += 1
        if j - i >= 2:
            out.append(dict(t=round(words[i]['t0'], 3), w=words[i]['w'], gap=0.0, why=f'repetida {j - i + 1} veces',
                            times=[round(words[k]['t0'], 3) for k in range(i, j + 1)]))
        i = j + 1
    return sorted(out, key=lambda a: a['t'])


def _norm(w):
    return ''.join(ch for ch in w.lower() if ch.isalnum())


def transcribe(project, model='base'):
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return None
    src, clean = vocals_path(project)
    import subprocess
    import numpy as np
    # el audio se decodifica con ffmpeg (como el resto del motor), no con la librería de video que trae faster-whisper
    audio = np.frombuffer(subprocess.run(['ffmpeg', '-v', 'error', '-i', src, '-ac', '1', '-ar', '16000', '-f', 'f32le', '-'],
                                         capture_output=True).stdout, np.float32)
    m = WhisperModel(model, device='auto', compute_type='auto')
    segs, info = m.transcribe(audio, word_timestamps=True, vad_filter=clean, condition_on_previous_text=False)
    words = []
    for s in segs:
        for w in (s.words or []):
            t = w.word.strip()
            if t: words.append(dict(t0=round(float(w.start), 3), t1=round(float(w.end), 3), w=t, p=round(float(w.probability), 2)))
    return dict(model=model, language=info.language, source=os.path.basename(src), separated=clean, words=words,
                accents=accents([w for w in words if w['p'] >= 0.4]))


def main():
    try: sys.stdout.reconfigure(encoding='utf-8')
    except Exception: pass
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if not args: raise SystemExit(__doc__)
    project = os.path.abspath(args[0])
    model = sys.argv[sys.argv.index('--model') + 1] if '--model' in sys.argv else 'base'
    data = transcribe(project, model)
    if data is None:
        print('faster-whisper no está instalado: se saltea (opcional). Para tenerlo: pip install faster-whisper')
        return 0
    out = os.path.join(project, 'words.json')
    json.dump(data, open(out, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    print(f"{len(data['words'])} palabras ({data['language']}, voz {'separada' if data['separated'] else 'sin separar'}) -> {out}")
    print('Golpes de voz para mirar (tiempo de canción; confirmá a oído antes de anclar una kill):')
    for a in data['accents']:
        print(f"  {a['t']:7.2f}s  {a['why']}" + (f" (silencio previo {a['gap']:.2f}s)" if a['gap'] else '')
              + (f"  en {', '.join(f'{x:.2f}' for x in a['times'])}" if a.get('times') else ''))
    return 0


if __name__ == '__main__':
    sys.exit(main())
