import hashlib
from pathlib import Path

from starlette.templating import Jinja2Templates

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _static_url(filename: str) -> str:
    """Return /static/{filename}?v={hash} for cache-busting."""
    filepath = STATIC_DIR / filename
    if filepath.exists():
        digest = hashlib.md5(filepath.read_bytes()).hexdigest()[:8]
        return f"/static/{filename}?v={digest}"
    return f"/static/{filename}"


templates.env.globals["static_url"] = _static_url
