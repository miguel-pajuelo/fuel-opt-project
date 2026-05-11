from __future__ import annotations

from app.config import PROJECT_ROOT


STATIC_DIR = PROJECT_ROOT / "static"
INDEX_HTML_PATH = STATIC_DIR / "index.html"


def load_index_html() -> str:
    return INDEX_HTML_PATH.read_text(encoding="utf-8")


# Backwards-compatible placeholder for scripts/tests that import the former
# module-level HTML. Keep the actual file read lazy so packaged launchers can
# finish resolving FUELOPT_PROJECT_ROOT before the UI is loaded.
INDEX_HTML = ""
