"""
NodesHub API Client — shared module for all NodesHub skills.

Usage:
    from client import NodeshubClient
    client = NodeshubClient()
    results = client.search("keyword", gl="us", hl="en")
"""

import json
import os
import sys
import time
import urllib.request
import urllib.parse
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

BASE_URL = "https://api.serpdata.io/v1"

# Order: repo .claude/settings.local.json first, then root (legacy), then user home
_REPO_CLAUDE = Path(__file__).resolve().parents[3]  # .claude/
_SETTINGS_CANDIDATES = [
    _REPO_CLAUDE / "settings.local.json",
    Path(__file__).resolve().parents[4] / "settings.local.json",  # repo root (legacy)
    Path.home() / ".claude" / "settings.local.json",
    Path.home() / ".claude" / "settings.json",
]


def _load_key_from_settings():
    """Try to read NODESHUB_API_KEY from settings files."""
    for path in _SETTINGS_CANDIDATES:
        if path.is_file():
            try:
                data = json.loads(path.read_text())
                key = data.get("env", {}).get("NODESHUB_API_KEY")
                if key:
                    return key, path
            except (json.JSONDecodeError, OSError):
                continue
    return None, None


def save_key(api_key):
    """Save API key to .claude/settings.local.json in repo."""
    settings_path = _SETTINGS_CANDIDATES[0]

    if settings_path.is_file():
        try:
            data = json.loads(settings_path.read_text())
        except (json.JSONDecodeError, OSError):
            data = {}
    else:
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        data = {}

    if "env" not in data:
        data["env"] = {}
    data["env"]["NODESHUB_API_KEY"] = api_key

    settings_path.write_text(json.dumps(data, indent=2) + "\n")
    print(f"Saved API key to {settings_path}")


def _missing_key_message():
    """Print instructions for providing the API key and exit."""
    settings_path = _SETTINGS_CANDIDATES[0]
    print("NODESHUB_API_KEY not found.")
    print()
    print("Option 1 — Save key via script:")
    print(f"  python3 {Path(__file__).resolve().parent / 'save_key.py'} YOUR_API_KEY")
    print()
    print("Option 2 — Add manually to settings:")
    print(f"  File: {settings_path}")
    print('  Add: { "env": { "NODESHUB_API_KEY": "your-key" } }')
    print()
    print("Get your key at https://nodeshub.io (scroll to API Playground, click 'Copy to clipboard')")
    sys.exit(1)


class NodeshubError(Exception):
    """Base exception for NodesHub API errors."""
    def __init__(self, message, status_code=None, response_body=None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class NodeshubClient:
    """NodesHub API client using only stdlib (urllib)."""

    def __init__(self, api_key=None):
        self.api_key = api_key or os.environ.get("NODESHUB_API_KEY")

        # Try settings files if not in env
        if not self.api_key:
            self.api_key, source = _load_key_from_settings()
            if self.api_key and source:
                print(f"Using API key from {source}", file=sys.stderr)

        # Still no key — print instructions and exit
        if not self.api_key:
            _missing_key_message()

        self.base_url = BASE_URL

    def _request(self, endpoint, params=None, retries=3):
        """Make authenticated GET request to NodesHub API with retry on transient errors."""
        url = f"{self.base_url}{endpoint}"
        if params:
            # Remove None values
            params = {k: v for k, v in params.items() if v is not None}
            url += "?" + urllib.parse.urlencode(params)

        last_error = None
        for attempt in range(retries):
            req = urllib.request.Request(url)
            req.add_header("Authorization", f"Bearer {self.api_key}")
            req.add_header("User-Agent", "NodeshubClient/1.0")
            req.add_header("Accept", "application/json")

            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    result = json.loads(resp.read().decode("utf-8"))

                # Check for capacity limit in response body (API returns 200 with error inside)
                inner = result.get("data", {}).get("results", {})
                if isinstance(inner, dict) and inner.get("error_code") in ("CAPACITY_LIMIT", "CAP"):
                    retry_after = inner.get("retry_after", 2)
                    last_error = NodeshubError(
                        f"Server at capacity (attempt {attempt + 1}/{retries})",
                        status_code=408, response_body=json.dumps(result),
                    )
                    if attempt < retries - 1:
                        wait = max(retry_after, 2) * (attempt + 1)
                        print(f"  [retry in {wait}s — server at capacity]", flush=True)
                        time.sleep(wait)
                        continue
                    raise last_error

                return result

            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8") if e.fp else ""
                if e.code == 401:
                    raise NodeshubError(
                        "401 Unauthorized — invalid or expired API key. "
                        "Get a new one at https://nodeshub.io",
                        status_code=401, response_body=body,
                    )
                # Retry on transient errors: 408, 429, 5xx
                if e.code in (408, 429) or e.code >= 500:
                    last_error = NodeshubError(
                        f"HTTP {e.code}: {e.reason}\n{body}",
                        status_code=e.code, response_body=body,
                    )
                    if attempt < retries - 1:
                        wait = 3 * (attempt + 1)
                        print(f"  [retry in {wait}s — HTTP {e.code}]", flush=True)
                        time.sleep(wait)
                        continue
                raise NodeshubError(
                    f"HTTP {e.code}: {e.reason}\n{body}",
                    status_code=e.code, response_body=body,
                )
            except (urllib.error.URLError, TimeoutError) as e:
                reason = getattr(e, "reason", str(e))
                last_error = NodeshubError(f"Connection error: {reason}")
                if attempt < retries - 1:
                    wait = 3 * (attempt + 1)
                    print(f"  [retry in {wait}s — connection error]", flush=True)
                    time.sleep(wait)
                    continue

        raise last_error

    # ── SERPdata ──────────────────────────────────────────────

    def search(self, keyword, gl="us", hl="en", device=None):
        """
        Extract SERP results for a keyword.
        Cost: 1 token per request.

        Args:
            keyword: Search phrase
            gl: Country code (us, pl, de, uk, fr, ...)
            hl: Language code (en, pl, de, ...)
            device: "desktop" or "mobile" (optional)
        """
        return self._request("/search", {
            "keyword": keyword,
            "gl": gl,
            "hl": hl,
            "device": device,
        })

    def search_batch(self, keywords, gl="us", hl="en", device=None,
                     max_workers=4, on_result=None, on_error=None):
        """
        Fetch SERPs for multiple keywords concurrently.
        Cost: 1 token per keyword.

        Args:
            keywords: List of search phrases
            gl: Country code
            hl: Language code
            device: "desktop" or "mobile" (optional)
            max_workers: Number of concurrent threads (default: 4)
            on_result: Optional callback(keyword, result) called per success
            on_error: Optional callback(keyword, error) called per failure

        Returns:
            dict of {keyword: serp_result} for successful requests
        """
        results = {}
        errors = {}

        def _fetch(kw):
            return kw, self.search(kw, gl=gl, hl=hl, device=device)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_fetch, kw): kw for kw in keywords}
            for future in as_completed(futures):
                kw = futures[future]
                try:
                    _, result = future.result()
                    results[kw] = result
                    if on_result:
                        on_result(kw, result)
                except Exception as e:
                    errors[kw] = e
                    if on_error:
                        on_error(kw, e)

        return results

    # ── Query Fan-out ─────────────────────────────────────────

    def query_fanout(self, keyword, hl="en", mode="standard",
                     add_questions=True, add_topic_leaders=False,
                     include_reasoning=False):
        """
        Expand a keyword into related queries, questions, and topic leaders.
        Cost: 7.5 tokens (standard) / 30 tokens (reasoning).

        Args:
            keyword: Base keyword to expand
            hl: Language code
            mode: "standard" (faster/cheaper) or "reasoning" (better quality)
            add_questions: Include question-based queries
            add_topic_leaders: Include topic leader queries
            include_reasoning: Include reasoning explanation
        """
        return self._request("/query-fanout", {
            "keyword": keyword,
            "hl": hl,
            "mode": mode,
            "add_questions": str(add_questions).lower(),
            "add_topic_leaders": str(add_topic_leaders).lower(),
            "include_reasoning": str(include_reasoning).lower(),
        })

    # ── Intent Classifier (beta) ──────────────────────

    def classify_intent(self, keyword, gl="us", hl="en"):
        """
        Classify search intent for a keyword.
        Cost: 2 tokens per request.
        Status: Beta — may produce inaccurate results.
        """
        return self._request("/intent-classifier", {
            "keyword": keyword,
            "gl": gl,
            "hl": hl,
        })

    # ── Utility endpoints (free) ──────────────────────────────

    def get_balance(self):
        """Check remaining tokens. Cost: 0 tokens."""
        return self._request("/api-key/balance")

    def get_products(self):
        """List available plans. Cost: 0 tokens."""
        return self._request("/products")

    def get_countries(self):
        """List available country codes for gl param. Cost: 0 tokens."""
        return self._request("/google-params/gl")

    def get_languages(self):
        """List available language codes for hl param. Cost: 0 tokens."""
        return self._request("/google-params/hl")
