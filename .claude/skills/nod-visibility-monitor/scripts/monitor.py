#!/usr/bin/env python3
"""
Visibility Monitor — Calculate SEO visibility score via NodesHub SERPdata API.

Usage:
    python3 monitor.py example.com --file keywords.txt --gl us --hl en
    python3 monitor.py example.com --file keywords.txt --gl us --hl en --competitors ahrefs.com,semrush.com
"""

import argparse
import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'nod-nodeshub-api' / 'scripts'))
from client import NodeshubClient, NodeshubError
from report import render_section_wrapper, make_section_id, html_table, summary_card, bar_chart, badge, find_repo_root
import serp_cache

_PROJECT_ROOT = find_repo_root()
MAX_WORKERS = 5

# Visibility scoring weights
POSITION_POINTS = {
    1: 10, 2: 9, 3: 8,
    4: 6, 5: 6,
    6: 4, 7: 4,
    8: 2, 9: 2, 10: 2,
}


def score_position(pos):
    """Return visibility points for a given position."""
    if pos is None or pos < 1:
        return 0
    return POSITION_POINTS.get(pos, 0)


def find_domain_position(organic_results, domain):
    """Find a domain's position in organic results."""
    domain = domain.lower().replace("www.", "")
    for r in organic_results:
        r_domain = r.get("domain", "").lower().replace("www.", "")
        r_url = r.get("url", r.get("link", "")).lower()
        if domain in r_domain or domain in r_url:
            return r.get("pos", r.get("global_pos"))
    return None


def load_previous_snapshot(data_dir):
    """Load most recent previous snapshot for comparison."""
    if not data_dir.exists():
        return None
    files = sorted(data_dir.glob("*.json"), reverse=True)
    for f in files:
        if f.stem != str(date.today()):
            try:
                return json.loads(f.read_text())
            except (json.JSONDecodeError, OSError):
                continue
    return None


def render_report_section(data):
    """Convert visibility monitor snapshot into an HTML report section."""
    from html import escape as e
    parts = []
    domain = data.get("domain", "")
    pct = data.get("visibility_pct", 0)
    score = data.get("score", 0)
    max_score = data.get("max_score", 0)
    kws = data.get("keywords", {})

    parts.append(summary_card([
        (f"{pct}%", "Visibility"),
        (f"{score}/{max_score}", "Score"),
        (str(len(kws)), "Keywords"),
    ]))

    # Position bucket table
    buckets = {"#1": [0, 0], "#2-3": [0, 0], "#4-5": [0, 0],
               "#6-7": [0, 0], "#8-10": [0, 0], "Not in top 10": [0, 0]}
    for kw_data in kws.values():
        pos = kw_data.get("position")
        pts = kw_data.get("points", 0)
        if pos == 1: buckets["#1"][0] += 1; buckets["#1"][1] += pts
        elif pos and pos <= 3: buckets["#2-3"][0] += 1; buckets["#2-3"][1] += pts
        elif pos and pos <= 5: buckets["#4-5"][0] += 1; buckets["#4-5"][1] += pts
        elif pos and pos <= 7: buckets["#6-7"][0] += 1; buckets["#6-7"][1] += pts
        elif pos and pos <= 10: buckets["#8-10"][0] += 1; buckets["#8-10"][1] += pts
        else: buckets["Not in top 10"][0] += 1

    rows = [[k, str(v[0]), str(v[1])] for k, v in buckets.items() if v[0] > 0]
    if rows:
        parts.append("<h3>Score Breakdown</h3>")
        parts.append(html_table(["Position Bucket", "Keywords", "Points"], rows))

    # Competitor comparison
    competitors = data.get("competitors", {})
    if competitors:
        comp_rows = [[e(domain), str(score), f"{pct}%"]]
        for d, info in competitors.items():
            comp_rows.append([e(d), str(info.get("score", 0)),
                              f"{info.get('visibility_pct', 0)}%"])
        comp_rows.sort(key=lambda r: -int(r[1]))
        parts.append("<h3>Competitor Comparison</h3>")
        parts.append(html_table(["Domain", "Score", "Visibility %"], comp_rows))

    sid = make_section_id("visibility-monitor")
    return render_section_wrapper(sid, "Visibility Monitor",
                                  f"Visibility Monitor: {e(domain)}", "\n".join(parts))


def main():
    parser = argparse.ArgumentParser(description="Calculate SEO visibility score")
    parser.add_argument("domain", help="Domain to monitor")
    parser.add_argument("--keywords", nargs="*", help="Keywords to check")
    parser.add_argument("--file", help="File with keywords (one per line)")
    parser.add_argument("--gl", default="us", help="Country code (default: us)")
    parser.add_argument("--hl", default="en", help="Language code (default: en)")
    parser.add_argument("--competitors", help="Comma-separated competitor domains")
    parser.add_argument("--compare", action="store_true", help="Compare with previous snapshot")
    parser.add_argument("--raw", action="store_true", help="Output raw JSON to stdout (also saves snapshot to disk)")
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
        print("Error: No keywords provided. Use --keywords or --file.", file=sys.stderr)
        sys.exit(1)

    competitors = [d.strip().lower().replace("www.", "") for d in args.competitors.split(",")] if args.competitors else []
    all_domains = [args.domain.lower().replace("www.", "")] + competitors

    print(f"Monitoring visibility for {args.domain} across {len(keywords)} keywords (cost: {len(keywords)} tokens)")

    try:
        client = NodeshubClient()
        domain_scores = {d: {"keywords": {}, "total": 0} for d in all_domains}

        lock = threading.Lock()
        counter = [0]
        serp_results = {}

        def _fetch(kw):
            serp, from_cache = serp_cache.search_cached(client, kw, args.gl, args.hl)
            data = serp.get("data", {})
            return data.get("results", {}).get("organic_results", []), from_cache

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {executor.submit(_fetch, kw): kw for kw in keywords}
            for future in as_completed(futures):
                kw = futures[future]
                with lock:
                    counter[0] += 1
                    n = counter[0]
                try:
                    organic, from_cache = future.result()
                    serp_results[kw] = organic
                    tag = "[cache]" if from_cache else "[api]"
                    print(f"  [{n}/{len(keywords)}] {kw}... {tag}")
                except Exception as e:
                    serp_results[kw] = []
                    print(f"  [{n}/{len(keywords)}] {kw}... FAILED ({type(e).__name__}: {e})")

        for kw in keywords:
            organic = serp_results[kw]
            for domain in all_domains:
                pos = find_domain_position(organic, domain)
                points = score_position(pos)
                domain_scores[domain]["keywords"][kw] = {
                    "position": pos,
                    "points": points,
                }
                domain_scores[domain]["total"] += points

        max_score = len(keywords) * 10

        # Save snapshot
        primary = args.domain.lower().replace("www.", "")
        data_dir = _PROJECT_ROOT / "output" / "data" / "visibility" / primary
        data_dir.mkdir(parents=True, exist_ok=True)

        snapshot = {
            "domain": args.domain,
            "date": str(date.today()),
            "gl": args.gl,
            "hl": args.hl,
            "score": domain_scores[primary]["total"],
            "max_score": max_score,
            "visibility_pct": round(domain_scores[primary]["total"] / max_score * 100, 1) if max_score else 0,
            "keywords": domain_scores[primary]["keywords"],
            "competitors": {
                d: {
                    "score": domain_scores[d]["total"],
                    "visibility_pct": round(domain_scores[d]["total"] / max_score * 100, 1) if max_score else 0,
                }
                for d in competitors
            },
        }
        snapshot_path = data_dir / f"{date.today()}.json"
        snapshot_path.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n")

        if args.raw:
            print(json.dumps(snapshot, indent=2, ensure_ascii=False))
            return

        # Print results
        print()
        print(f"## Visibility Monitor: {args.domain}")
        print(f"**Date:** {date.today()} | **Keywords:** {len(keywords)} | **Tokens used:** {len(keywords)}")
        print()

        score = domain_scores[primary]["total"]
        pct = round(score / max_score * 100, 1) if max_score else 0
        print(f"### Visibility Score: {score}/{max_score} ({pct}%)")
        print()

        # Position bucket breakdown
        buckets = {"#1": 0, "#2-3": 0, "#4-5": 0, "#6-7": 0, "#8-10": 0, "Not in top 10": 0}
        bucket_points = {"#1": 0, "#2-3": 0, "#4-5": 0, "#6-7": 0, "#8-10": 0, "Not in top 10": 0}
        for kw_data in domain_scores[primary]["keywords"].values():
            pos = kw_data["position"]
            pts = kw_data["points"]
            if pos == 1:
                buckets["#1"] += 1
                bucket_points["#1"] += pts
            elif pos and pos <= 3:
                buckets["#2-3"] += 1
                bucket_points["#2-3"] += pts
            elif pos and pos <= 5:
                buckets["#4-5"] += 1
                bucket_points["#4-5"] += pts
            elif pos and pos <= 7:
                buckets["#6-7"] += 1
                bucket_points["#6-7"] += pts
            elif pos and pos <= 10:
                buckets["#8-10"] += 1
                bucket_points["#8-10"] += pts
            else:
                buckets["Not in top 10"] += 1

        print("### Score Breakdown")
        print("| Position Bucket | Keywords | Points |")
        print("|----------------|----------|--------|")
        for bucket, count in buckets.items():
            if count > 0:
                print(f"| {bucket} | {count} | {bucket_points[bucket]} |")
        print()

        # Competitor comparison
        if competitors:
            print("### Competitor Comparison")
            print("| Domain | Score | Visibility % |")
            print("|--------|-------|-------------|")
            all_scores = [(d, domain_scores[d]["total"]) for d in all_domains]
            all_scores.sort(key=lambda x: -x[1])
            for d, s in all_scores:
                p = round(s / max_score * 100, 1) if max_score else 0
                marker = " **" if d == primary else ""
                print(f"| {d}{marker} | {s}/{max_score} | {p}% |")
            print()

        # Compare with previous
        if args.compare:
            previous = load_previous_snapshot(data_dir)
            if previous:
                prev_score = previous.get("score", 0)
                diff = score - prev_score
                diff_pct = round(diff / prev_score * 100, 1) if prev_score else 0
                print(f"### Change (vs previous: {previous.get('date', '?')})")
                print(f"- Score: {prev_score} → {score} ({'+' if diff >= 0 else ''}{diff}, {'+' if diff_pct >= 0 else ''}{diff_pct}%)")

                prev_kws = previous.get("keywords", {})
                for kw, curr in domain_scores[primary]["keywords"].items():
                    prev = prev_kws.get(kw, {})
                    if curr["position"] and not prev.get("position"):
                        print(f"- New in top 10: \"{kw}\" (#{curr['position']})")
                    elif prev.get("position") and not curr["position"]:
                        print(f"- Lost from top 10: \"{kw}\" (was #{prev['position']})")
                print()

        print(f"Snapshot saved to: {snapshot_path}")

    except NodeshubError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
