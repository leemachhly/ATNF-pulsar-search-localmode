#!/usr/bin/env python3
"""Download ATNF psrcat database and load it into local SQLite.

Usage:
  python update_db.py            # download (if needed) + rebuild SQLite
  python update_db.py --offline  # rebuild from existing data/psrcat.db only
  python update_db.py --force    # re-download even if cache is fresh
"""
from __future__ import annotations

import argparse
import io
import json
import re
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
CFG_PATH = BASE / "config.json"
RAW_DB = DATA / "psrcat.db"
SQLITE = DATA / "pulsars.sqlite"
META = DATA / "meta.json"
PKG_CACHE = DATA / "psrcat_pkg.tar.gz"

UA = "Mozilla/5.0 (compatible; mimocode-pulsar-center/1.0)"


def load_config() -> dict:
    return json.loads(CFG_PATH.read_text(encoding="utf-8"))


def save_meta(meta: dict) -> None:
    META.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")


def load_meta() -> dict:
    if META.exists():
        try:
            return json.loads(META.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def curl_bytes(url: str, timeout: int = 180) -> bytes:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except Exception:
        # fallback to curl (helps on some Windows / proxy setups)
        r = subprocess.run(
            ["curl.exe", "-sS", "-L", "--max-time", str(timeout), "-A", UA, url],
            capture_output=True,
        )
        if r.returncode != 0:
            raise RuntimeError(f"download failed: {url}: {r.stderr[:200]!r}")
        return r.stdout


def download_psrcat_db(cfg: dict, force: bool = False) -> Path:
    DATA.mkdir(parents=True, exist_ok=True)
    meta = load_meta()
    interval = float(cfg.get("update_interval_days", 14)) * 86400
    last = float(meta.get("last_download_ts") or 0)
    if RAW_DB.exists() and not force and (time.time() - last) < interval:
        print(f"cache fresh ({RAW_DB.stat().st_size} bytes), skip download")
        return RAW_DB

    urls = [cfg.get("atnf_package_url"), cfg.get("atnf_package_fallback_url")]
    urls = [u for u in urls if u]
    blob = None
    last_err = None
    for url in urls:
        try:
            print(f"downloading {url} ...")
            blob = curl_bytes(url, timeout=180)
            if blob[:2] == b"\x1f\x8b" or blob[:26].startswith(b"psrcat") or len(blob) > 100_000:
                break
            # HTML error page
            if blob.lstrip()[:1] == b"<":
                raise RuntimeError("got HTML, not tarball")
        except Exception as ex:
            last_err = ex
            print(f"  fail: {ex}")
            blob = None
    if not blob:
        raise RuntimeError(f"could not download psrcat package: {last_err}")

    PKG_CACHE.write_bytes(blob)
    member = cfg.get("atnf_db_member", "psrcat_tar/psrcat.db")
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tf:
        names = tf.getnames()
        target = member if member in names else next(
            (n for n in names if n.endswith("psrcat.db")), None
        )
        if not target:
            raise RuntimeError(f"psrcat.db not in archive; members={names[:20]}")
        f = tf.extractfile(target)
        RAW_DB.write_bytes(f.read())
    print(f"extracted {target} -> {RAW_DB} ({RAW_DB.stat().st_size} bytes)")
    meta["last_download_ts"] = time.time()
    meta["source_url"] = urls[0]
    save_meta(meta)
    return RAW_DB


# ---------------------------------------------------------------------------
# psrcat.db parser
# ---------------------------------------------------------------------------

# Line forms:
#   PSRJ     J0002+6216                    cwp+17
#   RAJ      00:02:58.17              2    cwp+17
#   F0       8.66824782740            10   cwp+17
#   TYPE     HE[wcp+18]
#   ASSOC    GRS:4FGL_J0002.8+6217[aab+22],...
#   SURVEY   FermiBlind
#   # comment
#   @----  (entry separator)

FIELD_RE = re.compile(r"^([A-Z][A-Z0-9_]*)\s+(.*\S)\s*$")
# trailing literature ref like  cwp+17  /  lww+05  /  mkl+06
REF_RE = re.compile(r"\s+([a-z]{2,}[+&][0-9]{2}[a-z]?)\s*$")
# numeric value with optional error:  value   err
NUM_RE = re.compile(
    r"^([+-]?(?:\d+\.?\d*|\.\d+)(?:[Ee][+-]?\d+)?)"
    r"(?:\s+([+-]?(?:\d+\.?\d*|\.\d+)(?:[Ee][+-]?\d+)?))?"
)


def parse_entry_fields(body: str) -> dict:
    """Parse one catalogue entry body into {FIELD: {value, error, ref}}."""
    fields: dict[str, dict] = {}
    cur_field = None
    for raw in body.splitlines():
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = FIELD_RE.match(line.strip())
        if not m:
            continue
        name, rest = m.group(1), m.group(2).strip()
        ref = ""
        rm = REF_RE.search(rest)
        # only strip ref if it looks like a bibtex key at the end and isn't part of value
        if rm:
            cand = rm.group(1)
            # avoid eating things like  10.1088/0004-637X or numbers
            if re.fullmatch(r"[a-z]{2,}[+&][0-9]{2}[a-z]?", cand):
                ref = cand
                rest = rest[: rm.start()].strip()
        value = rest
        error = None
        # try numeric split
        nm = NUM_RE.match(rest)
        if nm and nm.group(2) is not None:
            value = nm.group(1)
            error = nm.group(2)
        elif nm and re.fullmatch(r"[+-]?(?:\d+\.?\d*|\.\d+)(?:[Ee][+-]?\d+)?", rest.strip()):
            value = nm.group(1)
        fields[name] = {"value": value, "error": error, "ref": ref}
        cur_field = name
    return fields


def parse_psrcat_db(path: Path) -> list[dict]:
    text = path.read_text(encoding="latin-1", errors="replace")
    # split on @----- separators
    chunks = re.split(r"^@-+", text, flags=re.M)
    entries = []
    for chunk in chunks:
        if "PSRJ" not in chunk and "PSRB" not in chunk:
            continue
        fields = parse_entry_fields(chunk)
        if not fields:
            continue
        jname = (fields.get("PSRJ") or {}).get("value")
        bname = (fields.get("PSRB") or {}).get("value")
        if not jname and not bname:
            continue
        if jname:
            jname = jname.strip()
            m = re.search(r"(J\d{4}[+-]\d{3,4})", jname)
            if m:
                jname = m.group(1)
        if bname:
            bname = bname.strip()
            m = re.search(r"(B\d{4}[+-]\d{2,3})", bname)
            if m:
                bname = m.group(1)
        entries.append({"jname": jname, "bname": bname, "fields": fields})
    return entries


# ---------------------------------------------------------------------------
# SQLite load
# ---------------------------------------------------------------------------

def _num(val: str | None) -> float | None:
    if val is None:
        return None
    try:
        return float(str(val).strip())
    except Exception:
        return None


SECONDS_PER_YEAR = 365.25 * 86400.0
I_NS = 1.0e45  # canonical NS moment of inertia (g cm^2)
C_MS = 2.99792458e10  # cm/s
R_NS = 1.0e6  # cm


def derive_spin_params(rec: dict) -> None:
    """Fill P0/P1/F0/F1 cross-derivations and AGE/BSURF/EDOT/BLC if missing.

    ATNF psrcat.db stores measured F0/F1 or P0/P1; characteristic age,
    surface field and spin-down power are computed by the `psrcat` tool
    on the fly and are not present in the raw database file.
    """
    p0 = rec.get("p0")
    p1 = rec.get("p1")
    f0 = rec.get("f0")
    f1 = rec.get("f1")

    if p0 is None and f0:
        try:
            p0 = 1.0 / float(f0)
            rec["p0"] = p0
        except Exception:
            pass
    if p1 is None and f1 is not None and f0:
        try:
            p1 = -float(f1) / (float(f0) * float(f0))
            rec["p1"] = p1
        except Exception:
            pass
    if f0 is None and p0:
        try:
            f0 = 1.0 / float(p0)
            rec["f0"] = f0
        except Exception:
            pass
    if f1 is None and p1 is not None and f0:
        try:
            # F1 = -P1 / P0^2 = -P1 * F0^2
            f1 = -float(p1) * (float(f0) ** 2)
            rec["f1"] = f1
        except Exception:
            pass

    # spin-down quantities need P1 > 0 (period increasing)
    if p0 and p0 > 0 and p1 is not None and p1 > 0:
        if rec.get("age") is None:
            rec["age"] = (p0 / (2.0 * p1)) / SECONDS_PER_YEAR
        if rec.get("bsurf") is None:
            rec["bsurf"] = 3.2e19 * (p0 * p1) ** 0.5
        if rec.get("edot") is None:
            rec["edot"] = 4.0 * (3.141592653589793**2) * I_NS * p1 / (p0**3)
        if rec.get("blc") is None:
            # B_LC = B_s * (R_NS / R_LC)^3,  R_LC = c*P0/(2π)
            r_lc = C_MS * p0 / (2.0 * 3.141592653589793)
            if r_lc > 0:
                rec["blc"] = 3.2e19 * (p0 * p1) ** 0.5 * (R_NS / r_lc) ** 3


def build_sqlite(entries: list[dict], cfg: dict) -> None:
    import sqlite3

    if SQLITE.exists():
        SQLITE.unlink()
    con = sqlite3.connect(SQLITE)
    cur = con.cursor()
    cur.execute(
        """
        CREATE TABLE pulsars (
            id INTEGER PRIMARY KEY,
            jname TEXT,
            bname TEXT,
            p0 REAL, p1 REAL, f0 REAL, f1 REAL, f2 REAL,
            dm REAL, dm1 REAL, rm REAL, rm1 REAL,
            raj TEXT, decj TEXT,
            gl REAL, gb REAL, elong TEXT, elat TEXT,
            pmra REAL, pmdec REAL, px REAL,
            s400 REAL, s600 REAL, s1400 REAL, s1500 REAL, s3000 REAL, s5000 REAL,
            w50 REAL, w10 REAL, scat REAL,
            pb REAL, a1 REAL, ecc REAL, t0 REAL, om REAL,
            minmass REAL, medmass REAL, m2 REAL,
            age REAL, bsurf REAL, blc REAL, edot REAL,
            type TEXT, survey TEXT, assoc TEXT,
            extra TEXT, fields_json TEXT, raw_fields TEXT
        )
        """
    )
    cur.execute("CREATE UNIQUE INDEX idx_j ON pulsars(jname)")
    cur.execute("CREATE INDEX idx_b ON pulsars(bname)")
    cur.execute("CREATE INDEX idx_dm ON pulsars(dm)")
    cur.execute("CREATE INDEX idx_p0 ON pulsars(p0)")

    cols = [
        "jname", "bname",
        "p0", "p1", "f0", "f1", "f2",
        "dm", "dm1", "rm", "rm1",
        "raj", "decj", "gl", "gb", "elong", "elat",
        "pmra", "pmdec", "px",
        "s400", "s600", "s1400", "s1500", "s3000", "s5000",
        "w50", "w10", "scat",
        "pb", "a1", "ecc", "t0", "om",
        "minmass", "medmass", "m2",
        "age", "bsurf", "blc", "edot",
        "type", "survey", "assoc",
        "extra", "fields_json", "raw_fields",
    ]

    # map ATNF field -> column
    to_col = {
        "P0": "p0", "P1": "p1", "F0": "f0", "F1": "f1", "F2": "f2",
        "DM": "dm", "DM1": "dm1", "RM": "rm", "RM1": "rm1",
        "RAJ": "raj", "DECJ": "decj", "GL": "gl", "GB": "gb",
        "ELONG": "elong", "ELAT": "elat",
        "PMRA": "pmra", "PMDEC": "pmdec", "PX": "px",
        "S400": "s400", "S600": "s600", "S1400": "s1400",
        "S1500": "s1500", "S3000": "s3000", "S5000": "s5000",
        "W50": "w50", "W10": "w10", "Scat": "scat",
        "PB": "pb", "A1": "a1", "ECC": "ecc", "T0": "t0", "OM": "om",
        "MINMASS": "minmass", "MEDMASS": "medmass", "M2": "m2",
        "AGE": "age", "BSURF": "bsurf", "BLC": "blc", "EDOT": "edot",
        "TYPE": "type", "SURVEY": "survey", "ASSOC": "assoc",
    }
    core = set(cfg.get("core_fields") or [])
    numeric = set(cfg.get("numeric_fields") or [])

    rows = []
    for e in entries:
        fields = e["fields"]
        rec = {c: None for c in cols}
        rec["jname"] = e["jname"]
        rec["bname"] = e["bname"]
        extra = {}
        for fname, finfo in fields.items():
            val = finfo.get("value")
            col = to_col.get(fname)
            if col:
                if col in ("jname", "bname"):
                    pass
                elif fname in numeric or col in {
                    "p0", "p1", "f0", "f1", "f2", "dm", "dm1", "rm", "rm1",
                    "gl", "gb", "pmra", "pmdec", "px",
                    "s400", "s600", "s1400", "s1500", "s3000", "s5000",
                    "w50", "w10", "scat", "pb", "a1", "ecc", "t0", "om",
                    "minmass", "medmass", "m2", "age", "bsurf", "blc", "edot",
                }:
                    rec[col] = _num(val)
                else:
                    rec[col] = val
            elif fname in core or fname not in {
                "PSRJ", "PSRB", "RAJ", "DECJ", "PEPOCH", "DMEPOCH",
            }:
                extra[fname] = finfo
        rec["extra"] = json.dumps(extra, ensure_ascii=False)
        # ATNF often stores F0/F1 rather than P0/P1; AGE/BSURF/EDOT/BLC
        # are computed by psrcat on the fly and are absent from psrcat.db.
        derive_spin_params(rec)
        fj = {k: v.get("value") for k, v in fields.items()}
        if rec.get("p0") is not None and "P0" not in fj:
            fj["P0"] = f"{rec['p0']:.12g}"
        if rec.get("p1") is not None and "P1" not in fj:
            fj["P1"] = f"{rec['p1']:.12g}"
        # surface derived quantities so the detail page can show them
        for src, key in (("p0", "P0"), ("p1", "P1"), ("f0", "F0"), ("f1", "F1")):
            if rec.get(src) is not None and key not in fj:
                fj[key] = f"{rec[src]:.12g}"
        for col, fname in (("age", "AGE"), ("bsurf", "BSURF"), ("edot", "EDOT"), ("blc", "BLC")):
            if rec.get(col) is not None and fname not in fj:
                fj[fname] = f"{rec[col]:.12g}"
                extra.setdefault(fname, {"value": fj[fname], "error": None, "ref": "derived"})
        rec["extra"] = json.dumps(extra, ensure_ascii=False)
        rec["fields_json"] = json.dumps(fj, ensure_ascii=False)
        rec["raw_fields"] = json.dumps(fields, ensure_ascii=False)
        rows.append(tuple(rec[c] for c in cols))

    ph = ",".join("?" for _ in cols)
    # ATNF can contain rare duplicate PSRJ keys; keep the last entry
    cur.executemany(
        f"INSERT OR REPLACE INTO pulsars ({','.join(cols)}) VALUES ({ph})", rows
    )
    con.commit()
    # FTS-like helper: search table
    cur.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS pulsars_fts USING fts5(
            jname, bname, type, assoc, content=''
        )
        """
    )
    con.commit()
    con.close()
    print(f"SQLite built: {SQLITE}  rows={len(rows)}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="use cached data/psrcat.db")
    ap.add_argument("--force", action="store_true", help="force re-download")
    args = ap.parse_args()

    cfg = load_config()
    DATA.mkdir(parents=True, exist_ok=True)

    if args.offline:
        if not RAW_DB.exists():
            print("no cached psrcat.db; run without --offline first", file=sys.stderr)
            return 1
    else:
        try:
            download_psrcat_db(cfg, force=args.force)
        except Exception as ex:
            if RAW_DB.exists():
                print(f"download failed ({ex}); using cached psrcat.db", file=sys.stderr)
            else:
                print(f"download failed: {ex}", file=sys.stderr)
                return 1

    print("parsing psrcat.db ...")
    entries = parse_psrcat_db(RAW_DB)
    print(f"parsed {len(entries)} entries")
    build_sqlite(entries, cfg)

    meta = load_meta()
    meta.update(
        {
            "last_build_ts": time.time(),
            "n_pulsars": len(entries),
            "psrcat_bytes": RAW_DB.stat().st_size,
            "update_interval_days": cfg.get("update_interval_days", 14),
            "next_due_ts": time.time() + float(cfg.get("update_interval_days", 14)) * 86400,
        }
    )
    # try read catalogue version comment
    try:
        head = RAW_DB.read_text(encoding="latin-1", errors="replace")[:500]
        m = re.search(r"CATALOGUE\s+([0-9.]+)", head)
        if m:
            meta["catalogue_version"] = m.group(1)
    except Exception:
        pass
    save_meta(meta)
    print(f"done. meta={META}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
