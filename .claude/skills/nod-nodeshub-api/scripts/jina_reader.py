"""
Jina Reader — fetch URL content as clean markdown via r.jina.ai.

Usage:
    from jina_reader import JinaReader
    reader = JinaReader()  # optional: JinaReader(api_key="jina_xxx")
    content = reader.fetch("https://example.com/page")
    results = reader.fetch_batch(["url1", "url2"], max_workers=3)
"""

import json
import os
import re
import sys
import time
import threading
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


JINA_READER_URL = "https://r.jina.ai/"


def _load_jina_key():
    """Try JINA_API_KEY from env, then from settings files."""
    key = os.environ.get("JINA_API_KEY")
    if key:
        return key

    candidates = [
        Path(__file__).resolve().parents[2] / "settings.local.json",
        Path(__file__).resolve().parents[3] / "settings.local.json",
        Path.home() / ".claude" / "settings.local.json",
        Path.home() / ".claude" / "settings.json",
    ]
    for path in candidates:
        if path.is_file():
            try:
                data = json.loads(path.read_text())
                key = data.get("env", {}).get("JINA_API_KEY")
                if key:
                    return key
            except (json.JSONDecodeError, OSError):
                continue
    return None


def _clean_markdown(text):
    """Remove navigation noise, menus, boilerplate from markdown."""
    lines = text.split("\n")
    cleaned = []
    skip_patterns = [
        r"^\s*\[.*\]\(.*\)\s*$",  # standalone links (navigation)
        r"^(menu|nav|footer|header|sidebar|cookie|copyright|©)",
        r"^\s*\|?\s*(home|about|contact|login|sign up|subscribe)\s*\|?",
        r"^!\[.*\]\(.*\)$",  # standalone images
    ]
    skip_re = re.compile("|".join(skip_patterns), re.IGNORECASE)

    consecutive_short = 0
    for line in lines:
        stripped = line.strip()
        # Skip empty lines at start
        if not cleaned and not stripped:
            continue
        # Skip navigation-like patterns
        if skip_re.match(stripped):
            continue
        # Track consecutive very short lines (likely nav items)
        if len(stripped) < 30 and not stripped.startswith("#"):
            consecutive_short += 1
            if consecutive_short > 5:
                continue
        else:
            consecutive_short = 0
        cleaned.append(line)

    return "\n".join(cleaned).strip()


class JinaReaderError(Exception):
    """Error fetching content via Jina Reader."""
    pass


class JinaReader:
    """Fetch web pages as clean markdown via Jina Reader API."""

    def __init__(self, api_key=None):
        self.api_key = api_key or _load_jina_key()
        self._rate_limit = threading.Semaphore(1)
        self._last_request = 0.0
        # Without API key: 20 RPM → 3s between requests
        # With API key: 200 RPM → 0.3s between requests
        self._min_interval = 0.35 if self.api_key else 3.5
        if not self.api_key:
            print("  Jina Reader: no API key (20 RPM limit). "
                  "Set JINA_API_KEY for 200 RPM.", file=sys.stderr)

    def _throttle(self):
        """Thread-safe rate limiting."""
        with self._rate_limit:
            elapsed = time.time() - self._last_request
            if elapsed < self._min_interval:
                time.sleep(self._min_interval - elapsed)
            self._last_request = time.time()

    def fetch(self, url, timeout=30, max_words=None):
        """
        Fetch a single URL and return clean markdown content.

        Args:
            url: URL to fetch
            timeout: Request timeout in seconds
            max_words: Truncate to N words (default: no limit)

        Returns:
            dict with keys: url, title, content, word_count, ok
        """
        self._throttle()

        target = f"{JINA_READER_URL}{url}"
        req = urllib.request.Request(target)
        req.add_header("Accept", "text/markdown")
        req.add_header("User-Agent", "NodeshubContentAuditor/1.0")
        if self.api_key:
            req.add_header("Authorization", f"Bearer {self.api_key}")
        # Ask Jina to skip non-content elements
        req.add_header("X-No-Cache", "true")

        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            return {"url": url, "title": "", "content": "", "word_count": 0,
                    "ok": False, "error": f"HTTP {e.code}"}
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            return {"url": url, "title": "", "content": "", "word_count": 0,
                    "ok": False, "error": str(e)}

        # Parse title from first markdown heading
        title = ""
        lines = raw.split("\n")
        for line in lines:
            if line.startswith("# "):
                title = line[2:].strip()
                break
            if line.startswith("Title:"):
                title = line[6:].strip()
                break

        content = _clean_markdown(raw)
        words = content.split()
        word_count = len(words)

        if max_words and word_count > max_words:
            content = " ".join(words[:max_words])
            word_count = max_words

        return {
            "url": url,
            "title": title,
            "content": content,
            "word_count": word_count,
            "ok": word_count >= 100,  # Less than 100 words = likely garbage
        }

    def fetch_batch(self, urls, max_workers=3, max_words=1500,
                    min_words=200, on_progress=None):
        """
        Fetch multiple URLs concurrently with rate limiting.

        Args:
            urls: List of URLs to fetch
            max_workers: Concurrent threads (default: 3)
            max_words: Max words per page (default: 1500)
            min_words: Skip pages with fewer words (default: 200)
            on_progress: Optional callback(done, total, url, ok)

        Returns:
            list of result dicts (only ok=True pages)
        """
        results = []
        done_count = 0

        def _fetch_one(url):
            return self.fetch(url, max_words=max_words)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_fetch_one, u): u for u in urls}
            for future in as_completed(futures):
                done_count += 1
                result = future.result()
                if result["ok"] and result["word_count"] >= min_words:
                    results.append(result)
                if on_progress:
                    on_progress(done_count, len(urls),
                                result["url"], result["ok"])

        return results
