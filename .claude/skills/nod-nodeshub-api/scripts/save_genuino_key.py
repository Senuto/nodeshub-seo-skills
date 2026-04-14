#!/usr/bin/env python3
"""
Save Genuino API key to .claude/settings.local.json.

Usage:
    python3 save_genuino_key.py YOUR_API_KEY
"""

import json
import os
import sys
import urllib.request
from pathlib import Path

_SETTINGS_PATH = Path(".claude/settings.local.json")


def save_genuino_key(api_key):
    """Save Genuino API key to .claude/settings.local.json in repo."""
    if _SETTINGS_PATH.is_file():
        try:
            data = json.loads(_SETTINGS_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            data = {}
    else:
        _SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        data = {}

    if "env" not in data:
        data["env"] = {}
    data["env"]["GENUINO_API_KEY"] = api_key

    _SETTINGS_PATH.write_text(json.dumps(data, indent=2) + "\n")
    print(f"Saved API key to {_SETTINGS_PATH}")


if len(sys.argv) < 2 or not sys.argv[1].strip():
    print("Usage: python3 save_genuino_key.py YOUR_API_KEY")
    print()
    print("Get your key at https://genuino.ai")
    sys.exit(1)

api_key = sys.argv[1].strip()
save_genuino_key(api_key)

# Verify the key works
try:
    req = urllib.request.Request("https://api.genuino.ai/v1/health/basic")
    req.add_header("X-API-Key", api_key)
    req.add_header("User-Agent", "genuino-claude-skill/0.1")
    resp = urllib.request.urlopen(req, timeout=10)
    data = json.loads(resp.read())
    print(f"Status: {data['status']}")
    print(f"Message: {data['message']}")
    print("Setup OK.")
except Exception as e:
    print(f"Key saved but verification failed: {e}")
    print("Check if the key is correct.")
    sys.exit(1)
