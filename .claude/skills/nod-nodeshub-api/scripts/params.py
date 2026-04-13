#!/usr/bin/env python3
"""
List available countries (gl) or languages (hl) for NodesHub API.

Usage:
    python3 params.py countries
    python3 params.py languages
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from client import NodeshubClient, NodeshubError


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("countries", "languages"):
        print("Usage: python3 params.py <countries|languages>")
        sys.exit(1)

    try:
        client = NodeshubClient()
        if sys.argv[1] == "countries":
            data = client.get_countries()
        else:
            data = client.get_languages()
        print(json.dumps(data, indent=2, ensure_ascii=False))
    except NodeshubError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
