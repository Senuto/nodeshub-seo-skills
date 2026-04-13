#!/usr/bin/env python3
"""
Query Fan-out CLI — Expand keywords via NodesHub API.

Usage:
    python3 fanout.py "keyword" --hl en --mode standard [--questions] [--topic-leaders] [--raw]
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from client import NodeshubClient, NodeshubError


def main():
    parser = argparse.ArgumentParser(description="Expand keywords via NodesHub Query Fan-out API")
    parser.add_argument("keyword", help="Base keyword to expand")
    parser.add_argument("--hl", default="en", help="Language code (default: en)")
    parser.add_argument("--mode", choices=["standard", "reasoning"], default="standard",
                        help="standard (7.5 tokens) or reasoning (30 tokens)")
    parser.add_argument("--questions", action="store_true", default=True,
                        help="Include question-based queries (default: true)")
    parser.add_argument("--no-questions", action="store_false", dest="questions")
    parser.add_argument("--topic-leaders", action="store_true", default=False,
                        help="Include topic leader queries")
    parser.add_argument("--reasoning", action="store_true", default=False,
                        help="Include reasoning explanation in output")
    parser.add_argument("--raw", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    try:
        client = NodeshubClient()
        result = client.query_fanout(
            args.keyword,
            hl=args.hl,
            mode=args.mode,
            add_questions=args.questions,
            add_topic_leaders=args.topic_leaders,
            include_reasoning=args.reasoning,
        )

        if args.raw:
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return

        # Pretty summary
        print(f"Keyword: {args.keyword}")
        print(f"Mode: {args.mode} ({7.5 if args.mode == 'standard' else 30} tokens)")
        print()

        data = result if isinstance(result, dict) else {}

        # Print whatever structure the API returns
        for key, value in data.items():
            if key in ("success", "totalResponseTime"):
                continue
            if isinstance(value, list):
                print(f"{key} ({len(value)}):")
                for item in value:
                    if isinstance(item, dict):
                        print(f"  - {item.get('query', item.get('keyword', json.dumps(item)))}")
                    else:
                        print(f"  - {item}")
                print()
            elif isinstance(value, dict):
                print(f"{key}:")
                for k, v in value.items():
                    if isinstance(v, list):
                        print(f"  {k} ({len(v)}):")
                        for item in v[:10]:
                            if isinstance(item, dict):
                                print(f"    - {item.get('query', item.get('keyword', json.dumps(item)))}")
                            else:
                                print(f"    - {item}")
                    else:
                        print(f"  {k}: {v}")
                print()

    except NodeshubError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
