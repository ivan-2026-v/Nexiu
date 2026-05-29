# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

A recruitment funnel dashboard for **LAFA / Nexiu**. Data lives in a Supabase table (`funnel`), fed daily by a Playwright automation that logs into the Railway app, and displayed in a single self-contained HTML file. No build step, no package manager, no framework.

---

## Final data flow

```
Railway app (lafa-nexiu-os-production.up.railway.app)
    │
    │  sync_railway.py  — Playwright logs in via Google OAuth,
    │                     selects "Rango de días" 2026-04-01 → today,
    │                     downloads .xlsx
    ▼
/Users/ivan/Code/vibe-coding/nexiu/LAFA/
    hr_os_funnel_Rango_…_Nexiu_YYYY-MM-DD.xlsx
    │
    │  upload_to_supabase.py
    │  upsert on id_candidato (merge-duplicates, nulls stripped)
    ▼
Supabase table: funnel  (one row per candidate)
    │
    │  fetch() at page load
    ▼
LAFA/recruitment-dashboard.html  (vanilla JS + Chart.js)
```

**Trigger:** macOS launchd fires at **9:00, 9:15, and 9:30 am** every day.  
The first successful run writes `.last_sync_date`; the other two exit immediately.  
If the Mac is off at 9:00, the 9:15 or 9:30 attempt catches it.

---

## Run the sync

```bash
# Normal headless run (what launchd does)
python3 sync_railway.py

# Force re-run even if already ran today
python3 sync_railway.py --force

# Watch the browser while it runs
python3 sync_railway.py --headed

# Download only, skip Supabase upload
python3 sync_railway.py --no-upload

# Explore Railway UI and print element snapshots (no upload)
python3 sync_railway.py --explore
```

---

## Manage the launchd agent

```bash
# Check status (shows last exit code)
launchctl list | grep nexiu

# Reload after editing the plist
launchctl unload ~/Library/LaunchAgents/com.nexiu.lafa.sync.plist
launchctl load   ~/Library/LaunchAgents/com.nexiu.lafa.sync.plist

# Trigger right now (without waiting for 9am)
launchctl start com.nexiu.lafa.sync

# Watch the log
tail -f /Users/ivan/Code/vibe-coding/nexiu/LAFA/sync_railway.log
```

Plist location: `~/Library/LaunchAgents/com.nexiu.lafa.sync.plist`  
Log location: `sync_railway.log` in this folder

---

## Manual upload from a local Excel file

```bash
python3 upload_to_supabase.py funnel.xlsx
python3 upload_to_supabase.py funnel.xlsx --periodo 2026-05-01_2026-05-31
```

Python deps: `openpyxl`, `requests`, `playwright` — install with `pip`.

The GitHub Actions workflow (`.github/workflows/sync-funnel.yml`) is **disabled** — it was the old Google Sheets sync. Data now comes exclusively from Railway via `sync_railway.py`.

---

## Dashboard

Open `LAFA/recruitment-dashboard.html` directly in a browser — no server needed.  
It fetches from Supabase at load time via REST API; result stored in `window._allRows`.

Three tabs: **Executive** · **Detalle Asistencia** · **Pipeline Activo**

Key JS functions:
- `renderFunnel` / `updateKPIs` / `renderCharts` — Executive tab
- `renderDetalleAsistencia` — attendance detail tab
- `renderPipeline` — active pipeline tab
- `makeChart(id, config)` — destroys prior Chart.js instance before creating new
- `isActivePipeline(r)` / `getPipelineStage(r)` — pipeline logic (6 stages)
- `isoWeek(dateStr)` — local date parsing, no UTC shift
- Friday 3pm Mexico City cutoff to exclude partial current-week data

---

## Supabase schema (table: `funnel`)

| Column | Meaning |
|---|---|
| `id_candidato` | Primary key (upsert key) |
| `asistencia` | `'Realizada'` = attended interview |
| `suma_bg` | `'Aprobado'` = passed interview + background check |
| `prueba_manejo` | `'Aprobado'` / `'No aprobado'` |
| `firma_contrato` | Date string if hired |
| `status_driver` | Final status (e.g. `'Listo para onboarding'`, `'Contratado'`) |
| `declina_oferta` | `'Sí'` if candidate declined the offer |
| `inicio` | Date the candidate first attended (YYYY-MM-DD) |
| `hora_llegada` | Arrival timestamp; used as presence date when available |
| `periodo` | Upload period string (e.g. `'2026-04-01_2026-05-29'`) |

## Adding a new column

1. Add the column to the Supabase table.
2. Map it in `upload_to_supabase.py` inside `load_excel()`.
3. Reference it in the HTML as `r.column_name` (snake_case).

The uploader silently skips unknown columns (PGRST204 handling), so old syncs won't break.
