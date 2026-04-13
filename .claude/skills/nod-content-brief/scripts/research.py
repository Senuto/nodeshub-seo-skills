#!/usr/bin/env python3
"""
Content Brief Research — Fetch SERP + Fan-out data for content brief generation.

Combines SERPdata (competition analysis) and Query Fan-out (keyword expansion)
into a single research output for content brief creation.

Usage:
    python3 research.py "keyword" --gl us --hl en
    python3 research.py "keyword" --gl us --hl en --mode reasoning --output brief-data.json
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


def extract_serp_insights(raw):
    """Extract structured insights from raw SERP data."""
    data = raw.get("data", {})
    results = data.get("results", {})
    organic = results.get("organic_results", [])
    snippets = results.get("snippets", {})

    # Domains
    domains = [r.get("domain", "") for r in organic if r.get("domain")]

    # SERP features
    features = []
    feature_map = {
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
        "shopping_results": "Shopping",
    }
    for key, name in feature_map.items():
        val = snippets.get(key)
        if val and val != {} and val != []:
            features.append(name)

    # PAA questions
    paa_questions = []
    paa = snippets.get("people_also_ask", {})
    if isinstance(paa, dict) and paa.get("items"):
        paa_questions = [item.get("question", "") for item in paa["items"] if item.get("question")]
    elif isinstance(paa, list):
        paa_questions = [q.get("question", str(q)) if isinstance(q, dict) else str(q) for q in paa]

    # Related searches
    related = snippets.get("related_searches", {})
    related_queries = []
    if isinstance(related, dict):
        related_queries = related.get("queries", [])

    # AI Overview text
    ai_overview = ""
    ai = snippets.get("ai_overview", {})
    if isinstance(ai, dict):
        ai_overview = ai.get("content_text", "")

    # Intent heuristic
    intent_scores = {"informational": 0, "commercial": 0, "transactional": 0, "navigational": 0}
    if "People Also Ask" in features:
        intent_scores["informational"] += 2
    if "Knowledge Panel" in features:
        intent_scores["informational"] += 1
    if "AI Overview" in features:
        intent_scores["informational"] += 1
    if "Videos" in features:
        intent_scores["informational"] += 1
    if "Shopping" in features:
        intent_scores["transactional"] += 3
    if "Ads" in features:
        intent_scores["commercial"] += 2
    for r in organic[:5]:
        title = (r.get("title", "") or "").lower()
        if any(w in title for w in ["best", "top", "review", "vs", "comparison"]):
            intent_scores["commercial"] += 1
        if any(w in title for w in ["buy", "price", "discount", "shop"]):
            intent_scores["transactional"] += 1

    dominant_intent = max(intent_scores, key=intent_scores.get)

    # Top results
    top_results = [
        {
            "pos": r.get("pos"),
            "title": r.get("title"),
            "url": r.get("url"),
            "domain": r.get("domain"),
            "description": r.get("description"),
        }
        for r in organic[:10]
    ]

    return {
        "total_results": data.get("total_results_count", "?"),
        "top_results": top_results,
        "domains": domains[:10],
        "domain_frequency": dict(Counter(domains).most_common(10)),
        "serp_features": features,
        "paa_questions": paa_questions,
        "related_searches": related_queries,
        "ai_overview": ai_overview[:500] if ai_overview else "",
        "dominant_intent": dominant_intent,
        "intent_scores": intent_scores,
    }


def render_report_section(data):
    """Convert content brief research data into an HTML report section.

    Args:
        data: Dict with keyword, gl, hl, tokens_used, serp (dict), fanout (dict).
    """
    from html import escape as e
    parts = []
    keyword = data.get("keyword", "")
    serp = data.get("serp", {})

    parts.append(summary_card([
        (e(keyword), "Keyword"),
        (e(str(serp.get("dominant_intent", ""))).title(), "Intent"),
        (str(data.get("tokens_used", 0)), "Tokens Used"),
    ]))

    # Top results table
    top = serp.get("top_results", [])
    if top:
        rows = [[str(r.get("pos", "")), e(str(r.get("title", "") or "")),
                 e(str(r.get("domain", "") or ""))]
                for r in top]
        parts.append("<h3>Top SERP Results</h3>")
        parts.append(html_table(["#", "Title", "Domain"], rows))

    # SERP features
    features = serp.get("serp_features", [])
    if features:
        badges_html = " ".join(badge(e(f), "info") for f in features)
        parts.append(f"<h3>SERP Features</h3>\n<p>{badges_html}</p>")

    # Related keywords from fanout
    fanout = data.get("fanout", {})
    variants = fanout.get("generated_variants", [])
    if variants:
        kw_items = "".join(f"<li>{e(str(v.get('keyword', v) if isinstance(v, dict) else v))}</li>"
                           for v in variants[:30])
        parts.append(f"<h3>Related Keywords</h3>\n<ul>{kw_items}</ul>")

    # PAA questions
    paa = serp.get("paa_questions", [])
    if paa:
        q_items = "".join(f"<li>{e(q)}</li>" for q in paa)
        parts.append(f"<h3>Questions (PAA)</h3>\n<ul>{q_items}</ul>")

    # Related searches
    related = serp.get("related_searches", [])
    if related:
        r_items = "".join(f"<li>{e(str(q))}</li>" for q in related)
        parts.append(f"<h3>Related Searches</h3>\n<ul>{r_items}</ul>")

    sid = make_section_id("content-brief")
    return render_section_wrapper(sid, "Content Brief",
                                  f"Content Brief: {e(keyword)}", "\n".join(parts))


def main():
    parser = argparse.ArgumentParser(description="Research data for content brief via NodesHub API")
    parser.add_argument("keyword", help="Target keyword for content brief")
    parser.add_argument("--gl", default="us", help="Country code (default: us)")
    parser.add_argument("--hl", default="en", help="Language code (default: en)")
    parser.add_argument("--device", choices=["desktop", "mobile"])
    parser.add_argument("--mode", choices=["standard", "reasoning"], default="standard",
                        help="Fan-out mode: standard (7.5 tokens) or reasoning (30 tokens)")
    parser.add_argument("--output", "-o", help="Save JSON output to file")
    args = parser.parse_args()



    tokens_estimate = 1 + (7.5 if args.mode == "standard" else 30)
    print(f"Researching: {args.keyword}", file=sys.stderr)
    print(f"Estimated cost: {tokens_estimate} tokens (1 SERPdata + {tokens_estimate - 1} Fan-out)", file=sys.stderr)

    try:
        client = NodeshubClient()

        # Check balance
        balance = client.get_balance()
        left = balance.get("left", 0)
        if isinstance(left, (int, float)) and left < tokens_estimate:
            print(f"Warning: Balance ({left}) may be insufficient ({tokens_estimate} needed)", file=sys.stderr)

        # Fetch SERP data
        print("Fetching SERP data...", file=sys.stderr)
        serp_raw = client.search(args.keyword, gl=args.gl, hl=args.hl, device=args.device)
        serp_insights = extract_serp_insights(serp_raw)

        # Fetch keyword expansion
        print("Expanding keywords...", file=sys.stderr)
        fanout_raw = client.query_fanout(
            args.keyword, hl=args.hl, mode=args.mode,
            add_questions=True, add_topic_leaders=True,
        )

        output = {
            "keyword": args.keyword,
            "gl": args.gl,
            "hl": args.hl,
            "tokens_used": tokens_estimate,
            "serp": serp_insights,
            "fanout": fanout_raw,
        }

        json_output = json.dumps(output, indent=2, ensure_ascii=False)

        if args.output:
            Path(args.output).write_text(json_output)
            print(f"Saved to {args.output}", file=sys.stderr)
        else:
            print(json_output)

        print(f"Done. Tokens used: {tokens_estimate}", file=sys.stderr)

    except NodeshubError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
