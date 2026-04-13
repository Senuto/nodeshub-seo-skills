#!/usr/bin/env python3
"""
SERPdata CLI — Extract Google SERP results via NodesHub API.

Usage:
    python3 serpdata.py "keyword" --gl us --hl en [--device desktop] [--raw]
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from client import NodeshubClient, NodeshubError


def _get_snippets(snippets):
    """Detect present SERP features from snippets dict."""
    features = []
    if not snippets:
        return features
    feature_checks = {
        "ai_overview": "AI Overview",
        "ads": "Ads",
        "answer_box": "Answer Box",
        "people_also_ask": "People Also Ask",
        "videos_pack": "Videos",
        "related_searches": "Related Searches",
        "knowledge_panel_right": "Knowledge Panel",
        "local_pack": "Local Pack",
        "top_stories": "Top Stories",
        "perspectives": "Perspectives",
        "perspectives_carousel": "Perspectives Carousel",
        "shopping_results": "Shopping",
        "image_pack": "Images",
    }
    for key, name in feature_checks.items():
        val = snippets.get(key)
        if val and val != [] and val != {}:
            features.append(name)
    return features


def main():
    parser = argparse.ArgumentParser(description="Extract SERP results via NodesHub SERPdata API")
    parser.add_argument("keyword", help="Search phrase")
    parser.add_argument("--gl", default="us", help="Country code (default: us)")
    parser.add_argument("--hl", default="en", help="Language code (default: en)")
    parser.add_argument("--device", choices=["desktop", "mobile"], help="Device type")
    parser.add_argument("--raw", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    try:
        client = NodeshubClient()
        result = client.search(args.keyword, gl=args.gl, hl=args.hl, device=args.device)

        if args.raw:
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return

        # Parse response: data.results.organic_results / data.results.snippets
        data = result.get("data", {})
        results = data.get("results", {})
        organic = results.get("organic_results", [])
        snippets = results.get("snippets", {})
        total = data.get("total_results_count", "?")

        print(f"Keyword: {results.get('query', args.keyword)}")
        print(f"Results: {total}")
        print(f"Response time: {result.get('totalResponseTime', '?')}ms")
        print()

        # SERP Features
        features = _get_snippets(snippets)
        if features:
            print(f"SERP Features: {', '.join(features)}")
            print()

        # Top organic results
        if organic:
            print(f"Top {min(len(organic), 10)} organic results:")
            for r in organic[:10]:
                pos = r.get("pos", r.get("global_pos", "?"))
                title = r.get("title", "No title")
                url = r.get("url", r.get("link", ""))
                domain = r.get("domain", "")
                print(f"  {pos}. {title}")
                print(f"     {url}")
            print()

        # Related searches
        related = snippets.get("related_searches", {})
        queries = related.get("queries", []) if isinstance(related, dict) else []
        if queries:
            print("Related Searches:")
            for q in queries[:8]:
                if isinstance(q, dict):
                    print(f"  - {q.get('query', q.get('text', q))}")
                else:
                    print(f"  - {q}")
            print()

        # AI Overview
        ai = snippets.get("ai_overview", {})
        if ai and isinstance(ai, dict):
            text = ai.get("content_text", "")
            if text:
                print("AI Overview:")
                print(f"  {text[:300]}{'...' if len(text) > 300 else ''}")
                print()

    except NodeshubError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
