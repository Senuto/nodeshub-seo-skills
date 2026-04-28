#!/usr/bin/env python3
"""
Keyword Expander — Expand seed keywords and organize into clusters.

Usage:
    python3 expand_keywords.py "keyword" --hl en --mode standard
    python3 expand_keywords.py "kw1" "kw2" --hl en --mode standard --output keywords.json
"""

import argparse
import json
import os
import sys
from pathlib import Path

# Import shared client
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'nod-nodeshub-api' / 'scripts'))
from client import NodeshubClient, NodeshubError



def expand_keyword(client, keyword, hl, mode, add_questions, add_topic_leaders):
    """Expand a single keyword via Query Fan-out."""
    result = client.query_fanout(
        keyword=keyword,
        hl=hl,
        mode=mode,
        add_questions=add_questions,
        add_topic_leaders=add_topic_leaders,
        include_reasoning=(mode == "reasoning"),
    )

    cost = 7.5 if mode == "standard" else 30

    return {
        "seed_keyword": keyword,
        "hl": hl,
        "mode": mode,
        "tokens_used": cost,
        "raw_response": result,
    }


def main():
    parser = argparse.ArgumentParser(description="Expand keywords via NodesHub Query Fan-out API")
    parser.add_argument("keywords", nargs="+", help="Seed keywords to expand")
    parser.add_argument("--hl", default="en", help="Language code (default: en)")
    parser.add_argument("--mode", choices=["standard", "reasoning"], default="standard",
                        help="standard (7.5 tokens) or reasoning (30 tokens)")
    parser.add_argument("--questions", action="store_true", default=True,
                        help="Include question queries (default: true)")
    parser.add_argument("--no-questions", action="store_false", dest="questions")
    parser.add_argument("--topic-leaders", action="store_true", default=False,
                        help="Include topic leader queries")
    parser.add_argument("--output", "-o", help="Save JSON output to file")
    args = parser.parse_args()



    token_cost = len(args.keywords) * (7.5 if args.mode == "standard" else 30)
    print(f"Expanding {len(args.keywords)} keyword(s) in {args.mode} mode", file=sys.stderr)
    print(f"Estimated cost: {token_cost} tokens", file=sys.stderr)

    try:
        client = NodeshubClient()

        # Check balance first
        balance = client.get_balance()
        left = balance.get("left", 0)
        if isinstance(left, (int, float)) and left < token_cost:
            print(f"Warning: Balance ({left} tokens) may be insufficient for this operation ({token_cost} tokens)", file=sys.stderr)

        results = []
        total_tokens = 0

        for kw in args.keywords:
            print(f"Expanding: {kw}...", file=sys.stderr)
            expansion = expand_keyword(client, kw, args.hl, args.mode, args.questions, args.topic_leaders)
            results.append(expansion)
            total_tokens += expansion["tokens_used"]

        output = {
            "total_keywords": len(results),
            "total_tokens_used": total_tokens,
            "mode": args.mode,
            "hl": args.hl,
            "expansions": results,
        }

        json_output = json.dumps(output, indent=2, ensure_ascii=False)

        if args.output:
            output_path = Path(args.output)
            if output_path.is_dir() or args.output.endswith(("/", os.sep)):
                os.makedirs(output_path, exist_ok=True)
                safe_name = args.keywords[0].replace(" ", "_").replace("/", "_")[:30]
                output_path = output_path / f"keywords_{safe_name}_{args.hl}.json"
            else:
                os.makedirs(output_path.parent or Path("."), exist_ok=True)
            output_path.write_text(json_output)
            print(f"Saved to {output_path}", file=sys.stderr)
        else:
            print(json_output)

        print(f"Done. Total tokens used: {total_tokens}", file=sys.stderr)

    except NodeshubError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
