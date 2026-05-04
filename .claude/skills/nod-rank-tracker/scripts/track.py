#!/usr/bin/env python3
"""
Rank Tracker — Track keyword positions for a domain via NodesHub SERPdata API.

Usage:
    python3 track.py example.com "keyword" --gl us --hl en
    python3 track.py example.com --file keywords.txt --gl us --hl en --compare
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


def find_domain_position(organic_results, domain):
    """Find a domain's position and URL in organic results."""
    domain = domain.lower().replace("www.", "")
    for r in organic_results:
        r_domain = r.get("domain", "").lower().replace("www.", "")
        r_url = r.get("url", r.get("link", "")).lower()
        if domain in r_domain or domain in r_url:
            return {
                "position": r.get("pos", r.get("global_pos")),
                "url": r.get("url", r.get("link", "")),
                "title": r.get("title", ""),
            }
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


def render_report_section(data, previous=None):
    """Convert rank tracker snapshot into an HTML report section.

    Args:
        data: Snapshot dict with domain, date, keywords.
        previous: Optional previous snapshot for comparison.
    """
    from html import escape as e
    parts = []
    domain = data.get("domain", "")
    kws = data.get("keywords", {})

    ranking = sum(1 for r in kws.values() if r.get("position"))
    top3 = sum(1 for r in kws.values() if r.get("position") and r["position"] <= 3)
    top10 = sum(1 for r in kws.values() if r.get("position") and r["position"] <= 10)

    parts.append(summary_card([
        (e(domain), "Domain"),
        (data.get("date", ""), "Date"),
        (f"{ranking}/{len(kws)}", "Ranking"),
        (str(top3), "Top 3"),
        (str(top10), "Top 10"),
    ]))

    # Positions table
    rows = []
    prev_kws = previous.get("keywords", {}) if previous else {}
    for kw, info in kws.items():
        pos = info.get("position")
        pos_str = f"#{pos}" if pos else "—"
        url = e(str(info.get("url", "") or "—"))

        change_html = ""
        if prev_kws.get(kw):
            prev_pos = prev_kws[kw].get("position")
            if prev_pos and pos:
                diff = prev_pos - pos
                if diff > 0:
                    change_html = f'<span class="change-up">+{diff} ↑</span>'
                elif diff < 0:
                    change_html = f'<span class="change-down">{diff} ↓</span>'
                else:
                    change_html = '<span class="change-stable">=</span>'
            elif pos and not prev_pos:
                change_html = '<span class="change-up">new ↑</span>'
            elif prev_pos and not pos:
                change_html = '<span class="change-down">lost ↓</span>'

        rows.append([e(kw), pos_str, change_html, url])

    headers = ["Keyword", "Position", "Change", "URL"]
    parts.append("<h3>Rankings</h3>")
    parts.append(html_table(headers, rows))

    # Position distribution
    buckets = {"#1": 0, "#2-3": 0, "#4-5": 0, "#6-7": 0, "#8-10": 0, "Not ranked": 0}
    for info in kws.values():
        pos = info.get("position")
        if pos == 1: buckets["#1"] += 1
        elif pos and pos <= 3: buckets["#2-3"] += 1
        elif pos and pos <= 5: buckets["#4-5"] += 1
        elif pos and pos <= 7: buckets["#6-7"] += 1
        elif pos and pos <= 10: buckets["#8-10"] += 1
        else: buckets["Not ranked"] += 1

    chart_items = [(k, v, str(v)) for k, v in buckets.items() if v > 0]
    if chart_items:
        parts.append("<h3>Position Distribution</h3>")
        parts.append(bar_chart(chart_items))

    sid = make_section_id("rank-tracker")
    return render_section_wrapper(sid, "Rank Tracker",
                                  f"Rank Tracker: {e(domain)}", "\n".join(parts))


def main():
    parser = argparse.ArgumentParser(description="Track keyword positions for a domain")
    parser.add_argument("domain", help="Domain to track (e.g., example.com)")
    parser.add_argument("keywords", nargs="*", help="Keywords to track")
    parser.add_argument("--file", help="File with keywords (one per line)")
    parser.add_argument("--gl", default="us", help="Country code (default: us)")
    parser.add_argument("--hl", default="en", help="Language code (default: en)")
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
        print("Error: No keywords provided. Use positional args or --file.", file=sys.stderr)
        sys.exit(1)

    print(f"Tracking {len(keywords)} keywords for {args.domain} (cost: {len(keywords)} tokens)")

    try:
        client = NodeshubClient()
        results = {}

        failed = []
        lock = threading.Lock()
        counter = [0]

        def _fetch(kw):
            serp, from_cache = serp_cache.search_cached(client, kw, args.gl, args.hl)
            data = serp.get("data", {})
            organic = data.get("results", {}).get("organic_results", [])
            return find_domain_position(organic, args.domain), from_cache

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {executor.submit(_fetch, kw): kw for kw in keywords}
            for future in as_completed(futures):
                kw = futures[future]
                with lock:
                    counter[0] += 1
                    n = counter[0]
                try:
                    match, from_cache = future.result()
                    tag = "[cache]" if from_cache else "[api]"
                    if match:
                        results[kw] = match
                        print(f"  [{n}/{len(keywords)}] {kw}... #{match['position']} {tag}")
                    else:
                        results[kw] = {"position": None, "url": None, "title": None}
                        print(f"  [{n}/{len(keywords)}] {kw}... not in top 10 {tag}")
                except NodeshubError as e:
                    with lock:
                        failed.append(kw)
                    results[kw] = {"position": None, "url": None, "title": None, "error": str(e)}
                    print(f"  [{n}/{len(keywords)}] {kw}... FAILED ({e})")

        # Save snapshot
        data_dir = _PROJECT_ROOT / "output" / "data" / "rank-history" / args.domain.lower().replace("www.", "")
        data_dir.mkdir(parents=True, exist_ok=True)
        snapshot = {
            "domain": args.domain,
            "date": str(date.today()),
            "gl": args.gl,
            "hl": args.hl,
            "keywords": results,
        }
        snapshot_path = data_dir / f"{date.today()}.json"
        snapshot_path.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n")

        if args.raw:
            print(json.dumps(snapshot, indent=2, ensure_ascii=False))
            return

        # Load previous for comparison
        previous = None
        if args.compare:
            previous = load_previous_snapshot(data_dir)

        # Print results
        print()
        print(f"## Rank Tracker: {args.domain}")
        print(f"**Date:** {date.today()} | **Keywords:** {len(keywords)} | **Tokens used:** {len(keywords)}")
        print()

        ranking_count = sum(1 for r in results.values() if r["position"])
        top3 = sum(1 for r in results.values() if r["position"] and r["position"] <= 3)
        top10 = sum(1 for r in results.values() if r["position"] and r["position"] <= 10)

        print(f"| Keyword | Position | {'Change | ' if previous else ''}URL |")
        print(f"|---------|----------|{'--------|' if previous else ''}-----|")

        improved = declined = stable = 0
        for kw, data in results.items():
            pos = f"#{data['position']}" if data["position"] else "—"
            url = data.get("url", "—") or "—"

            change_str = ""
            if previous and previous.get("keywords", {}).get(kw):
                prev_pos = previous["keywords"][kw].get("position")
                curr_pos = data["position"]
                if prev_pos and curr_pos:
                    diff = prev_pos - curr_pos
                    if diff > 0:
                        change_str = f"+{diff} ↑"
                        improved += 1
                    elif diff < 0:
                        change_str = f"{diff} ↓"
                        declined += 1
                    else:
                        change_str = "="
                        stable += 1
                elif curr_pos and not prev_pos:
                    change_str = "new ↑"
                    improved += 1
                elif prev_pos and not curr_pos:
                    change_str = "lost ↓"
                    declined += 1

            if previous:
                print(f"| {kw} | {pos} | {change_str} | {url} |")
            else:
                print(f"| {kw} | {pos} | {url} |")

        print()
        print(f"**Ranking:** {ranking_count}/{len(keywords)} keywords")
        print(f"**Top 3:** {top3} | **Top 10:** {top10}")
        if previous:
            print(f"**Improved:** {improved} | **Declined:** {declined} | **Stable:** {stable}")

        if failed:
            print(f"\n**Failed keywords ({len(failed)}):** {', '.join(failed)}")
            print("Tip: API was at capacity. Re-run to retry failed keywords.")

        print(f"\nSnapshot saved to: {snapshot_path}")

    except NodeshubError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
