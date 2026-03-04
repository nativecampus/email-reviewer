"""Take full-page screenshots of every UI route for visual review.

Starts the FastAPI app against the PostgreSQL database configured in .env,
launches headless Chrome via Selenium, and saves PNGs to /tmp.

Prerequisites:
    - PostgreSQL running with migrations applied and seed data loaded
    - google-chrome-stable installed
    - selenium installed (pipenv install --dev selenium)

Usage:
    pipenv run python -m scripts.visual_test
"""

import os
import threading
import time

os.environ.setdefault("AUTH_ENABLED", "FALSE")
os.environ.setdefault("CURRENT_USER", "test")

import uvicorn
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

from app.main import app

PORT = 8765
BASE = f"http://127.0.0.1:{PORT}"


def _run_server():
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="error")


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

    # Block the Tailwind CDN via CDP network interception so the blocking
    # <script> tag fails immediately instead of hanging the renderer.
    driver.execute_cdp_cmd("Network.enable", {})
    driver.execute_cdp_cmd(
        "Network.setBlockedURLs",
        {"urls": ["*cdn.tailwindcss.com*"]},
    )

    urls = {
        "leaderboard": f"{BASE}/",
        "rep_detail": f"{BASE}/reps/inderpalgill@nativecampusadvertising.com",
        "settings": f"{BASE}/settings",
    }

    for name, url in urls.items():
        print(f"  loading {name}...")
        driver.get(url)
        time.sleep(1)
        total_height = driver.execute_script("return document.body.scrollHeight")
        driver.set_window_size(1440, max(900, total_height + 200))
        time.sleep(0.5)
        path = f"/tmp/{name}.png"
        driver.save_screenshot(path)
        print(f"  saved {path}")

    driver.quit()


def main():
    server_thread = threading.Thread(target=_run_server, daemon=True)
    server_thread.start()
    time.sleep(2)

    print("Taking screenshots...")
    _take_screenshots()
    print("Done.")


if __name__ == "__main__":
    main()
