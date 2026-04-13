"""
OpenRouter API Client — shared module for LLM operations across skills.

Usage:
    from openrouter_client import OpenRouterClient
    client = OpenRouterClient()
    response = client.chat("Name this cluster of keywords", model="google/gemini-2.5-flash-lite")
"""

import json
import os
import sys
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path

BASE_URL = "https://openrouter.ai/api/v1"

_REPO_CLAUDE = Path(__file__).resolve().parents[3]  # .claude/
_SETTINGS_CANDIDATES = [
    _REPO_CLAUDE / "settings.local.json",
    Path(__file__).resolve().parents[4] / "settings.local.json",
    Path.home() / ".claude" / "settings.local.json",
    Path.home() / ".claude" / "settings.json",
]


def _load_key_from_settings():
    """Try to read OPENROUTER_API_KEY from settings files."""
    for path in _SETTINGS_CANDIDATES:
        if path.is_file():
            try:
                data = json.loads(path.read_text())
                key = data.get("env", {}).get("OPENROUTER_API_KEY")
                if key:
                    return key, path
            except (json.JSONDecodeError, OSError):
                continue
    return None, None


def save_openrouter_key(api_key):
    """Save OpenRouter API key to .claude/settings.local.json in repo."""
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
    data["env"]["OPENROUTER_API_KEY"] = api_key

    settings_path.write_text(json.dumps(data, indent=2) + "\n")
    print(f"Saved OpenRouter API key to {settings_path}")


class OpenRouterError(Exception):
    def __init__(self, message, status_code=None, response_body=None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class OpenRouterClient:
    """OpenRouter API client using only stdlib."""

    DEFAULT_MODEL = "google/gemini-2.5-flash-lite"

    def __init__(self, api_key=None):
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY")

        if not self.api_key:
            self.api_key, source = _load_key_from_settings()
            if self.api_key and source:
                print(f"Using OpenRouter key from {source}", file=sys.stderr)

        if not self.api_key:
            print("OPENROUTER_API_KEY not found.", file=sys.stderr)
            print(f"Run: python3 {Path(__file__).resolve().parent / 'save_openrouter_key.py'} YOUR_KEY", file=sys.stderr)
            sys.exit(1)

        self.base_url = BASE_URL

    def chat(self, prompt, model=None, system=None, temperature=0.3, max_tokens=2000):
        """Send a chat completion request to OpenRouter.

        Args:
            prompt: User message
            model: Model ID (default: google/gemini-2.5-flash-lite)
            system: Optional system message
            temperature: Sampling temperature (0-1)
            max_tokens: Max response tokens

        Returns:
            Response text string
        """
        model = model or self.DEFAULT_MODEL

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(f"{self.base_url}/chat/completions", data=data)
        req.add_header("Authorization", f"Bearer {self.api_key}")
        req.add_header("Content-Type", "application/json")
        req.add_header("HTTP-Referer", "https://github.com/Senuto/nodeshub-seo-skills")

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                return result["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8") if e.fp else ""
            raise OpenRouterError(f"HTTP {e.code}: {body}", status_code=e.code, response_body=body)
        except urllib.error.URLError as e:
            raise OpenRouterError(f"Connection error: {e.reason}")
