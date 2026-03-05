# Visual Testing

Visual testing renders pages in a real browser and captures screenshots. Use it to verify layout, styling, and conditional UI elements after template or CSS changes.

## Prerequisites

- Google Chrome (`google-chrome-stable`)
- Python packages: `selenium`

```bash
pipenv install --dev selenium
```

Chrome is available via direct download if not already installed:

```bash
wget -q 'https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb' -O /tmp/chrome.deb
sudo dpkg -i /tmp/chrome.deb
sudo apt-get install -f -y
```

## How It Works

1. Create an in-memory SQLite database with the JSONB compiler patch (same as the test suite).
2. Insert seed data via ORM.
3. Override `get_db` on the FastAPI app and start uvicorn in a daemon thread.
4. Launch headless Chrome via Selenium and navigate to each page.
5. Resize the viewport to match the page's scroll height for a full-page capture.
6. Save screenshots as PNG files.

## Database Setup

The test suite's SQLite compatibility patches are required. Use `StaticPool` so all threads share one connection.

```python
import os
os.environ["AUTH_ENABLED"] = "FALSE"
os.environ["CURRENT_USER"] = "test"

from sqlalchemy import create_engine, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(element, compiler, **kw):
    return "JSON"


engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()
```

**Use `sqlite:///:memory:`** — not `sqlite:///file::memory:?cache=shared`. The latter creates a persistent file on disk named `file::memory:` and data accumulates across runs.

## Starting the Server

Run uvicorn in a daemon thread so the script can drive Chrome in the main thread.

```python
import threading
import time
import uvicorn

from app.database import get_db
from app.main import app

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _override_get_db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


app.dependency_overrides[get_db] = _override_get_db


def run_server():
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="error")


server_thread = threading.Thread(target=run_server, daemon=True)
server_thread.start()
time.sleep(2)
```

## Taking Screenshots

```python
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

chrome_options = Options()
chrome_options.add_argument("--headless=new")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--window-size=1440,900")
chrome_options.binary_location = "/usr/bin/google-chrome-stable"

driver = webdriver.Chrome(options=chrome_options)

urls = {
    "team": "http://127.0.0.1:8765/",
    "settings": "http://127.0.0.1:8765/settings",
}

for name, url in urls.items():
    driver.get(url)
    time.sleep(1)
    total_height = driver.execute_script("return document.body.scrollHeight")
    driver.set_window_size(1440, max(900, total_height + 200))
    time.sleep(0.5)
    driver.save_screenshot(f"/tmp/{name}.png")

driver.quit()
```

Key Selenium options:

| Flag | Purpose |
|------|---------|
| `--headless=new` | Run without a display server |
| `--no-sandbox` | Required when running as root or in containers |
| `--disable-dev-shm-usage` | Prevents `/dev/shm` memory issues in Docker |
| `--window-size=1440,900` | Set initial viewport; resized per page for full-height capture |

## Seed Data

Capture the primary keys of seed entities before closing the session used for insertion. SQLAlchemy expires attributes on commit, so accessing `obj.id` after `session.close()` raises `DetachedInstanceError`.

```python
rep = Rep(email="jane@example.com", display_name="Jane Doe")
db.add(rep)
db.commit()
db.refresh(rep)

# Capture before closing
rep_email = rep.email
db.close()

# Use the captured value in URLs
detail_url = f"http://127.0.0.1:8765/reps/{rep_email}"
```

## Reviewing Screenshots

Open the PNG files directly or use any image viewer. In CI, screenshots can be archived as build artifacts for manual review or fed into a visual diff tool.
