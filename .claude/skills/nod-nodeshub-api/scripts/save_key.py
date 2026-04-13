#!/usr/bin/env python3
"""
Save NodesHub API key to .claude/settings.local.json.

Usage:
    python3 save_key.py YOUR_API_KEY
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from client import save_key, NodeshubClient, NodeshubError

if len(sys.argv) < 2 or not sys.argv[1].strip():
    print("Usage: python3 save_key.py YOUR_API_KEY")
    print()
    print("Get your key at https://nodeshub.io (API Playground section)")
    sys.exit(1)

api_key = sys.argv[1].strip()
save_key(api_key)

# Verify the key works
try:
    client = NodeshubClient(api_key=api_key)
    balance = client.get_balance()
    left = balance.get("left", "?")
    limit = balance.get("limit", "?")
    print(f"Balance: {left} / {limit} tokens")
    print("Setup OK.")
except NodeshubError as e:
    print(f"Key saved but verification failed: {e}")
    print("Check if the key is correct.")
    sys.exit(1)
