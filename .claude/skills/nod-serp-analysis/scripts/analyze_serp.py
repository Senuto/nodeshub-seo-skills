#!/usr/bin/env python3
"""
SERP Analyzer — Fetch and analyze SERP data for one or more keywords.

Usage:
    python3 analyze_serp.py "keyword" --gl us --hl en
    python3 analyze_serp.py "kw1" "kw2" "kw3" --gl us --hl en
    python3 analyze_serp.py "keyword" --gl us --hl en --output report.json
"""

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

# Import shared client
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'nod-nodeshub-api' / 'scripts'))
from client import NodeshubClient, NodeshubError
from report import render_section_wrapper, make_section_id, html_table, summary_card, badge



def analyze_single(client, keyword, gl, hl, device=None):
    """Fetch and analyze SERP for a single keyword."""
    raw = client.search(keyword, gl=gl, hl=hl, device=device)
    data = raw.get("data", {})
    results = data.get("results", {})
    organic = results.get("organic_results", [])
    snippets = results.get("snippets", {})

    # Extract domains
    domains = [r.get("domain", "") for r in organic if r.get("domain")]

    # Detect SERP features
    features = {}
    feature_keys = {
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
    for key, name in feature_keys.items():
        val = snippets.get(key)
        if val and val != {} and val != []:
            features[name] = val

    # Extract PAA questions
    paa = snippets.get("people_also_ask", {})
    paa_questions = []
    if isinstance(paa, dict) and paa.get("items"):
        paa_questions = [item.get("question", "") for item in paa["items"] if item.get("question")]
    elif isinstance(paa, list):
        paa_questions = [q.get("question", str(q)) if isinstance(q, dict) else str(q) for q in paa]

    # Related searches
    related = snippets.get("related_searches", {})
    related_queries = []
    if isinstance(related, dict):
        related_queries = related.get("queries", [])

    # AI Overview
    ai_overview = ""
    ai = snippets.get("ai_overview", {})
    if isinstance(ai, dict):
        ai_overview = ai.get("content_text", "")

    # Intent heuristic
    intent_signals = {"informational": 0, "commercial": 0, "transactional": 0, "navigational": 0}
    if "People Also Ask" in features:
        intent_signals["informational"] += 2
    if "Knowledge Panel" in features:
        intent_signals["informational"] += 1
    if "AI Overview" in features:
        intent_signals["informational"] += 1
    if "Shopping" in features:
        intent_signals["transactional"] += 3
    if "Local Pack" in features:
        intent_signals["transactional"] += 1
    if "Videos" in features:
        intent_signals["informational"] += 1
    if "Ads" in features:
        intent_signals["commercial"] += 2

    for r in organic[:5]:
        title = (r.get("title", "") or "").lower()
        if any(w in title for w in ["best", "top", "review", "vs", "comparison", "alternative"]):
            intent_signals["commercial"] += 1
        if any(w in title for w in ["buy", "price", "discount", "deal", "shop", "order"]):
            intent_signals["transactional"] += 1

    dominant_intent = max(intent_signals, key=intent_signals.get)
    domain_counts = Counter(domains)

    return {
        "keyword": keyword,
        "gl": gl,
        "hl": hl,
        "total_results": data.get("total_results_count", "?"),
        "response_time_ms": raw.get("totalResponseTime"),
        "organic_results": [
            {
                "pos": r.get("pos"),
                "title": r.get("title"),
                "url": r.get("url"),
                "domain": r.get("domain"),
                "description": r.get("description"),
            }
            for r in organic
        ],
        "organic_count": len(organic),
        "domains": domains,
        "domain_frequency": dict(domain_counts.most_common()),
        "unique_domains": len(set(domains)),
        "serp_features": list(features.keys()),
        "paa_questions": paa_questions,
        "related_searches": related_queries,
        "ai_overview": ai_overview[:500] if ai_overview else "",
        "dominant_intent": dominant_intent,
        "intent_signals": intent_signals,
    }


def render_report_section(data):
    """Convert SERP analysis data into an HTML report section."""
    from html import escape as e
    parts = []

    parts.append(summary_card([
        (e(str(data.get("keyword", ""))), "Keyword"),
        (e(str(data.get("dominant_intent", ""))).title(), "Intent"),
        (str(data.get("unique_domains", 0)), "Unique Domains"),
        (str(data.get("organic_count", 0)), "Organic Results"),
    ]))

    org = data.get("organic_results", [])
    if org:
        rows = [[str(r.get("pos", "")), e(str(r.get("title", "") or "")),
                 e(str(r.get("domain", "") or "")),
                 f'<a href="{e(str(r.get("url", "") or ""))}" target="_blank">'
                 f'{e(str(r.get("url", "") or "")[:60])}</a>']
                for r in org]
        parts.append("<h3>Organic Results</h3>")
        parts.append(html_table(["#", "Title", "Domain", "URL"], rows))

    features = data.get("serp_features", [])
    if features:
        badges_html = " ".join(badge(e(f), "info") for f in features)
        parts.append(f"<h3>SERP Features</h3>\n<p>{badges_html}</p>")

    paa = data.get("paa_questions", [])
    if paa:
        items = "".join(f"<li>{e(q)}</li>" for q in paa)
        parts.append(f"<h3>People Also Ask</h3>\n<ul>{items}</ul>")

    related = data.get("related_searches", [])
    if related:
        items = "".join(f"<li>{e(str(q))}</li>" for q in related)
        parts.append(f"<h3>Related Searches</h3>\n<ul>{items}</ul>")

    sid = make_section_id("serp-analysis")
    kw = e(str(data.get("keyword", "")))
    return render_section_wrapper(sid, "SERP Analysis", f"SERP Analysis: {kw}", "\n".join(parts))


def main():
    parser = argparse.ArgumentParser(description="Analyze SERP data via NodesHub API")
    parser.add_argument("keywords", nargs="+", help="Keywords to analyze")
    parser.add_argument("--gl", default="us", help="Country code")
    parser.add_argument("--hl", default="en", help="Language code")
    parser.add_argument("--device", choices=["desktop", "mobile"])
    parser.add_argument("--output", "-o", help="Save JSON output to file")
    args = parser.parse_args()



    try:
        client = NodeshubClient()
        results = []

        for kw in args.keywords:
            print(f"Analyzing: {kw}...", file=sys.stderr)
            analysis = analyze_single(client, kw, args.gl, args.hl, args.device)
            results.append(analysis)

        output = results[0] if len(results) == 1 else {"analyses": results}
        json_output = json.dumps(output, indent=2, ensure_ascii=False)

        if args.output:
            Path(args.output).write_text(json_output)
            print(f"Saved to {args.output}", file=sys.stderr)
        else:
            print(json_output)

    except NodeshubError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
