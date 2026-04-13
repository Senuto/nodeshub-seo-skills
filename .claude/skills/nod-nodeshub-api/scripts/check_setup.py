#!/usr/bin/env python3
"""Verify NodesHub API setup — checks key exists and tests connectivity."""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from client import NodeshubClient, NodeshubError

try:
    client = NodeshubClient()
    print(f"API Key: {client.api_key[:8]}...")
    balance = client.get_balance()
    limit = balance.get("limit", "?")
    left = balance.get("left", "?")
    print(f"Balance: {left} / {limit} tokens")
    print("Setup OK.")
except NodeshubError as e:
    print(f"Connection failed: {e}")
    sys.exit(1)
