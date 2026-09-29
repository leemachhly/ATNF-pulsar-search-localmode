#!/usr/bin/env python3
"""Local interactive ATNF pulsar query center (stdlib HTTP server).

  python server.py              # build DB if needed, then serve
  python server.py --port 8787
  python server.py --no-update  # skip auto-update check
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
CFG_PATH = BASE / "config.json"
SQLITE = DATA / "pulsars.sqlite"
META = DATA / "meta.json"
STATIC = BASE / "static"


def load_config() -> dict:
    return json.loads(CFG_PATH.read_text(encoding="utf-8"))


def load_meta() -> dict:
    if META.exists():
        try:
            return json.loads(META.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_config(cfg: dict) -> None:
    CFG_PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")


def get_db() -> sqlite3.Connection:
    con = sqlite3.connect(SQLITE)
    con.row_factory = sqlite3.Row
    return con


def humanize(val) -> str:
    if val is None:
        return ""
    if isinstance(val, float):
        if val == 0:
            return "0"
        av = abs(val)
        if av >= 1e6 or av < 1e-3:
            return f"{val:.6g}"
        if av >= 100:
            return f"{val:.4g}"
        return f"{val:.6g}"
    return str(val)


ROW_FIELDS = [
    "jname", "bname", "p0", "f0", "f1", "dm", "rm",
    "raj", "decj", "s1400", "w50", "w10",
    "pb", "ecc", "age", "bsurf", "edot", "type",
]


def row_to_dict(r: sqlite3.Row, detail: bool = False) -> dict:
    d = {k: r[k] for k in r.keys()}
    out = {
        "jname": d.get("jname"),
        "bname": d.get("bname"),
        "p0": d.get("p0"),
        "p1": d.get("p1"),
        "f0": d.get("f0"),
        "f1": d.get("f1"),
        "f2": d.get("f2"),
        "dm": d.get("dm"),
        "dm1": d.get("dm1"),
        "rm": d.get("rm"),
        "rm1": d.get("rm1"),
        "raj": d.get("raj"),
        "decj": d.get("decj"),
        "gl": d.get("gl"),
        "gb": d.get("gb"),
        "pmra": d.get("pmra"),
        "pmdec": d.get("pmdec"),
        "px": d.get("px"),
        "s400": d.get("s400"),
        "s1400": d.get("s1400"),
        "s3000": d.get("s3000"),
        "w50": d.get("w50"),
        "w10": d.get("w10"),
        "scat": d.get("scat"),
        "pb": d.get("pb"),
        "a1": d.get("a1"),
        "ecc": d.get("ecc"),
        "age": d.get("age"),
        "bsurf": d.get("bsurf"),
        "blc": d.get("blc"),
        "edot": d.get("edot"),
        "type": d.get("type"),
        "survey": d.get("survey"),
        "assoc": d.get("assoc"),
    }
    if detail:
        try:
            out["fields"] = json.loads(d.get("fields_json") or "{}")
        except Exception:
            out["fields"] = {}
        try:
            out["raw"] = json.loads(d.get("raw_fields") or "{}")
        except Exception:
            out["raw"] = {}
        try:
            out["extra"] = json.loads(d.get("extra") or "{}")
        except Exception:
            out["extra"] = {}
    return out


def search_pulsars(q: str, limit: int = 50, field: str = "") -> list[dict]:
    con = get_db()
    q = (q or "").strip()
    limit = max(1, min(int(limit), 500))
    try:
        if not q:
            rows = con.execute(
                "SELECT * FROM pulsars ORDER BY jname LIMIT ?", (limit,)
            ).fetchall()
            return [row_to_dict(r) for r in rows]

        like = f"%{q}%"
        # normalize B/J search
        qn = q.upper().replace("PSR", "").strip()
        if field == "bname":
            rows = con.execute(
                "SELECT * FROM pulsars WHERE bname LIKE ? ORDER BY jname LIMIT ?",
                (like, limit),
            ).fetchall()
        elif field == "jname":
            rows = con.execute(
                "SELECT * FROM pulsars WHERE jname LIKE ? ORDER BY jname LIMIT ?",
                (like, limit),
            ).fetchall()
        elif field == "dm":
            try:
                lo, hi = (q.split(",") + [""])[:2]
                if hi:
                    rows = con.execute(
                        "SELECT * FROM pulsars WHERE dm >= ? AND dm <= ? ORDER BY jname LIMIT ?",
                        (float(lo), float(hi), limit),
                    ).fetchall()
                else:
                    rows = con.execute(
                        "SELECT * FROM pulsars WHERE dm >= ? ORDER BY jname LIMIT ?",
                        (float(lo), limit),
                    ).fetchall()
            except Exception:
                rows = []
        else:
            # free text: jname, bname, type, assoc
            rows = con.execute(
                """
                SELECT * FROM pulsars
                WHERE jname LIKE ? COLLATE NOCASE
                   OR bname LIKE ? COLLATE NOCASE
                   OR IFNULL(type,'') LIKE ? COLLATE NOCASE
                   OR IFNULL(assoc,'') LIKE ? COLLATE NOCASE
                ORDER BY
                  CASE WHEN jname = ? THEN 0
                       WHEN bname = ? THEN 1
                       WHEN jname LIKE ? THEN 2
                       ELSE 3 END,
                  jname
                LIMIT ?
                """,
                (like, like, like, like, qn, qn, f"{qn}%", limit),
            ).fetchall()
        return [row_to_dict(r) for r in rows]
    finally:
        con.close()


def get_pulsar(name: str) -> dict | None:
    con = get_db()
    try:
        n = name.strip()
        r = con.execute(
            "SELECT * FROM pulsars WHERE jname = ? COLLATE NOCASE OR bname = ? COLLATE NOCASE",
            (n, n),
        ).fetchone()
        if not r:
            like = f"%{n}%"
            r = con.execute(
                "SELECT * FROM pulsars WHERE jname LIKE ? OR bname LIKE ? LIMIT 1",
                (like, like),
            ).fetchone()
        return row_to_dict(r, detail=True) if r else None
    finally:
        con.close()


def db_stats() -> dict:
    meta = load_meta()
    con = get_db()
    try:
        n = con.execute("SELECT COUNT(*) FROM pulsars").fetchone()[0]
        n_b = con.execute(
            "SELECT COUNT(*) FROM pulsars WHERE bname IS NOT NULL AND bname != ''"
        ).fetchone()[0]
    finally:
        con.close()
    interval = float(meta.get("update_interval_days") or 14)
    last = meta.get("last_download_ts") or meta.get("last_build_ts") or 0
    next_due = (last + interval * 86400) if last else 0
    return {
        "n_pulsars": n,
        "n_with_bname": n_b,
        "catalogue_version": meta.get("catalogue_version"),
        "last_update_ts": last,
        "last_update": time.strftime("%Y-%m-%d %H:%M", time.localtime(last)) if last else None,
        "interval_days": interval,
        "next_due_ts": next_due,
        "next_due": time.strftime("%Y-%m-%d", time.localtime(next_due)) if next_due else None,
        "update_overdue": bool(next_due and time.time() > next_due),
        "config": {
            "display_fields": load_config().get("display_fields"),
            "core_fields": load_config().get("core_fields"),
            "field_labels": load_config().get("field_labels"),
        },
    }


_update_lock = threading.Lock()
_update_status = {"running": False, "last_result": None, "last_ts": 0}


def run_update() -> dict:
    if not _update_lock.acquire(blocking=False):
        return {"ok": False, "error": "update already running"}
    _update_status["running"] = True
    try:
        print("[update] running update_db.py ...")
        r = subprocess.run(
            [sys.executable, str(BASE / "update_db.py")],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        ok = r.returncode == 0
        _update_status["last_result"] = {
            "ok": ok,
            "returncode": r.returncode,
            "stdout": (r.stdout or "")[-2000:],
            "stderr": (r.stderr or "")[-2000:],
            "ts": time.time(),
        }
        _update_status["last_ts"] = time.time()
        return _update_status["last_result"]
    finally:
        _update_status["running"] = False
        _update_lock.release()


def maybe_auto_update(cfg: dict, meta: dict, enable: bool) -> None:
    if not enable:
        return
    interval = float(cfg.get("update_interval_days", 14)) * 86400
    last = float(meta.get("last_download_ts") or 0)
    if last and (time.time() - last) < interval:
        return
    print("[auto-update] cache stale, starting background update ...")
    threading.Thread(target=run_update, daemon=True).start()


class Handler(BaseHTTPRequestHandler):
    server_version = "PulsarCenter/1.0"

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _send(self, code: int, body: bytes, ctype: str = "application/json; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code: int = 200):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"))

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path in ("/", "/index.html"):
            html = (STATIC / "index.html").read_bytes()
            self._send(200, html, "text/html; charset=utf-8")
            return
        if path.startswith("/static/"):
            rel = path[len("/static/") :]
            fp = (STATIC / rel).resolve()
            if not str(fp).startswith(str(STATIC.resolve())) or not fp.is_file():
                self._send(404, b"not found", "text/plain")
                return
            ctype = "application/octet-stream"
            if fp.suffix == ".css":
                ctype = "text/css; charset=utf-8"
            elif fp.suffix == ".js":
                ctype = "application/javascript; charset=utf-8"
            elif fp.suffix == ".html":
                ctype = "text/html; charset=utf-8"
            self._send(200, fp.read_bytes(), ctype)
            return

        if path == "/api/status":
            self._json({"ok": True, "status": db_stats(), "update": {
                "running": _update_status["running"],
                "last_result": _update_status["last_result"],
            }})
            return

        if path == "/api/search":
            q = (qs.get("q") or [""])[0]
            limit = int((qs.get("limit") or ["50"])[0])
            field = (qs.get("field") or [""])[0]
            try:
                rows = search_pulsars(q, limit=limit, field=field)
                self._json({"ok": True, "q": q, "n": len(rows), "items": rows})
            except Exception as ex:
                self._json({"ok": False, "error": str(ex)}, 500)
            return

        if path.startswith("/api/pulsar/"):
            name = unquote(path[len("/api/pulsar/") :])
            rec = get_pulsar(name)
            if not rec:
                self._json({"ok": False, "error": "not found"}, 404)
            else:
                self._json({"ok": True, "item": rec})
            return

        if path == "/api/fields":
            cfg = load_config()
            self._json({
                "ok": True,
                "core_fields": cfg.get("core_fields"),
                "display_fields": cfg.get("display_fields"),
                "field_labels": cfg.get("field_labels"),
            })
            return

        self._json({"ok": False, "error": "unknown path"}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(body.decode("utf-8") or "{}")
        except Exception:
            payload = {}

        if path == "/api/update":
            if _update_status["running"]:
                self._json({"ok": False, "error": "already running"})
                return
            threading.Thread(target=run_update, daemon=True).start()
            self._json({"ok": True, "started": True})
            return

        if path == "/api/config":
            cfg = load_config()
            for key in ("display_fields", "core_fields", "field_labels", "update_interval_days"):
                if key in payload:
                    cfg[key] = payload[key]
            save_config(cfg)
            self._json({"ok": True, "config": cfg})
            return

        if path == "/api/field":
            # add one extra field to core_fields
            name = (payload.get("name") or "").strip().upper()
            if not name or not re.fullmatch(r"[A-Z][A-Z0-9_]*", name):
                self._json({"ok": False, "error": "invalid field name"}, 400)
                return
            cfg = load_config()
            core = cfg.setdefault("core_fields", [])
            if name not in core:
                core.append(name)
            labels = cfg.setdefault("field_labels", {})
            labels.setdefault(name, name)
            if payload.get("display") and name not in cfg.setdefault("display_fields", []):
                cfg["display_fields"].append(name)
            save_config(cfg)
            self._json({"ok": True, "core_fields": core, "display_fields": cfg["display_fields"]})
            return

        self._json({"ok": False, "error": "unknown path"}, 404)


def ensure_db(cfg: dict) -> None:
    if SQLITE.exists() and SQLITE.stat().st_size > 1000:
        return
    print("database missing, building from psrcat.db ...")
    if not (DATA / "psrcat.db").exists():
        print("cached psrcat.db missing, downloading ...")
    r = subprocess.run([sys.executable, str(BASE / "update_db.py")], cwd=str(BASE))
    if r.returncode != 0 or not SQLITE.exists():
        raise SystemExit("failed to build pulsars.sqlite")


def main() -> int:
    global Handler
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default=None)
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--no-update", action="store_true", help="disable auto-update check")
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    cfg = load_config()
    ensure_db(cfg)
    meta = load_meta()
    if not args.no_update:
        maybe_auto_update(cfg, meta, True)

    host = args.host or cfg.get("server_host") or "127.0.0.1"
    port = args.port or int(cfg.get("server_port") or 8787)
    url = f"http://{host}:{port}/"
    print(f"Pulsar Query Center  ->  {url}")
    print(f"DB: {SQLITE}  ({db_stats()['n_pulsars']} pulsars)")
    if not args.no_browser:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()

    httpd = ThreadingHTTPServer((host, port), Handler)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
