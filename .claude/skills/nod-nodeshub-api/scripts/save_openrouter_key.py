#!/usr/bin/env python3
"""
Save OpenRouter API key to .claude/settings.local.json.

Usage:
    python3 save_openrouter_key.py YOUR_API_KEY
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from openrouter_client import save_openrouter_key, OpenRouterClient, OpenRouterError

if len(sys.argv) < 2 or not sys.argv[1].strip():
    print("Usage: python3 save_openrouter_key.py YOUR_API_KEY")
    print()
    print("Get your key at https://openrouter.ai/keys")
    sys.exit(1)

api_key = sys.argv[1].strip()
save_openrouter_key(api_key)

# Verify with a simple test
try:
    client = OpenRouterClient(api_key=api_key)
    response = client.chat("Say OK", max_tokens=5)
    print(f"Test response: {response.strip()}")
    print("Setup OK.")
except OpenRouterError as e:
    print(f"Key saved but verification failed: {e}")
    sys.exit(1)
