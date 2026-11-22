"""Corre varios comandos del motor uno tras otro (una sola tarea para el editor web). Corta en el primero que falla.

    python engine/ui/chain.py '[["publish.py", "<proyecto>", "frames"], ["publish.py", "<proyecto>", "thumb"]]'
"""
import json, os, subprocess, sys

ENGINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for cmd in json.loads(sys.argv[1]):
    print('>', ' '.join(cmd[:1] + cmd[2:]), flush=True)
    r = subprocess.run([sys.executable, os.path.join(ENGINE, cmd[0]), *cmd[1:]])
    if r.returncode != 0:
        sys.exit(r.returncode)
