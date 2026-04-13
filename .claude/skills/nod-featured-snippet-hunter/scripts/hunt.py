#!/usr/bin/env python3
"""
Featured Snippet Hunter — Find snippet opportunities via NodesHub SERPdata API.

Usage:
    python3 hunt.py --domain example.com "keyword" --gl us --hl en
    python3 hunt.py --domain example.com --file keywords.txt --gl us --hl en
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'nod-nodeshub-api' / 'scripts'))
from client import NodeshubClient, NodeshubError
from report import render_section_wrapper, make_section_id, html_table, summary_card, badge


def normalize_domain(domain):
    """Strip www. and lowercase for comparison."""
    return domain.lower().replace("www.", "").strip().rstrip("/")


def find_domain_position(organic, domain):
    """Find domain's position in organic results. Returns (position, url) or (None, None)."""
    target = normalize_domain(domain)
    for r in organic:
        r_domain = normalize_domain(r.get("domain", ""))
        if r_domain == target or r_domain.endswith("." + target):
            pos = r.get("pos") or r.get("global_pos")
            url = r.get("url") or r.get("link", "")
            return pos, url
    return None, None


def analyze_snippet(serp_data, domain):
    """Analyze a SERP for snippet opportunity. Returns classification dict."""
    data = serp_data.get("data", {})
    results = data.get("results", {})
    snippets = results.get("snippets", {})
    organic = results.get("organic_results", [])

    result = {
        "has_snippet": False,
        "snippet_type": None,
        "snippet_owner": None,
        "snippet_url": None,
        "snippet_answer": None,
        "your_position": None,
        "your_url": None,
        "category": "no_snippet",
    }

    # Find domain position
    pos, url = find_domain_position(organic, domain)
    result["your_position"] = pos
    result["your_url"] = url

    # Check answer box
    ab = snippets.get("answer_box")
    if not ab or not isinstance(ab, dict) or ab == {}:
        return result

    result["has_snippet"] = True

    # Extract snippet details
    snippet_domain = ab.get("domain", "")
    snippet_url = ab.get("url") or ab.get("link", "")
    if not snippet_domain and snippet_url:
        # Try to extract domain from URL
        try:
            from urllib.parse import urlparse
            snippet_domain = urlparse(snippet_url).netloc
        except Exception:
            pass

    result["snippet_owner"] = normalize_domain(snippet_domain) if snippet_domain else "unknown"
    result["snippet_url"] = snippet_url

    # Snippet type
    snippet_type = ab.get("type", "")
    if not snippet_type:
        if ab.get("list") or ab.get("items"):
            snippet_type = "list"
        elif ab.get("table"):
            snippet_type = "table"
        else:
            snippet_type = "paragraph"
    result["snippet_type"] = snippet_type

    # Snippet answer preview
    answer = ab.get("answer") or ab.get("content_text") or ab.get("title", "")
    if answer:
        result["snippet_answer"] = answer[:150].strip()

    # Classify opportunity
    target = normalize_domain(domain)
    owner = result["snippet_owner"]

    if owner == target or owner.endswith("." + target):
        result["category"] = "defend"
    elif pos is not None and pos <= 10:
        result["category"] = "steal"
    elif pos is not None:
        result["category"] = "target"
    else:
        result["category"] = "target"

    return result


def render_report_section(data):
    """Convert featured snippet hunter data into an HTML report section.

    Args:
        data: Dict with domain, results (keyword -> analysis dict).
    """
    from html import escape as e
    parts = []
    results = data.get("results", {})
    domain = data.get("domain", "")

    steal = [(kw, r) for kw, r in results.items() if r.get("category") == "steal"]
    defend = [(kw, r) for kw, r in results.items() if r.get("category") == "defend"]
    target = [(kw, r) for kw, r in results.items() if r.get("category") == "target"]
    snippets_found = sum(1 for r in results.values() if r.get("has_snippet"))

    steal.sort(key=lambda x: x[1].get("your_position") or 999)
    target.sort(key=lambda x: x[1].get("your_position") or 999)

    parts.append(summary_card([
        (str(len(results)), "Keywords"),
        (str(snippets_found), "Snippets Found"),
        (str(len(steal)), "Steal"),
        (str(len(defend)), "Defend"),
        (str(len(target)), "Target"),
    ]))

    cat_badge_map = {"steal": "error", "defend": "success", "target": "warning"}
    all_opps = ([("steal", kw, r) for kw, r in steal] +
                [("defend", kw, r) for kw, r in defend] +
                [("target", kw, r) for kw, r in target])
    if all_opps:
        rows = []
        for cat, kw, r in all_opps:
            pos = r.get("your_position")
            rows.append([
                badge(cat.upper(), cat_badge_map.get(cat, "info")),
                e(kw), f"#{pos}" if pos else "N/A",
                e(str(r.get("snippet_owner", "") or "")),
                e(str(r.get("snippet_type", "") or "")),
            ])
        parts.append("<h3>Snippet Opportunities</h3>")
        parts.append(html_table(["Category", "Keyword", "Your Pos", "Snippet Owner", "Type"], rows))

    sid = make_section_id("featured-snippet-hunter")
    return render_section_wrapper(sid, "Featured Snippet Hunter",
                                  f"Snippet Opportunities: {e(domain)}", "\n".join(parts))


def main():
    parser = argparse.ArgumentParser(description="Find Featured Snippet opportunities")
    parser.add_argument("keywords", nargs="*", help="Keywords to check")
    parser.add_argument("--domain", required=True, help="Your domain (e.g. example.com)")
    parser.add_argument("--file", help="File with keywords (one per line)")
    parser.add_argument("--gl", default="us", help="Country code (default: us)")
    parser.add_argument("--hl", default="en", help="Language code (default: en)")
    parser.add_argument("--raw", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    # Collect keywords
    keywords = list(args.keywords) if args.keywords else []
    if args.file:
        try:
            with open(args.file) as f:
                keywords.extend(line.strip() for line in f if line.strip())
        except FileNotFoundError:
            print(f"Error: File not found: {args.file}", file=sys.stderr)
            sys.exit(1)

    if not keywords:
        print("Error: No keywords provided.", file=sys.stderr)
        sys.exit(1)

    domain = normalize_domain(args.domain)
    print(f"Hunting Featured Snippets for {domain} ({len(keywords)} keywords, cost: {len(keywords)} tokens)")

    try:
        client = NodeshubClient()
        all_results = {}

        for i, kw in enumerate(keywords, 1):
            print(f"  [{i}/{len(keywords)}] {kw}...", end=" ", flush=True)
            serp = client.search(kw, gl=args.gl, hl=args.hl)
            analysis = analyze_snippet(serp, domain)
            all_results[kw] = analysis

            cat = analysis["category"]
            if cat == "steal":
                print(f"STEAL (snippet: {analysis['snippet_owner']}, you: #{analysis['your_position']})")
            elif cat == "defend":
                print(f"DEFEND (you own it, #{analysis['your_position']})")
            elif cat == "target" and analysis["has_snippet"]:
                pos_str = f"#{analysis['your_position']}" if analysis['your_position'] else "not ranking"
                print(f"TARGET (snippet: {analysis['snippet_owner']}, you: {pos_str})")
            else:
                pos_str = f"#{analysis['your_position']}" if analysis['your_position'] else "not ranking"
                print(f"no snippet (you: {pos_str})")

        if args.raw:
            print(json.dumps(all_results, indent=2, ensure_ascii=False))
            return

        # Group by category
        steal = [(kw, r) for kw, r in all_results.items() if r["category"] == "steal"]
        defend = [(kw, r) for kw, r in all_results.items() if r["category"] == "defend"]
        target = [(kw, r) for kw, r in all_results.items() if r["category"] == "target"]
        no_snippet = [(kw, r) for kw, r in all_results.items() if r["category"] == "no_snippet"]

        # Sort steal by position (closest to #1 first)
        steal.sort(key=lambda x: x[1]["your_position"] or 999)
        target.sort(key=lambda x: x[1]["your_position"] or 999)

        print()
        print(f"## Featured Snippet Opportunities for {domain}")
        print()
        print(f"**Keywords analyzed:** {len(keywords)} | **Tokens used:** {len(keywords)}")
        print(f"**Opportunities:** {len(steal)} steal, {len(defend)} defend, {len(target)} target, {len(no_snippet)} no snippet")
        print()

        if steal:
            print("### Steal (you rank but don't own the snippet)")
            print("| Keyword | Your Pos | Snippet Owner | Type |")
            print("|---------|:--------:|---------------|:----:|")
            for kw, r in steal:
                print(f"| {kw} | #{r['your_position']} | {r['snippet_owner']} | {r['snippet_type']} |")
            print()

        if defend:
            print("### Defend (you own the snippet)")
            print("| Keyword | Your Pos | Type |")
            print("|---------|:--------:|:----:|")
            for kw, r in defend:
                print(f"| {kw} | #{r['your_position']} | {r['snippet_type']} |")
            print()

        if target:
            print("### Target (snippet exists, you're not in TOP 10)")
            print("| Keyword | Snippet Owner | Type | Your Pos |")
            print("|---------|---------------|:----:|:--------:|")
            for kw, r in target:
                pos_str = f"#{r['your_position']}" if r['your_position'] else "N/A"
                print(f"| {kw} | {r['snippet_owner']} | {r['snippet_type']} | {pos_str} |")
            print()

        if no_snippet:
            print("### No Snippet")
            print(", ".join(kw for kw, _ in no_snippet))
            print()

        if steal or target:
            print("### Recommendations")
            snippet_types = set()
            for kw, r in steal + target:
                if r["snippet_type"]:
                    snippet_types.add(r["snippet_type"])

            print("1. **Focus on \"steal\" keywords first** — you already rank, optimize content for snippet format")
            if "paragraph" in snippet_types:
                print("2. **Paragraph snippets:** Add a concise 40-60 word definition/answer near the top of your page")
            if "list" in snippet_types:
                print(f"{'3' if 'paragraph' in snippet_types else '2'}. **List snippets:** Structure content with clear H2/H3 headings and bullet/numbered lists")
            if "table" in snippet_types:
                print(f"{len(snippet_types) + 1}. **Table snippets:** Add comparison or data tables with clear headers")

    except NodeshubError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
