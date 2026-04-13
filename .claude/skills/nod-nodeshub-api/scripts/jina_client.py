"""
Jina Reader Client — fetch web pages as clean markdown.

Usage:
    from jina_client import JinaClient
    client = JinaClient()
    md = client.read_url("https://example.com/article")
    results = client.read_batch(["https://...", "https://..."], workers=3)
"""

import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

BASE_URL = "https://r.jina.ai"

_REPO_CLAUDE = Path(__file__).resolve().parents[3]
_SETTINGS_CANDIDATES = [
    _REPO_CLAUDE / "settings.local.json",
    Path(__file__).resolve().parents[4] / "settings.local.json",
    Path.home() / ".claude" / "settings.local.json",
    Path.home() / ".claude" / "settings.json",
]


def _load_jina_key():
    for path in _SETTINGS_CANDIDATES:
        if path.is_file():
            try:
                data = json.loads(path.read_text())
                key = data.get("env", {}).get("JINA_API_KEY")
                if key:
                    return key, path
            except (json.JSONDecodeError, OSError):
                continue
    return None, None


class JinaError(Exception):
    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.status_code = status_code


def clean_markdown(text, max_words=1500):
    """Remove noise from markdown: nav, menus, boilerplate, images."""
    lines = text.split("\n")
    cleaned = []
    skip_patterns = [
        r"^\s*\[.*\]\(.*\)\s*$",  # bare links
        r"^\s*!\[",  # images
        r"^\s*(Menu|Navigation|Footer|Copyright|Cookie|Privacy)",
        r"^\s*\|.*\|.*\|.*\|",  # tables with many columns (likely nav)
    ]
    for line in lines:
        if any(re.match(p, line, re.IGNORECASE) for p in skip_patterns):
            continue
        cleaned.append(line)

    result = "\n".join(cleaned).strip()

    # Truncate to max_words
    words = result.split()
    if len(words) > max_words:
        result = " ".join(words[:max_words]) + "\n\n[...truncated]"

    return result


class JinaClient:
    """Jina Reader API client — URL to clean markdown."""

    MIN_WORDS = 200  # skip pages with less content

    def __init__(self, api_key=None):
        self.api_key = api_key or os.environ.get("JINA_API_KEY")
        if not self.api_key:
            self.api_key, source = _load_jina_key()
            if self.api_key and source:
                print(f"Using Jina key from {source}", file=sys.stderr)

        # Works without key (20 RPM) but slower
        if not self.api_key:
            print("JINA_API_KEY not found — using free tier (20 RPM limit).", file=sys.stderr)

    def read_url(self, url, max_words=1500, retries=3):
        """Fetch a URL and return clean markdown.

        Args:
            url: Web page URL
            max_words: Max words to keep (default: 1500)
            retries: Number of retry attempts

        Returns:
            dict with keys: url, title, content, word_count, status
        """
        for attempt in range(retries):
            try:
                req_url = f"{BASE_URL}/{url}"
                req = urllib.request.Request(req_url)
                if self.api_key:
                    req.add_header("Authorization", f"Bearer {self.api_key}")
                req.add_header("X-Return-Format", "markdown")
                req.add_header("User-Agent", "JinaClient/1.0")

                with urllib.request.urlopen(req, timeout=30) as resp:
                    raw = resp.read().decode("utf-8")

                # Parse: first line is usually "Title: ..." or markdown
                title = ""
                content = raw
                lines = raw.split("\n", 5)
                for line in lines[:3]:
                    if line.startswith("Title:"):
                        title = line[6:].strip()
                    elif line.startswith("# "):
                        title = line[2:].strip()

                content = clean_markdown(content, max_words=max_words)
                word_count = len(content.split())

                return {
                    "url": url,
                    "title": title,
                    "content": content,
                    "word_count": word_count,
                    "status": "OK" if word_count >= self.MIN_WORDS else "SKIP",
                }

            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < retries - 1:
                    time.sleep(2 * (attempt + 1))
                    continue
                return {"url": url, "title": "", "content": "", "word_count": 0,
                        "status": f"ERROR_{e.code}"}
            except (urllib.error.URLError, OSError) as e:
                if attempt < retries - 1:
                    time.sleep(1 * (attempt + 1))
                    continue
                return {"url": url, "title": "", "content": "", "word_count": 0,
                        "status": f"ERROR: {e}"}

    def read_batch(self, urls, workers=3, max_words=1500, on_result=None):
        """Fetch multiple URLs concurrently.

        Args:
            urls: List of URLs
            workers: Concurrent threads (default: 3)
            max_words: Max words per page
            on_result: Optional callback(result_dict)

        Returns:
            list of result dicts, ordered by input
        """
        results = {}

        def _fetch(url):
            result = self.read_url(url, max_words=max_words)
            if on_result:
                on_result(result)
            return url, result

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(_fetch, url): url for url in urls}
            for future in as_completed(futures):
                url = futures[future]
                try:
                    _, result = future.result()
                    results[url] = result
                except Exception as e:
                    results[url] = {"url": url, "title": "", "content": "",
                                    "word_count": 0, "status": f"ERROR: {e}"}

        # Return in original order
        return [results.get(url, {"url": url, "status": "MISSING"}) for url in urls]

    def consolidate(self, results, max_words_per=1500):
        """Consolidate multiple results into a single markdown document.

        Args:
            results: List of result dicts from read_batch
            max_words_per: Max words per competitor in consolidated output

        Returns:
            dict with: consolidated_md, quality_report, ok_count, skip_count, error_count
        """
        ok_results = [r for r in results if r["status"] == "OK"]
        skip_results = [r for r in results if r["status"] == "SKIP"]
        error_results = [r for r in results if r["status"].startswith("ERROR")]

        # Build consolidated markdown
        parts = []
        for r in ok_results:
            words = r["content"].split()[:max_words_per]
            truncated = " ".join(words)
            parts.append(f"## {r['title'] or r['url']}\n\nSource: {r['url']}\n\n{truncated}\n")

        consolidated = "\n---\n\n".join(parts)

        # Quality report
        report_lines = []
        for r in results:
            status = r["status"]
            wc = r.get("word_count", 0)
            report_lines.append(f"{status:>10} | {wc:>5} words | {r['url']}")

        quality_report = "\n".join(report_lines)

        return {
            "consolidated_md": consolidated,
            "quality_report": quality_report,
            "ok_count": len(ok_results),
            "skip_count": len(skip_results),
            "error_count": len(error_results),
        }
