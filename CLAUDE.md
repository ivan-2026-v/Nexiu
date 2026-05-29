# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

A recruitment funnel dashboard for **LAFA / Nexiu**. Data lives in a Supabase table (`funnel`), is fed by a Google Sheets spreadsheet exported as `.xlsx`, and is displayed in a single self-contained HTML file. There is no build step, no package manager, and no framework.

## Running / viewing the dashboard

Open `LAFA/recruitment-dashboard.html` directly in a browser. It fetches data from Supabase at load time via the REST API — no local server needed.

## Daily automated sync (macOS launchd)

`sync_railway.py` is the daily sync agent. It:
1. Logs into `https://lafa-nexiu-os-production.up.railway.app/workflow` via Google OAuth
2. Downloads the funnel export for April 1, 2026 → today ("Rango de días")
3. Saves the `.xlsx` to this folder
4. Uploads to Supabase via `upload_to_supabase.py`

```bash
# Run manually (headless)
python3 sync_railway.py

# Run with browser visible
python3 sync_railway.py --headed

# Download only, skip upload
python3 sync_railway.py --no-upload

# Explore UI without uploading (shows element snapshots)
python3 sync_railway.py --explore
```

The macOS launchd agent runs this every day at 8am:
- Plist: `~/Library/LaunchAgents/com.nexiu.lafa.sync.plist`
- Logs: `sync_railway.log` in this folder

```bash
# Load/unload the launchd agent
launchctl load   ~/Library/LaunchAgents/com.nexiu.lafa.sync.plist
launchctl unload ~/Library/LaunchAgents/com.nexiu.lafa.sync.plist

# Run manually right now
launchctl start com.nexiu.lafa.sync
```

## Manual data update from local Excel file

```bash
# Run locally against a local Excel file
python3 upload_to_supabase.py funnel.xlsx

# Pass a custom period string (YYYY-MM-DD_YYYY-MM-DD)
python3 upload_to_supabase.py funnel.xlsx --periodo 2026-05-01_2026-05-31
```

Python dependencies: `openpyxl`, `requests` (no virtualenv in the repo; install with `pip`).

The GitHub Actions workflow (`.github/workflows/sync-funnel.yml`) is **disabled** — it was the old Google Sheets sync. Data now comes exclusively from the Railway app via `sync_railway.py`.

## Architecture

```
funnel.xlsx (Google Sheets export)
    ↓  upload_to_supabase.py
Supabase table: funnel (one row per candidate)
    ↓  fetch() at page load
LAFA/recruitment-dashboard.html  (vanilla JS + Chart.js)
```

**`recruitment-dashboard.html`** is the entire frontend: CSS variables, HTML layout, and all JavaScript in a single `<script>` block. Key sections:

- **Config** — `SUPABASE_URL` and `SUPABASE_KEY` (publishable) at the top of the script.
- **Data fetch** — `fetch()` to `${SUPABASE_URL}/rest/v1/funnel?select=*&limit=10000` on load; result stored in `window._allRows`.
- **Tab rendering** — three tabs (Executive, Detalle Asistencia, Pipeline Activo) each rendered by a dedicated function: `renderFunnel/updateKPIs/renderCharts`, `renderDetalleAsistencia`, `renderPipeline`.
- **Chart management** — `makeChart(id, config)` destroys any prior Chart.js instance before creating a new one to avoid canvas reuse errors.
- **Pipeline logic** — `isActivePipeline(r)` determines which candidates are in the active pipeline; `getPipelineStage(r)` maps a candidate to one of six ordered stages. The pipeline chart uses a Friday-3pm cutoff to exclude partial current-week data.
- **Week numbering** — `isoWeek(dateStr)` computes ISO week from a local date string (no UTC shift); all date math uses local parsing via `parseDateLocal`.

## Supabase schema (table: `funnel`)

Column names map 1-to-1 from the Excel "Funnel" sheet headers. Key columns used in display logic:

| Column | Meaning |
|---|---|
| `id_candidato` | Primary key (upsert key) |
| `asistencia` | `'Realizada'` = attended interview |
| `suma_bg` | `'Aprobado'` = passed interview + background check |
| `prueba_manejo` | `'Aprobado'` / `'No aprobado'` |
| `firma_contrato` | Date string if hired |
| `status_driver` | Final status (e.g., `'Listo para onboarding'`, `'Contratado'`) |
| `declina_oferta` | `'Sí'` if candidate declined the offer |
| `inicio` | Date the candidate first attended (YYYY-MM-DD) |
| `hora_llegada` | Timestamp of arrival; used as the presence date when available |
| `periodo` | String set at upload time (e.g., `'2026-04-01_2026-05-15'`) |

## Adding a new column

1. Add the column to the Supabase table.
2. Map it in `upload_to_supabase.py` inside `load_excel()`.
3. Reference it in the HTML as `r.column_name` (snake_case matching Supabase).
The uploader silently skips unknown columns (PGRST204 handling), so old data syncs won't break.
