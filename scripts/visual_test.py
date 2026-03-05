"""Take full-page screenshots of every UI route and interactive state.

Starts the FastAPI app against the PostgreSQL database configured in .env,
launches headless Chrome via Selenium, and saves PNGs to /tmp.

The Tailwind Play CDN <script> tag is blocked via CDP and replaced with
pre-compiled Tailwind CSS injected into each page. The CSS is compiled
from the project templates using the Tailwind CLI.

Captures:
    - Team table with all reps and pagination controls
    - Click-through from team to each rep detail page
    - Expanded <details> elements showing email body and scorer notes
    - Back-to-team navigation
    - Settings page with form values and operations panel
    - Nav bar link navigation between pages

Prerequisites:
    - PostgreSQL running with migrations applied and seed data loaded
    - google-chrome-stable installed
    - selenium installed (pipenv install --dev selenium)
    - tailwindcss npm package (npm install -g tailwindcss@3)

Usage:
    pipenv run python -m scripts.visual_test
"""

import os
import subprocess
import threading
import time
from pathlib import Path

os.environ.setdefault("AUTH_ENABLED", "FALSE")
os.environ.setdefault("CURRENT_USER", "test")

import uvicorn
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By

from app.main import app

APP_PORT = 8765
BASE = f"http://127.0.0.1:{APP_PORT}"
TAILWIND_CSS_CACHE = "/tmp/tailwind_compiled.css"


def _compile_tailwind():
    """Compile Tailwind CSS from the project templates."""
    templates = str(Path(__file__).resolve().parent.parent / "app" / "templates" / "**" / "*.html")
    subprocess.run(
        ["npx", "tailwindcss", "--content", templates, "-o", TAILWIND_CSS_CACHE, "--minify"],
        check=True,
        timeout=30,
        capture_output=True,
    )


def _run_app_server():
    uvicorn.run(app, host="127.0.0.1", port=APP_PORT, log_level="error")


def _inject_tailwind(driver, tailwind_css):
    """Inject compiled Tailwind CSS if not already present."""
    driver.execute_script("""
    if (!document.getElementById('tw-injected')) {
        var style = document.createElement('style');
        style.id = 'tw-injected';
        style.textContent = arguments[0];
        document.head.appendChild(style);
    }
    """, tailwind_css)


def _screenshot(driver, tailwind_css, name):
    """Inject Tailwind CSS, resize to full page height, and screenshot."""
    _inject_tailwind(driver, tailwind_css)
    time.sleep(1)
    total_height = driver.execute_script("return document.body.scrollHeight")
    driver.set_window_size(1440, max(900, total_height + 200))
    time.sleep(0.5)
    path = f"/tmp/{name}.png"
    driver.save_screenshot(path)
    print(f"    saved {path}")


def _take_screenshots():
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1440,900")
    chrome_options.binary_location = "/usr/bin/google-chrome-stable"

    service = Service("/opt/node22/bin/chromedriver")
    driver = webdriver.Chrome(service=service, options=chrome_options)
    driver.set_page_load_timeout(30)

    # Block the Tailwind CDN so Chrome doesn't hang on the <script> tag.
    driver.execute_cdp_cmd("Network.enable", {})
    driver.execute_cdp_cmd(
        "Network.setBlockedURLs",
        {"urls": ["*cdn.tailwindcss.com*"]},
    )

    with open(TAILWIND_CSS_CACHE) as f:
        tailwind_css = f.read()

    # ── 1. Team ──────────────────────────────────────────────────────────
    print("  1. Team")
    driver.get(f"{BASE}/")
    time.sleep(1)
    _screenshot(driver, tailwind_css, "01_team")

    # ── 1b. Team page with per_page=2 to show pagination controls ──────
    print("  1b. Team with pagination controls")
    driver.get(f"{BASE}/?per_page=2")
    time.sleep(1)
    _screenshot(driver, tailwind_css, "01b_team_paginated")

    # ── 2. Click first rep link -> rep detail ────────────────────────────
    print("  2. Click first rep -> rep detail")
    first_rep_link = driver.find_element(By.CSS_SELECTOR, "tbody a.text-blue-600")
    first_rep_name = first_rep_link.text
    first_rep_link.click()
    time.sleep(1)
    _screenshot(driver, tailwind_css, "02_rep_detail_via_click")

    # ── 2b. Rep detail with search/filter controls visible ────────────────
    print("  2b. Rep detail with search/filter controls")
    search_input = driver.find_element(By.ID, "search-input")
    search_input.send_keys("test")
    _screenshot(driver, tailwind_css, "02b_rep_detail_filters")
    search_input.clear()

    # ── 3. Expand all email <details> to show body and notes ─────────────
    print("  3. Expand email details (body + notes)")
    for summary in driver.find_elements(By.CSS_SELECTOR, "details summary"):
        summary.click()
        time.sleep(0.3)
    _screenshot(driver, tailwind_css, "03_rep_detail_expanded")

    # ── 4. Click "Back to Team" ─────────────────────────────────────────
    print("  4. Click back to team link")
    back_link = driver.find_element(By.LINK_TEXT, "\u2190 Back to Team")
    back_link.click()
    time.sleep(1)
    _screenshot(driver, tailwind_css, "04_team_via_back")

    # ── 5. Click a different rep ─────────────────────────────────────────
    print("  5. Click different rep")
    rep_links = driver.find_elements(By.CSS_SELECTOR, "tbody a.text-blue-600")
    for link in rep_links:
        if link.text != first_rep_name:
            link.click()
            break
    time.sleep(1)
    _screenshot(driver, tailwind_css, "05_rep_detail_second_rep")

    # Expand details on second rep
    for summary in driver.find_elements(By.CSS_SELECTOR, "details summary"):
        summary.click()
        time.sleep(0.3)
    _screenshot(driver, tailwind_css, "06_rep_detail_second_expanded")

    # ── 6. Navigate to Settings via nav link ─────────────────────────────
    print("  6. Click Settings nav link")
    driver.find_element(By.LINK_TEXT, "Settings").click()
    time.sleep(2)  # extra time for loadJobs() JS fetch
    _screenshot(driver, tailwind_css, "07_settings")

    # ── 7. Navigate back to Team via nav link ────────────────────────────
    print("  7. Click Team nav link")
    driver.find_element(By.LINK_TEXT, "Team").click()
    time.sleep(1)
    _screenshot(driver, tailwind_css, "08_team_via_nav")

    # ── 8. Direct URL to every rep detail, with expanded emails ──────────
    rep_emails = [
        "sheraazahmed@native.fm",
        "kieranberrycampbell@nativecampusadvertising.com",
        "inderpalgill@nativecampusadvertising.com",
        "setaitarokodrava@nativecampusadvertising.com",
    ]
    for i, rep_email in enumerate(rep_emails):
        short = rep_email.split("@")[0]
        print(f"  {9 + i}. Rep detail: {short}")
        driver.get(f"{BASE}/reps/{rep_email}")
        time.sleep(1)
        _inject_tailwind(driver, tailwind_css)
        time.sleep(0.5)
        # Expand all email details
        for summary in driver.find_elements(By.CSS_SELECTOR, "details summary"):
            summary.click()
            time.sleep(0.3)
        _screenshot(driver, tailwind_css, f"{9 + i:02d}_rep_{short}")

    driver.quit()


def main():
    print("Compiling Tailwind CSS...")
    _compile_tailwind()

    app_thread = threading.Thread(target=_run_app_server, daemon=True)
    app_thread.start()
    time.sleep(2)

    print("Taking screenshots...")
    _take_screenshots()
    print("Done.")


if __name__ == "__main__":
    main()
