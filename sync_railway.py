#!/usr/bin/env python3
"""
Daily sync agent:
  1. Logs into https://lafa-nexiu-os-production.up.railway.app/workflow via Google OAuth
  2. Exports data from 2026-04-01 to today using "Rango de días" mode
  3. Saves the .xlsx to /Users/ivan/Code/vibe-coding/nexiu/LAFA/
  4. Uploads to Supabase via upload_to_supabase.py

Usage:
    python3 sync_railway.py               # headless
    python3 sync_railway.py --headed      # show browser window
    python3 sync_railway.py --explore     # explore UI only (no upload)
    python3 sync_railway.py --no-upload   # download but skip Supabase upload
"""

import argparse
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# ── CONFIG ────────────────────────────────────────────────────────────────────
RAILWAY_URL   = "https://lafa-nexiu-os-production.up.railway.app/workflow"
GOOGLE_EMAIL  = "i@nexiu.ai"
GOOGLE_PASS   = "kjWgvRgpe%$42P"
DOWNLOAD_DIR  = Path("/Users/ivan/Code/vibe-coding/nexiu/LAFA")
UPLOAD_SCRIPT = DOWNLOAD_DIR / "upload_to_supabase.py"
START_DATE    = "2026-04-01"   # Always April 1st
SENTINEL_FILE = DOWNLOAD_DIR / ".last_sync_date"   # tracks "already ran today"

# ── HELPERS ───────────────────────────────────────────────────────────────────

def today_str():
    return date.today().strftime("%Y-%m-%d")

def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def snapshot(page, label="PAGE SNAPSHOT"):
    """Print visible interactive elements for debugging."""
    log(f"\n── {label} ─────────────────────────────────")
    log(f"  URL: {page.url}")
    for tag in ("button", "input", "select"):
        for el in page.query_selector_all(tag):
            try:
                text  = (el.inner_text() or "").strip()[:60]
                attrs = {a: el.get_attribute(a)
                         for a in ("type","placeholder","aria-label","name","id","value")
                         if el.get_attribute(a)}
                if text or attrs:
                    log(f"  <{tag}> '{text}' {attrs}")
            except Exception:
                pass
    log("─────────────────────────────────────────────\n")


# ── AUTH ──────────────────────────────────────────────────────────────────────

def google_login(page):
    """Handle Google OAuth: email → Next → password → Next → wait for Railway."""
    log("  Google login…")

    # Email
    try:
        page.wait_for_selector('input[type="email"]', timeout=15_000)
        page.fill('input[type="email"]', GOOGLE_EMAIL)
        page.keyboard.press("Enter")
        log("  Email ingresado")
    except PWTimeout:
        log("  ⚠ Sin campo de email")
        return

    # Password
    try:
        page.wait_for_selector('input[type="password"]', timeout=15_000)
        page.fill('input[type="password"]', GOOGLE_PASS)
        page.keyboard.press("Enter")
        log("  Password ingresado")
    except PWTimeout:
        log("  ⚠ Sin campo de password")
        return

    # Wait for redirect back to Railway
    try:
        page.wait_for_url("**/workflow**", timeout=25_000)
        log("  ✓ Login completado")
    except PWTimeout:
        log(f"  URL post-login: {page.url}")
        # "Allow" screen
        for sel in ['button:has-text("Allow")', 'button:has-text("Continuar")',
                    'button:has-text("Continue")', '#submit_approve_access']:
            btn = page.query_selector(sel)
            if btn:
                btn.click()
                log(f"  Clic en '{sel}'")
                break
        try:
            page.wait_for_url("**/workflow**", timeout=15_000)
            log("  ✓ Login completado (tras Allow)")
        except PWTimeout:
            log(f"  ⚠ No pudo redirigir — URL: {page.url}")


def ensure_logged_in(page):
    """Navigate to Railway and handle login if needed."""
    log(f"Navegando a {RAILWAY_URL}…")
    page.goto(RAILWAY_URL, wait_until="load", timeout=30_000)
    page.wait_for_timeout(1500)

    url = page.url
    if "accounts.google.com" in url:
        google_login(page)
    elif "/login" in url or "/auth" in url:
        # Click "Login with Google" button
        for sel in ['button:has-text("Google")', 'a:has-text("Google")',
                    '[data-provider="google"]',
                    'button:has-text("Iniciar sesión con Google")']:
            btn = page.query_selector(sel)
            if btn:
                btn.click()
                log(f"  Clic en botón Google login")
                page.wait_for_timeout(2000)
                break
        if "accounts.google.com" in page.url:
            google_login(page)
    else:
        log(f"  URL: {url} (puede que ya esté logueado)")

    try:
        page.wait_for_url("**/workflow**", timeout=10_000)
    except PWTimeout:
        pass
    log(f"✓ En la app — URL: {page.url}")


# ── EXPORT ────────────────────────────────────────────────────────────────────

def download_export(page, explore=False):
    """
    1. Click "Descargar funnel"
    2. In the modal: select "Rango de días", fill dates, click download
    Returns local Path of downloaded file, or None.
    """
    page.wait_for_load_state("load", timeout=20_000)
    page.wait_for_timeout(2000)   # extra settle time for JS rendering
    if explore:
        snapshot(page, "BEFORE EXPORT CLICK")

    # ── 1. Open the export modal ──────────────────────────────────────────────
    # Use exact text "Descargar funnel" to avoid matching anything else
    export_btn = page.query_selector('button:has-text("Descargar funnel")')
    if not export_btn:
        log("⚠ No se encontró el botón 'Descargar funnel'")
        snapshot(page, "CURRENT PAGE")
        return None

    export_btn.click()
    log("  Clic en 'Descargar funnel'")

    # Wait for modal to appear (the <select> is the key indicator)
    try:
        page.wait_for_selector('#crm-funnel-report-mode', timeout=8_000)
        log("  Modal de descarga abierto")
    except PWTimeout:
        log("  ⚠ Modal no apareció")
        snapshot(page, "AFTER EXPORT CLICK")
        return None

    if explore:
        snapshot(page, "MODAL OPEN (default mode)")

    # ── 2. Switch to "Rango de días" ─────────────────────────────────────────
    mode_select = page.query_selector('#crm-funnel-report-mode')
    mode_select.select_option(label="Rango de días")
    log("  Modo 'Rango de días' seleccionado")
    page.wait_for_timeout(800)   # let the UI re-render

    if explore:
        snapshot(page, "AFTER SELECTING 'Rango de días'")

    # ── 3. Fill date range ────────────────────────────────────────────────────
    end_date = today_str()

    # Known IDs (confirmed from UI exploration):
    start_inp = page.query_selector('#crm-funnel-report-start')
    end_inp   = page.query_selector('#crm-funnel-report-end')

    if start_inp and end_inp:
        start_inp.fill(START_DATE)
        end_inp.fill(end_date)
        log(f"  Fechas ingresadas: {START_DATE} → {end_date}")
        filled_start = filled_end = True
    else:
        filled_start = filled_end = False
        log("  ⚠ No se encontraron los campos #crm-funnel-report-start / -end")

    if explore:
        snapshot(page, "AFTER FILLING DATES")

    if not (filled_start and filled_end):
        log("  ⚠ No se pudieron rellenar ambas fechas")

    # ── 4. Click the download button inside the modal ─────────────────────────
    # The button text is something like "Descargar: Rango 2026-04-01 – 2026-05-29"
    # We use :visible and exclude "Descargar funnel" which is behind the overlay
    today = today_str()
    with page.expect_download(timeout=60_000) as dl_info:
        # Prefer a button that contains both "Descargar" and a date-like string
        # inside the modal (not the main-page button)
        dl_btn = None

        # 1st try: button with "Rango" in text (most specific)
        dl_btn = dl_btn or page.query_selector('button:has-text("Rango")')
        # 2nd try: any visible "Descargar" button that's NOT "Descargar funnel"
        if not dl_btn:
            for btn in page.query_selector_all('button:has-text("Descargar")'):
                txt = (btn.inner_text() or "").strip()
                if txt != "Descargar funnel" and btn.is_visible():
                    dl_btn = btn
                    break
        # 3rd try: submit inside any dialog
        if not dl_btn:
            dl_btn = page.query_selector('[role="dialog"] button[type="submit"]')
        # 4th try: any visible submit button
        if not dl_btn:
            dl_btn = page.query_selector('button[type="submit"]:visible')

        if not dl_btn:
            log("  ⚠ No se encontró botón de descarga dentro del modal")
            if explore:
                snapshot(page, "COULD NOT FIND DOWNLOAD BUTTON")
            return None

        txt = (dl_btn.inner_text() or "").strip()
        log(f"  Clic en botón de descarga: '{txt}'")
        dl_btn.click()

    dl   = dl_info.value
    name = dl.suggested_filename or f"funnel_{today}.xlsx"
    dest = DOWNLOAD_DIR / name
    dl.save_as(str(dest))
    log(f"✓ Archivo descargado → {dest}  ({dest.stat().st_size:,} bytes)")
    return dest


# ── MAIN ──────────────────────────────────────────────────────────────────────

def already_ran_today():
    """Return True if the sentinel file records today's date."""
    try:
        return SENTINEL_FILE.read_text().strip() == today_str()
    except FileNotFoundError:
        return False

def mark_ran_today():
    SENTINEL_FILE.write_text(today_str())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--headed",    action="store_true", help="Show browser window")
    parser.add_argument("--explore",   action="store_true", help="Print UI snapshots (implies --headed)")
    parser.add_argument("--no-upload", action="store_true", help="Skip Supabase upload")
    parser.add_argument("--force",     action="store_true", help="Run even if already ran today")
    args = parser.parse_args()

    headed  = args.headed or args.explore
    explore = args.explore

    # Skip if already ran today (unless --force or interactive modes)
    if not args.force and not explore and not args.headed:
        if already_ran_today():
            log(f"Ya se ejecutó hoy ({today_str()}). Usa --force para forzar.")
            return

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=not headed,
            slow_mo=300 if headed else 0,
            downloads_path=str(DOWNLOAD_DIR),
        )
        context = browser.new_context(
            accept_downloads=True,
            viewport={"width": 1400, "height": 900},
        )
        page = context.new_page()

        ensure_logged_in(page)

        local_file = download_export(page, explore=explore)
        browser.close()

    if local_file is None:
        log("✗ No se pudo descargar el archivo.")
        sys.exit(1)

    if args.no_upload or explore:
        log(f"Archivo: {local_file}")
        log("(Upload omitido)")
        return

    # ── Upload to Supabase ────────────────────────────────────────────────────
    periodo = f"{START_DATE}_{today_str()}"
    log(f"Subiendo a Supabase (periodo {periodo})…")
    result = subprocess.run(
        [sys.executable, str(UPLOAD_SCRIPT), str(local_file), "--periodo", periodo],
    )
    if result.returncode == 0:
        log("✓ Supabase actualizado correctamente")
        mark_ran_today()   # stamp success so retries today are skipped
    else:
        log(f"✗ Error al subir a Supabase (código {result.returncode})")
        sys.exit(result.returncode)


if __name__ == "__main__":
    main()
