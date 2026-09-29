#!/usr/bin/env python3
"""Cross-platform launcher for the ATNF Pulsar Query Center.

Works on Windows / Linux / macOS:

    python start.py              # build DB if needed, serve, open browser
    python start.py --port 8790
    python start.py --no-browser
    python start.py --no-update
    python start.py --help

Also runnable as:
    ./start.sh                   # Linux / macOS
    start.bat                    # Windows
"""
from __future__ import annotations

import argparse
import os
import sys
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="Start ATNF Pulsar Query Center (cross-platform)",
    )
    ap.add_argument("--host", default=None, help="bind host (default 127.0.0.1)")
    ap.add_argument("--port", type=int, default=None, help="bind port (default 8787)")
    ap.add_argument(
        "--no-update",
        action="store_true",
        help="do not auto-update ATNF cache on start",
    )
    ap.add_argument(
        "--no-browser",
        action="store_true",
        help="do not open the web page automatically",
    )
    ap.add_argument(
        "--build-only",
        action="store_true",
        help="only ensure the local database, then exit",
    )
    return ap.parse_args()


def main() -> int:
    args = parse_args()

    # Make sure we run from the package root (portable: copy this folder anywhere)
    os.chdir(ROOT)

    if not (ROOT / "server.py").is_file() or not (ROOT / "update_db.py").is_file():
        print(f"error: incomplete package under {ROOT}", file=sys.stderr)
        return 1

    import server as srv

    cfg = srv.load_config()
    print(f"[start] package root: {ROOT}")
    print("[start] ensuring local database ...")
    try:
        srv.ensure_db(cfg)
    except SystemExit:
        return 1
    except Exception as ex:
        print(f"[start] database build failed: {ex}", file=sys.stderr)
        return 1

    meta = srv.load_meta()
    n = 0
    try:
        import sqlite3

        if srv.SQLITE.exists():
            con = sqlite3.connect(srv.SQLITE)
            n = con.execute("SELECT COUNT(*) FROM pulsars").fetchone()[0]
            con.close()
    except Exception:
        pass
    print(f"[start] database ready: {n} pulsars")

    if args.build_only:
        print("[start] --build-only: done")
        return 0

    if not args.no_update:
        try:
            srv.maybe_auto_update(cfg, meta, True)
        except Exception as ex:
            print(f"[start] auto-update check skipped: {ex}")

    host = args.host or cfg.get("server_host") or "127.0.0.1"
    port = args.port or int(cfg.get("server_port") or 8787)
    url = f"http://{host}:{port}/"

    # Reuse server.main; always suppress its own browser open (we handle it here)
    argv = ["server.py", "--no-browser"]
    if args.host:
        argv += ["--host", args.host]
    if args.port:
        argv += ["--port", str(args.port)]
    if args.no_update:
        argv += ["--no-update"]

    print(f"[start] Pulsar Query Center  ->  {url}")
    if not args.no_browser:
        import threading

        def _open() -> None:
            try:
                webbrowser.open(url)
            except Exception:
                pass

        threading.Timer(1.0, _open).start()

    old = sys.argv
    try:
        sys.argv = argv
        return srv.main()
    finally:
        sys.argv = old


if __name__ == "__main__":
    raise SystemExit(main())
