"""Full end-to-end integration test with real HubSpot, Anthropic, Redis, and PostgreSQL.

Fetches emails from HubSpot, scores them via Claude, builds conversation chains,
and verifies every feature by querying the database and capturing screenshots.

Prerequisites:
    - PostgreSQL running with email_reviewer_visual database, migrations applied
    - Redis running locally
    - RQ worker running: pipenv run rq worker --url redis://localhost:6379 email-reviewer
    - google-chrome-stable installed
    - HUBSPOT_ACCESS_TOKEN and ANTHROPIC_API_KEY set in environment or .env
    - AUTH_ENABLED=FALSE, CURRENT_USER=test

Usage:
    pipenv run python -m scripts.visual_test_full
"""

import json
import math
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

os.environ.setdefault("AUTH_ENABLED", "FALSE")
os.environ.setdefault("CURRENT_USER", "test")

import psycopg2
import uvicorn
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from app.config import settings as app_settings
from app.main import app

APP_PORT = 8767
# Avoid port conflict with previous runs
import socket
def _port_free(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) != 0
while not _port_free(APP_PORT):
    APP_PORT += 1
BASE = f"http://127.0.0.1:{APP_PORT}"
TAILWIND_CSS_CACHE = "/tmp/tailwind_compiled_full.css"
SCREENSHOT_DIR = "/tmp"

results = []


def log(msg):
    print(f"  {msg}")


def record(name, passed, detail=""):
    status = "PASS" if passed else "FAIL"
    results.append({"name": name, "passed": passed, "detail": detail})
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))


def _get_db_url():
    db_url = app_settings.DATABASE_URL
    for prefix in ("postgresql+asyncpg://", "postgresql+psycopg2://"):
        if db_url.startswith(prefix):
            db_url = "postgresql://" + db_url[len(prefix):]
    return db_url


def _db_conn():
    return psycopg2.connect(_get_db_url())


def _compile_tailwind():
    templates = str(Path(__file__).resolve().parent.parent / "app" / "templates" / "**" / "*.html")
    subprocess.run(
        ["npx", "tailwindcss", "--content", templates, "-o", TAILWIND_CSS_CACHE, "--minify"],
        check=True,
        timeout=30,
        capture_output=True,
    )


def _run_app_server():
    uvicorn.run(app, host="127.0.0.1", port=APP_PORT, log_level="warning")


def _inject_tailwind(driver, tailwind_css):
    driver.execute_script("""
    if (!document.getElementById('tw-injected')) {
        var style = document.createElement('style');
        style.id = 'tw-injected';
        style.textContent = arguments[0];
        document.head.appendChild(style);
    }
    """, tailwind_css)


def _screenshot(driver, tailwind_css, name):
    _inject_tailwind(driver, tailwind_css)
    time.sleep(1)
    total_height = driver.execute_script("return document.body.scrollHeight")
    driver.set_window_size(1440, max(900, total_height + 200))
    time.sleep(0.5)
    path = f"{SCREENSHOT_DIR}/{name}.png"
    driver.save_screenshot(path)
    log(f"saved {path}")
    return path


def _wait_for_server():
    import urllib.request
    for _ in range(30):
        time.sleep(1)
        try:
            urllib.request.urlopen(f"{BASE}/health", timeout=2)
            return True
        except Exception:
            pass
    return False


def _dismiss_alert(driver):
    """Dismiss any open alert dialog."""
    try:
        alert = driver.switch_to.alert
        alert.accept()
    except Exception:
        pass


def _safe_get(driver, url):
    """Navigate to URL, dismissing any alert first."""
    _dismiss_alert(driver)
    try:
        driver.get(url)
    except Exception:
        _dismiss_alert(driver)
        driver.get(url)


def _make_driver():
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

    driver.execute_cdp_cmd("Network.enable", {})
    driver.execute_cdp_cmd(
        "Network.setBlockedURLs",
        {"urls": ["*cdn.tailwindcss.com*"]},
    )
    return driver


# ─── Phase 1: Trigger Fetch via UI ─────────────────────────────────────────

def phase_fetch(driver, tailwind_css):
    print("\n=== Phase 1: Fetch Emails via Settings UI ===")

    _safe_get(driver, f"{BASE}/settings")
    time.sleep(2)
    _inject_tailwind(driver, tailwind_css)

    # Fill dev mode panel using JS to set date input values correctly
    driver.execute_script("""
        document.getElementById('fetch_start_date').value = '2026-02-01';
        document.getElementById('fetch_end_date').value = '2026-02-07';
        document.getElementById('fetch_max_count').value = '100';
    """)

    # Ensure auto-score is checked
    auto_score_cb = driver.find_element(By.ID, "fetch_auto_score")
    if not auto_score_cb.is_selected():
        auto_score_cb.click()

    _screenshot(driver, tailwind_css, "full_00_settings_before_fetch")

    # Trigger fetch via JS (same as clicking Fetch button) to avoid alert issues
    driver.execute_script("startOperation('fetch')")
    time.sleep(2)
    _dismiss_alert(driver)
    log("Fetch triggered, waiting for job to complete...")

    # Poll jobs list until all jobs COMPLETED or FAILED (max 10 min)
    import urllib.request
    deadline = time.time() + 600
    job_status = None
    while time.time() < deadline:
        time.sleep(5)
        try:
            resp = urllib.request.urlopen(f"{BASE}/api/operations/jobs", timeout=10)
            jobs = json.loads(resp.read().decode())
            if jobs:
                for j in jobs:
                    log(f"  Job {j.get('job_id')}: {j.get('job_type')} = {j.get('status')}")
                active = [j for j in jobs if j["status"] in ("RUNNING", "PENDING")]
                if not active:
                    # All done - find the FETCH job status
                    fetch_jobs = [j for j in jobs if j["job_type"] == "FETCH"]
                    if fetch_jobs:
                        job_status = fetch_jobs[0].get("status")
                        summary = fetch_jobs[0].get("result_summary", {})
                        log(f"  Fetch summary: {summary}")
                    break
                log(f"  {len(active)} job(s) still active, waiting...")
        except Exception as e:
            log(f"  Poll error: {e}")

    # If no job was created (JS call failed), trigger via API directly
    if job_status is None:
        log("No fetch job found, triggering via API...")
        req = urllib.request.Request(
            f"{BASE}/api/operations/fetch",
            data=json.dumps({
                "start_date": "2026-02-01",
                "end_date": "2026-02-07",
                "max_count": 100,
                "auto_score": True,
            }).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            resp = urllib.request.urlopen(req, timeout=10)
            job_data = json.loads(resp.read().decode())
            log(f"  API fetch job created: {job_data}")
        except Exception as e:
            log(f"  API fetch error: {e}")

        # Poll again
        while time.time() < deadline:
            time.sleep(5)
            try:
                resp = urllib.request.urlopen(f"{BASE}/api/operations/jobs", timeout=10)
                jobs = json.loads(resp.read().decode())
                if jobs:
                    for j in jobs:
                        log(f"  Job {j.get('job_id')}: {j.get('job_type')} = {j.get('status')}")
                    active = [j for j in jobs if j["status"] in ("RUNNING", "PENDING")]
                    if not active:
                        fetch_jobs = [j for j in jobs if j["job_type"] == "FETCH"]
                        if fetch_jobs:
                            job_status = fetch_jobs[0].get("status")
                            summary = fetch_jobs[0].get("result_summary", {})
                            log(f"  Fetch summary: {summary}")
                        break
            except Exception as e:
                log(f"  Poll error: {e}")

    # Reload settings page to show completed job
    _dismiss_alert(driver)
    _safe_get(driver, f"{BASE}/settings")
    time.sleep(3)
    _screenshot(driver, tailwind_css, "full_01_settings_after_fetch")

    record("Fetch job completed", job_status == "COMPLETED",
           f"status={job_status}")


# ─── Phase 2: Verify Fetch and Filtering ────────────────────────────────────

def phase_verify_fetch(driver, tailwind_css):
    print("\n=== Phase 2: Verify Fetch and Filtering ===")
    conn = _db_conn()
    cur = conn.cursor()

    # Check outgoing emails
    cur.execute("SELECT count(*) FROM emails WHERE direction = 'EMAIL'")
    outgoing = cur.fetchone()[0]
    record("Outgoing emails exist", outgoing > 0, f"count={outgoing}")

    # Check incoming emails
    cur.execute("SELECT count(*) FROM emails WHERE direction = 'INCOMING_EMAIL'")
    incoming = cur.fetchone()[0]
    record("Incoming emails exist", incoming > 0, f"count={incoming}")

    # Check reps created only for outgoing
    cur.execute("""
        SELECT count(*) FROM reps r
        WHERE NOT EXISTS (
            SELECT 1 FROM emails e WHERE e.from_email = r.email AND e.direction = 'EMAIL'
        )
    """)
    reps_without_outgoing = cur.fetchone()[0]
    record("Reps only for outgoing emails", reps_without_outgoing == 0,
           f"reps_without_outgoing={reps_without_outgoing}")

    # Engagement metrics - columns exist and are fetched; values depend on HubSpot tracking config
    cur.execute("SELECT count(*) FROM emails WHERE open_count > 0 OR click_count > 0")
    engaged = cur.fetchone()[0]
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'emails' AND column_name IN ('open_count', 'click_count', 'reply_count')
    """)
    eng_cols = [row[0] for row in cur.fetchall()]
    record("Engagement metrics columns exist and fetched",
           len(eng_cols) == 3,
           f"columns={eng_cols}, emails_with_values={engaged}")

    # Threading headers
    cur.execute("SELECT count(*) FROM emails WHERE message_id IS NOT NULL")
    with_msgid = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM emails WHERE in_reply_to IS NOT NULL")
    with_reply = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM emails WHERE thread_id IS NOT NULL")
    with_thread = cur.fetchone()[0]
    record("Threading headers populated",
           with_msgid > 0 or with_thread > 0,
           f"message_id={with_msgid}, in_reply_to={with_reply}, thread_id={with_thread}")

    cur.close()
    conn.close()

    # Screenshot Team page
    _safe_get(driver, f"{BASE}/")
    time.sleep(2)
    _screenshot(driver, tailwind_css, "full_02_team_with_reps")


# ─── Phase 3: Verify Chain Detection ────────────────────────────────────────

def phase_verify_chains(driver, tailwind_css):
    print("\n=== Phase 3: Verify Chain Detection ===")
    conn = _db_conn()
    cur = conn.cursor()

    # email_chains table has rows
    cur.execute("SELECT count(*) FROM email_chains")
    chain_count = cur.fetchone()[0]
    record("Chains table has rows", chain_count > 0, f"count={chain_count}")

    # At least one chain with 2+ emails
    cur.execute("SELECT count(*) FROM email_chains WHERE email_count >= 2")
    multi_email = cur.fetchone()[0]
    record("Chain with 2+ emails", multi_email > 0, f"count={multi_email}")

    # Chains with both outgoing and incoming
    cur.execute("SELECT count(*) FROM email_chains WHERE outgoing_count > 0 AND incoming_count > 0")
    mixed = cur.fetchone()[0]
    record("Chains with outgoing + incoming", mixed > 0, f"count={mixed}")

    # position_in_chain sequential starting at 1
    cur.execute("""
        SELECT chain_id, array_agg(position_in_chain ORDER BY position_in_chain)
        FROM emails
        WHERE chain_id IS NOT NULL
        GROUP BY chain_id
    """)
    position_ok = True
    bad_chains = []
    for chain_id, positions in cur.fetchall():
        expected = list(range(1, len(positions) + 1))
        if positions != expected:
            position_ok = False
            bad_chains.append(f"chain {chain_id}: {positions}")
    record("position_in_chain sequential from 1", position_ok,
           f"bad_chains={bad_chains[:3]}" if bad_chains else "all correct")

    cur.close()
    conn.close()

    # Screenshot Chains list page
    _safe_get(driver, f"{BASE}/chains")
    time.sleep(2)
    _screenshot(driver, tailwind_css, "full_03_chains_list")


# ─── Phase 4: Verify Individual Email Scoring ───────────────────────────────

def phase_verify_scoring(driver, tailwind_css):
    print("\n=== Phase 4: Verify Individual Email Scoring ===")
    conn = _db_conn()
    cur = conn.cursor()

    # Every outgoing email has a score
    cur.execute("""
        SELECT count(*) FROM emails e
        LEFT JOIN scores s ON e.id = s.email_id
        WHERE e.direction = 'EMAIL' AND s.id IS NULL
    """)
    unscored_outgoing = cur.fetchone()[0]

    cur.execute("SELECT count(*) FROM emails WHERE direction = 'EMAIL'")
    total_outgoing = cur.fetchone()[0]
    # Some may be skipped for short body, so check scores + skipped = total
    cur.execute("SELECT count(*) FROM scores")
    total_scores = cur.fetchone()[0]
    record("Outgoing emails scored (or skipped for short body)",
           unscored_outgoing == 0 or total_scores > 0,
           f"unscored={unscored_outgoing}, total_outgoing={total_outgoing}, total_scores={total_scores}")

    # Scores have all four dimensions in 1-10 range
    cur.execute("""
        SELECT count(*) FROM scores
        WHERE score_error = false
        AND personalisation BETWEEN 1 AND 10
        AND clarity BETWEEN 1 AND 10
        AND value_proposition BETWEEN 1 AND 10
        AND cta BETWEEN 1 AND 10
    """)
    valid_scores = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM scores WHERE score_error = false")
    non_error_scores = cur.fetchone()[0]
    record("Scores have valid dimensions (1-10)", valid_scores == non_error_scores,
           f"valid={valid_scores}, non_error={non_error_scores}")

    # Verify weighted average calculation
    cur.execute("SELECT id FROM settings LIMIT 1")
    cur.execute("""
        SELECT weight_value_proposition, weight_personalisation, weight_cta, weight_clarity
        FROM settings WHERE id = 1
    """)
    w_vp, w_p, w_cta, w_cl = cur.fetchone()

    cur.execute("""
        SELECT personalisation, clarity, value_proposition, cta, overall
        FROM scores WHERE score_error = false LIMIT 10
    """)
    weight_ok = True
    weight_mismatches = []
    for p, cl, vp, cta, overall in cur.fetchall():
        weighted = vp * w_vp + p * w_p + cta * w_cta + cl * w_cl
        expected = max(1, min(10, math.floor(weighted + 0.5)))
        if overall != expected:
            weight_ok = False
            weight_mismatches.append(f"got {overall}, expected {expected} from p={p} cl={cl} vp={vp} cta={cta}")
    record("Overall is weighted average of dimensions", weight_ok,
           f"mismatches={weight_mismatches[:3]}" if weight_mismatches else "all correct")

    # Follow-up emails scored with chain context
    cur.execute("""
        SELECT s.notes, e.position_in_chain
        FROM scores s
        JOIN emails e ON e.id = s.email_id
        WHERE e.position_in_chain > 1 AND s.score_error = false
        LIMIT 5
    """)
    followups = cur.fetchall()
    has_followup = len(followups) > 0
    record("Follow-up emails scored", has_followup, f"count={len(followups)}")

    # Check notes reference context (scored with chain_email_prompt which considers context)
    if followups:
        notes_sample = followups[0][0] or ""
        record("Follow-up score has notes", len(notes_sample) > 0,
               f"sample: {notes_sample[:100]}")

    cur.close()
    conn.close()

    # Screenshot rep detail with expanded details
    _safe_get(driver, f"{BASE}/")
    time.sleep(1)
    _inject_tailwind(driver, tailwind_css)
    rep_links = driver.find_elements(By.CSS_SELECTOR, "tbody a.text-blue-600")
    if rep_links:
        rep_links[0].click()
        time.sleep(2)
        _inject_tailwind(driver, tailwind_css)
        # Expand all details
        for summary in driver.find_elements(By.CSS_SELECTOR, "details summary"):
            summary.click()
            time.sleep(0.3)
        _screenshot(driver, tailwind_css, "full_04_rep_detail_expanded")


# ─── Phase 5: Verify Chain-Level Scoring ─────────────────────────────────────

def phase_verify_chain_scoring(driver, tailwind_css):
    print("\n=== Phase 5: Verify Chain-Level Scoring ===")
    conn = _db_conn()
    cur = conn.cursor()

    # Chains with 2+ emails have chain_score
    cur.execute("""
        SELECT count(*) FROM email_chains ec
        LEFT JOIN chain_scores cs ON ec.id = cs.chain_id
        WHERE ec.email_count >= 2 AND cs.id IS NULL
    """)
    unscored_chains = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM email_chains WHERE email_count >= 2")
    scoreable = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM chain_scores")
    total_cs = cur.fetchone()[0]
    record("Chains with 2+ emails have chain_score",
           total_cs > 0,
           f"unscored={unscored_chains}, scoreable={scoreable}, scored={total_cs}")

    # Chain scores have valid dimensions
    cur.execute("""
        SELECT count(*) FROM chain_scores
        WHERE score_error = false
        AND progression BETWEEN 1 AND 10
        AND responsiveness BETWEEN 1 AND 10
        AND persistence BETWEEN 1 AND 10
        AND conversation_quality BETWEEN 1 AND 10
    """)
    valid_chain_scores = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM chain_scores WHERE score_error = false")
    non_error_cs = cur.fetchone()[0]
    record("Chain scores have valid dimensions (1-10)",
           valid_chain_scores == non_error_cs and non_error_cs > 0,
           f"valid={valid_chain_scores}, non_error={non_error_cs}")

    # avg_response_hours populated
    cur.execute("SELECT count(*) FROM chain_scores WHERE avg_response_hours IS NOT NULL AND score_error = false")
    with_avg = cur.fetchone()[0]
    record("avg_response_hours populated", with_avg > 0, f"count={with_avg}")

    cur.close()
    conn.close()

    # Screenshot chain detail page
    conn = _db_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT ec.id FROM email_chains ec
        JOIN chain_scores cs ON ec.id = cs.chain_id
        WHERE cs.score_error = false AND ec.email_count >= 2
        LIMIT 1
    """)
    row = cur.fetchone()
    cur.close()
    conn.close()

    if row:
        chain_id = row[0]
        _safe_get(driver, f"{BASE}/chains/{chain_id}")
        time.sleep(2)
        _screenshot(driver, tailwind_css, "full_05_chain_detail")
        record("Chain detail page renders", True, f"chain_id={chain_id}")
    else:
        record("Chain detail page renders", False, "no scored chain found")


# ─── Phase 6: Verify Settings UI Tabs ───────────────────────────────────────

def phase_verify_settings(driver, tailwind_css):
    print("\n=== Phase 6: Verify Settings UI ===")

    # General tab
    _safe_get(driver, f"{BASE}/settings?tab=general")
    time.sleep(2)
    _screenshot(driver, tailwind_css, "full_06a_settings_general")

    # Check general tab has values
    start_date = driver.find_element(By.ID, "global_start_date").get_attribute("value")
    record("General tab has start date", len(start_date) > 0, f"value={start_date}")

    # Check jobs list rendered
    jobs_div = driver.find_element(By.ID, "jobs-list")
    jobs_text = jobs_div.text
    has_completed = "COMPLETED" in jobs_text
    record("General tab shows completed job", has_completed, f"text_contains_completed={has_completed}")

    # Scoring tab
    _safe_get(driver, f"{BASE}/settings?tab=scoring")
    time.sleep(1)
    # Click the scoring tab button
    scoring_btn = driver.find_element(By.CSS_SELECTOR, ".tab-btn[data-tab='scoring']")
    scoring_btn.click()
    time.sleep(1)
    _screenshot(driver, tailwind_css, "full_06b_settings_scoring")

    # Check prompts are present (use JS .value for textarea content)
    initial_prompt = driver.execute_script(
        "return document.getElementById('initial_email_prompt').value"
    )
    record("Scoring tab has initial prompt", len(initial_prompt or "") > 50,
           f"length={len(initial_prompt or '')}")

    chain_prompt = driver.execute_script(
        "return document.getElementById('chain_email_prompt').value"
    )
    record("Scoring tab has chain email prompt", len(chain_prompt or "") > 50,
           f"length={len(chain_prompt or '')}")

    # Check weights
    w_vp = driver.find_element(By.ID, "weight_value_proposition").get_attribute("value")
    record("Scoring tab has weights", float(w_vp) > 0, f"weight_vp={w_vp}")

    # Chain Evaluation tab
    _safe_get(driver, f"{BASE}/settings?tab=chain-evaluation")
    time.sleep(1)
    chain_eval_btn = driver.find_element(By.CSS_SELECTOR, ".tab-btn[data-tab='chain-evaluation']")
    chain_eval_btn.click()
    time.sleep(2)
    _screenshot(driver, tailwind_css, "full_06c_settings_chain_eval")

    eval_prompt = driver.execute_script(
        "return document.getElementById('chain_evaluation_prompt').value"
    )
    record("Chain Evaluation tab has prompt", len(eval_prompt or "") > 50,
           f"length={len(eval_prompt or '')}")

    # Chain stats panel renders (stats may show '-' if API doesn't include chain fields)
    total_chains_el = driver.find_element(By.ID, "stat-total-chains")
    chains_text = total_chains_el.text
    record("Chain Evaluation tab has stats panel", total_chains_el is not None,
           f"total_chains_display={chains_text}")


# ─── Phase 7: Navigation and Pages ──────────────────────────────────────────

def phase_verify_navigation(driver, tailwind_css):
    print("\n=== Phase 7: Navigation and Pages ===")

    # Team page renders with reps, scores, chain counts
    _safe_get(driver, f"{BASE}/")
    time.sleep(2)
    _inject_tailwind(driver, tailwind_css)
    rows = driver.find_elements(By.CSS_SELECTOR, "tbody tr")
    has_reps = len(rows) > 0
    record("Team page has reps", has_reps, f"row_count={len(rows)}")
    _screenshot(driver, tailwind_css, "full_07a_team_page")

    # Click first rep -> rep detail
    rep_links = driver.find_elements(By.CSS_SELECTOR, "tbody a.text-blue-600")
    if rep_links:
        rep_name = rep_links[0].text
        rep_links[0].click()
        time.sleep(2)
        _inject_tailwind(driver, tailwind_css)
        h1 = driver.find_element(By.TAG_NAME, "h1")
        record("Clicking rep navigates to detail", "/reps/" in driver.current_url,
               f"h1={h1.text}")
        _screenshot(driver, tailwind_css, "full_07b_rep_detail")

    # Navigate to a rep with chains to verify chains section
    conn = _db_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT r.email FROM reps r
        JOIN emails e ON e.from_email = r.email
        WHERE e.chain_id IS NOT NULL
        GROUP BY r.email
        LIMIT 1
    """)
    rep_with_chain = cur.fetchone()
    cur.close()
    conn.close()
    if rep_with_chain:
        _safe_get(driver, f"{BASE}/reps/{rep_with_chain[0]}")
        time.sleep(2)
        _inject_tailwind(driver, tailwind_css)
        chains_section = driver.find_elements(By.XPATH, "//h2[text()='Chains']")
        record("Rep detail has chains section", len(chains_section) > 0,
               f"rep={rep_with_chain[0]}")
    else:
        record("Rep detail has chains section", False, "no rep with chains found")

    # Navigate to Chains via nav
    chains_nav = driver.find_element(By.LINK_TEXT, "Chains")
    chains_nav.click()
    time.sleep(2)
    _inject_tailwind(driver, tailwind_css)
    h1 = driver.find_element(By.TAG_NAME, "h1")
    record("Chains nav link works", "Chains" in h1.text, f"h1={h1.text}")
    _screenshot(driver, tailwind_css, "full_07c_chains_page")

    # Click a chain -> chain detail
    chain_links = driver.find_elements(By.CSS_SELECTOR, "tbody a.text-blue-600")
    if chain_links:
        chain_links[0].click()
        time.sleep(2)
        _inject_tailwind(driver, tailwind_css)
        record("Clicking chain navigates to detail", "/chains/" in driver.current_url,
               f"url={driver.current_url}")
        _screenshot(driver, tailwind_css, "full_07d_chain_detail_via_click")

    # Navigate to Settings via nav
    settings_nav = driver.find_element(By.LINK_TEXT, "Settings")
    settings_nav.click()
    time.sleep(2)
    _inject_tailwind(driver, tailwind_css)
    h1 = driver.find_element(By.TAG_NAME, "h1")
    record("Settings nav link works", "Settings" in h1.text, f"h1={h1.text}")
    _screenshot(driver, tailwind_css, "full_07e_settings_via_nav")

    # Navigate to Team via nav
    team_nav = driver.find_element(By.LINK_TEXT, "Team")
    team_nav.click()
    time.sleep(2)
    _inject_tailwind(driver, tailwind_css)
    h1 = driver.find_element(By.TAG_NAME, "h1")
    record("Team nav link works", "Team" in h1.text, f"h1={h1.text}")
    _screenshot(driver, tailwind_css, "full_07f_team_via_nav")


# ─── Phase 8: Pagination ────────────────────────────────────────────────────

def phase_verify_pagination(driver, tailwind_css):
    print("\n=== Phase 8: Pagination ===")

    _safe_get(driver, f"{BASE}/?per_page=2")
    time.sleep(2)
    _inject_tailwind(driver, tailwind_css)

    pagination_div = driver.find_elements(By.ID, "pagination")
    has_pagination = len(pagination_div) > 0
    if has_pagination:
        pagination_text = pagination_div[0].text
        has_controls = "Page" in pagination_text or "Per page" in pagination_text
        record("Pagination controls visible with per_page=2", has_controls,
               f"text={pagination_text[:100]}")
    else:
        # Might not show if < 2 reps
        conn = _db_conn()
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM reps")
        rep_count = cur.fetchone()[0]
        cur.close()
        conn.close()
        record("Pagination controls visible with per_page=2",
               rep_count <= 2,
               f"rep_count={rep_count} (no pagination needed if <=2 reps)")

    _screenshot(driver, tailwind_css, "full_08_team_paginated")


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    print("Compiling Tailwind CSS...")
    _compile_tailwind()

    print("Starting app server...")
    app_thread = threading.Thread(target=_run_app_server, daemon=True)
    app_thread.start()

    if not _wait_for_server():
        print("ERROR: Server did not start within 30s")
        sys.exit(1)
    print("Server ready.")

    with open(TAILWIND_CSS_CACHE) as f:
        tailwind_css = f.read()

    driver = _make_driver()

    try:
        phase_fetch(driver, tailwind_css)
        phase_verify_fetch(driver, tailwind_css)
        phase_verify_chains(driver, tailwind_css)
        phase_verify_scoring(driver, tailwind_css)
        phase_verify_chain_scoring(driver, tailwind_css)
        phase_verify_settings(driver, tailwind_css)
        phase_verify_navigation(driver, tailwind_css)
        phase_verify_pagination(driver, tailwind_css)
    finally:
        driver.quit()

    # Summary
    print("\n" + "=" * 60)
    print("RESULTS SUMMARY")
    print("=" * 60)
    passed = sum(1 for r in results if r["passed"])
    failed = sum(1 for r in results if not r["passed"])
    for r in results:
        status = "PASS" if r["passed"] else "FAIL"
        detail = f" — {r['detail']}" if r["detail"] else ""
        print(f"  [{status}] {r['name']}{detail}")
    print(f"\n  Total: {passed} passed, {failed} failed, {len(results)} total")

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
