"""Smoke test — works on Windows / Linux / macOS.

    python _smoke_test.py
"""
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
p = subprocess.Popen(
    [sys.executable, str(ROOT / "start.py"), "--port", "8789", "--no-browser", "--no-update", "--build-only"],
    cwd=str(ROOT),
)
# --build-only exits; for a real serve test call server.py instead
p.wait(timeout=60)

p = subprocess.Popen(
    [sys.executable, str(ROOT / "server.py"), "--port", "8789", "--no-browser", "--no-update"],
    cwd=str(ROOT),
)
time.sleep(1.5)


def get(u):
    with urllib.request.urlopen(u, timeout=10) as r:
        return json.loads(r.read().decode())


try:
    st = get("http://127.0.0.1:8789/api/status")
    s = st["status"]
    print("STATUS n=", s["n_pulsars"], "B=", s["n_with_bname"], "ver", s["catalogue_version"], "next", s["next_due"])
    for name in ["J0826+2637", "B1913+16", "J1713+0747", "J1645-0317", "J2219+4754"]:
        d = get("http://127.0.0.1:8789/api/pulsar/" + name)
        it = d.get("item") or {}
        print(
            f"{name}: j={it.get('jname')} b={it.get('bname')} P0={it.get('p0')} "
            f"F1={it.get('f1')} DM={it.get('dm')} RM={it.get('rm')} W10={it.get('w10')} "
            f"AGE={it.get('age')} BSURF={it.get('bsurf')} EDOT={it.get('edot')} type={it.get('type')}"
        )
finally:
    p.terminate()
