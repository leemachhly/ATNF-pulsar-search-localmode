# Pulsar Query Center

A local, offline-friendly interactive query center for the **ATNF Pulsar Catalogue**. Look up pulsars by **J-name / B-name**, inspect spin, dispersion, magnetic, binary, and flux parameters, and keep the catalogue fresh with periodic ATNF updates.

> Zero third-party dependencies — Python 3.9+ standard library only. Runs on **Windows / Linux / macOS**.

## Features

- **J-name ↔ B-name** cross lookup (`J0826+2637` / `B0823+26`) with fuzzy search
- **Parameter table**: P0, F0, F1, DM, RM, coordinates, flux densities, W50/W10, binary orbital elements, TYPE, and more
- **Derived spin parameters** computed locally when missing from the raw catalogue (see [Derived parameters](#derived-parameters))
- **Detail page**: full ATNF field dump per source; add any field to the main table in one click
- **Filters**: name, DM range, quick tags (has B-name, MSP, high-energy association, binary)
- **Two UI themes** (top-right toggle, persisted):
  - **Blue** — blue background, white parameter text (default)
  - **Light** — white background, black text
- **Language switch** (top-right toggle, persisted):
  - **English** (default)
  - **中文** (Chinese)
- **Auto-update**: refresh from ATNF every 14 days (configurable), or trigger manually from the UI
- **Self-contained package**: copy the whole folder anywhere; optional portable zip included

## Quick Start

| Platform | Command |
|----------|---------|
| Windows | double-click `start.bat`, or run `start.bat` |
| Linux / macOS | `./start.sh` or `sh start.sh` |
| Any | `python start.py` / `python3 start.py` |

This will:

1. Build the local SQLite database if needed
2. Check for ATNF cache expiry (default: 14 days)
3. Start the HTTP server
4. Open the web UI at <http://127.0.0.1:8787/>

### Launcher options

```bash
python start.py --port 8790      # custom port
python start.py --no-browser     # serve only, do not open a browser
python start.py --no-update      # skip auto-update check
python start.py --build-only     # ensure the local database, then exit
python start.py --help
```

### Database-only update

```bash
python update_db.py              # download if needed + rebuild SQLite
python update_db.py --offline    # rebuild from cached data/psrcat.db (no network)
python update_db.py --force      # force re-download the ATNF package
```

## Web UI

| Control | Location | Behavior |
|---------|----------|----------|
| **Language** `EN` / `中文` | header, top-right | Switches all UI text; choice saved in `localStorage` |
| **Theme** `Blue` / `Light` | header, top-right | Blue-white or light theme; choice saved in `localStorage` |
| Search box | left panel | J name / B name / keyword; DM range mode via dropdown |
| Quick tags | under search | All · Has B name · MSP · High-energy · Binary |
| Column headers | table | Click to sort |
| Detail panel | right | Full ATNF fields + **Add field** to extend the main table |
| Refresh / Update ATNF | header | Reload status; force catalogue refresh |

## Derived parameters

Raw `psrcat.db` stores measured values (`P0`/`P1` or `F0`/`F1`, DM, RM, …) but not characteristic age or spin-down quantities. Those are computed at build time:

| Parameter | Formula |
|-----------|---------|
| `AGE` (yr) | `P0 / (2·P1)` |
| `BSURF` (G) | `3.2e19 · √(P0·P1)` |
| `EDOT` (erg/s) | `4π²·I·P1/P0³` (I = 10⁴⁵ g cm²) |
| `BLC` (G) | `BSURF · (R_NS/R_LC)³`, `R_LC = c·P0/(2π)` |

Also auto-converted when missing: `P0 = 1/F0`, `P1 = -F1/F0²` (and the inverse).  
Computed only for spin-down sources (`P1 > 0`). In the detail view these values are tagged `derived`.

## Project Layout

```
pulsar_center/
├── start.py            # cross-platform entry point
├── start.bat           # Windows launcher
├── start.sh            # Linux / macOS launcher
├── server.py           # HTTP server + REST API
├── update_db.py        # ATNF download / parse / SQLite build
├── config.json         # fields, port, update interval
├── static/index.html   # web UI (themes + EN/中文)
├── data/               # generated locally (gitignored)
│   ├── psrcat.db       # ATNF raw catalogue cache
│   ├── pulsars.sqlite  # local query database
│   └── meta.json       # last update / version / next due
├── .gitignore
├── README.md           # this file (English)
├── README.zh-CN.md     # Chinese documentation
└── _smoke_test.py      # optional self-check
```

The folder is self-contained. Copy it anywhere (or unzip the portable archive); only Python 3.9+ is required.  
`data/` is rebuilt automatically on first start.

## Configuration

Edit `config.json`:

```jsonc
{
  "update_interval_days": 14,
  "core_fields": ["PSRJ", "PSRB", "P0", "DM", "RM", "..."],
  "display_fields": ["PSRJ", "PSRB", "P0", "DM", "RM", "..."]
}
```

- `core_fields` — ATNF parameter names to retain (see [psrcat parameter definitions](https://www.atnf.csiro.au/research/pulsar/psrcat/psrcat_definition.html))
- `display_fields` — default columns in the UI table
- `update_interval_days` — auto-refresh period (default 14)
- `field_labels` — optional display labels
- You can also add fields from the web UI (detail page → **Add field**)

After changing fields:

```bash
python update_db.py --offline
```

## REST API

```
GET  /api/status
GET  /api/search?q=J0826&field=jname&limit=50
GET  /api/pulsar/J0826+2637
GET  /api/fields
POST /api/update
POST /api/config          # {update_interval_days, display_fields, ...}
POST /api/field           # {name:"S1500", display:true}
```

## Scheduled Updates

- **Default**: `start.py` / `server.py` re-checks the cache on launch and updates in the background when older than `update_interval_days`.
- **Windows Task Scheduler** (every 14 days):

```bat
schtasks /Create /TN "ATNF_PulsarCenter_Update" /SC DAILY /MO 14 ^
  /TR "python C:\path\to\pulsar_center\update_db.py" /F
```

- **Linux cron** (every 14 days):

```cron
0 4 */14 * *  cd /path/to/pulsar_center && python3 update_db.py >> update.log 2>&1
```

## Notes

- Data from the **ATNF Pulsar Catalogue** (Manchester et al. 2005, AJ 129, 1993).
- About 4000+ pulsars; search supports fuzzy matching.
- No third-party packages — standard library only.
- UI language and theme preferences are stored in the browser (`localStorage`), not on the server.

## License

Data © ATNF / CSIRO. Please cite Manchester et al. (2005) when using catalogue values in publications. Code in this repository is provided as-is for research use.
