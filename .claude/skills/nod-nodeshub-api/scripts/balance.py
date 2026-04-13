#!/usr/bin/env python3
"""Check NodesHub API token balance."""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from client import NodeshubClient, NodeshubError

try:
    client = NodeshubClient()
    balance = client.get_balance()
    limit = balance.get("limit", "?")
    left = balance.get("left", "?")
    print(f"Balance: {left} / {limit} tokens remaining")
except NodeshubError as e:
    print(f"Error: {e}", file=sys.stderr)
    sys.exit(1)
