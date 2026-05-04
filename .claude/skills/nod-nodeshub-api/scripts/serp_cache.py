"""Shared SERP disk cache for SEO skills.

Saves full API responses to data/serp-cache/{gl}-{hl}/{keyword_slug}.json.
Any skill can call search_cached() instead of client.search() to avoid
re-fetching the same keyword multiple times across different runs.

TTL: 24 hours by default. Pass ttl_hours=0 to disable expiry.
"""

import json
import re
import time
from pathlib import Path

DEFAULT_TTL_HOURS = 24

# Anchored to project root (4 levels up from this file)
_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_CACHE_DIR = _PROJECT_ROOT / "output" / "data" / "serp-cache"


def _slug(keyword: str) -> str:
    """Normalize keyword to a safe, readable filename (max 100 chars)."""
    return re.sub(r"[^\w\s-]", "", keyword.lower().strip()).replace(" ", "_")[:100]


def _path(keyword: str, gl: str, hl: str) -> Path:
    return _CACHE_DIR / f"{gl}-{hl}" / f"{_slug(keyword)}.json"


def get(keyword: str, gl: str, hl: str, ttl_hours: float = DEFAULT_TTL_HOURS):
    """Return cached SERP response dict, or None if missing/expired."""
    p = _path(keyword, gl, hl)
    if not p.exists():
        return None
    if ttl_hours > 0:
        age_hours = (time.time() - p.stat().st_mtime) / 3600
        if age_hours > ttl_hours:
            return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def put(keyword: str, gl: str, hl: str, serp_data: dict) -> None:
    """Save SERP response to cache."""
    p = _path(keyword, gl, hl)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(serp_data, ensure_ascii=False), encoding="utf-8")


def search_cached(client, keyword: str, gl: str, hl: str,
                  ttl_hours: float = DEFAULT_TTL_HOURS):
    """Fetch SERP with cache — check disk first, call API on miss, then save.

    Returns (serp_data, from_cache).
    """
    cached = get(keyword, gl, hl, ttl_hours)
    if cached is not None:
        return cached, True
    result = client.search(keyword, gl=gl, hl=hl)
    put(keyword, gl, hl, result)
    return result, False
