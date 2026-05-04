#!/usr/bin/env python3
"""
Competitor Tracker — Track competitor domains across keywords via NodesHub SERPdata API.

Usage:
    python3 track.py "keyword1" "keyword2" --gl us --hl en
    python3 track.py --file keywords.txt --gl us --hl en --watch ahrefs.com,semrush.com
"""

import argparse
import json
import os
import sys
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'nod-nodeshub-api' / 'scripts'))
from client import NodeshubClient, NodeshubError
from report import render_section_wrapper, make_section_id, html_table, summary_card, bar_chart, badge
import serp_cache

MAX_WORKERS = 5


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
    """Convert competitor tracker data into an HTML report section.

    Args:
        data: Dict with date, gl, hl, watched_domains, keyword_results, domain_stats.
    """
    from html import escape as e
    parts = []
    keyword_results = data.get("keyword_results", {})
    domain_stats = data.get("domain_stats", {})
    watched = data.get("watched_domains", [])

    parts.append(summary_card([
        (str(len(keyword_results)), "Keywords Tracked"),
        (str(len(domain_stats)), "Domains Found"),
        (str(len(watched)), "Watched"),
    ]))

    # Domain frequency table (top 15)
    sorted_domains = sorted(domain_stats.items(),
        key=lambda x: (-len(x[1].get("keywords", [])),
                        sum(x[1].get("positions", [])) / max(len(x[1].get("positions", [1])), 1)))
    rows = []
    for domain, stats in sorted_domains[:15]:
        kw_count = len(stats.get("keywords", []))
        positions = stats.get("positions", [])
        avg_pos = sum(positions) / len(positions) if positions else 0
        marker = " **" if domain in watched else ""
        rows.append([e(domain) + marker, f"{kw_count}/{len(keyword_results)}",
                     f"{avg_pos:.1f}"])
    if rows:
        parts.append("<h3>Domain Frequency (Top 15)</h3>")
        parts.append(html_table(["Domain", "Keywords in Top 10", "Avg Position"], rows))

    # Keyword × Domain matrix for watched domains
    if watched:
        show_domains = [d for d in watched if d in domain_stats]
        if show_domains:
            matrix_rows = []
            for kw in keyword_results:
                row = [e(kw)]
                for domain in show_domains:
                    pos = None
                    for r in keyword_results[kw].get("top_10", []):
                        if r.get("domain") == domain:
                            pos = r.get("position")
                            break
                    row.append(f"#{pos}" if pos else "—")
                matrix_rows.append(row)
            parts.append("<h3>Keyword × Domain Matrix</h3>")
            parts.append(html_table(["Keyword"] + [e(d) for d in show_domains], matrix_rows))

    sid = make_section_id("competitor-tracker")
    return render_section_wrapper(sid, "Competitor Tracker",
                                  "Competitor Tracker", "\n".join(parts))


def main():
    parser = argparse.ArgumentParser(description="Track competitor domains across keywords")
    parser.add_argument("keywords", nargs="*", help="Keywords to track")
    parser.add_argument("--file", help="File with keywords (one per line)")
    parser.add_argument("--gl", default="us", help="Country code (default: us)")
    parser.add_argument("--hl", default="en", help="Language code (default: en)")
    parser.add_argument("--watch", help="Comma-separated domains to highlight")
    parser.add_argument("--compare", action="store_true", help="Compare with previous snapshot")
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

    watched = [d.strip().lower().replace("www.", "") for d in args.watch.split(",")] if args.watch else []



    print(f"Tracking competitors for {len(keywords)} keywords (cost: {len(keywords)} tokens)")

    try:
        client = NodeshubClient()
        keyword_results = {}
        domain_stats = defaultdict(lambda: {"keywords": [], "positions": []})

        lock = threading.Lock()
        counter = [0]

        def _fetch(kw):
            serp, from_cache = serp_cache.search_cached(client, kw, args.gl, args.hl)
            data = serp.get("data", {})
            organic = data.get("results", {}).get("organic_results", [])
            top_10 = []
            for r in organic[:10]:
                d = r.get("domain", "").lower().replace("www.", "")
                top_10.append({
                    "position": r.get("pos", r.get("global_pos")),
                    "domain": d,
                    "url": r.get("url", r.get("link", "")),
                    "title": r.get("title", ""),
                })
            return top_10, from_cache

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {executor.submit(_fetch, kw): kw for kw in keywords}
            for future in as_completed(futures):
                kw = futures[future]
                with lock:
                    counter[0] += 1
                    n = counter[0]
                top_10, from_cache = future.result()
                keyword_results[kw] = {"top_10": top_10}
                tag = "[cache]" if from_cache else "[api]"
                print(f"  [{n}/{len(keywords)}] {kw}... {tag}")

        for kw, kw_data in keyword_results.items():
            for entry in kw_data["top_10"]:
                domain_stats[entry["domain"]]["keywords"].append(kw)
                domain_stats[entry["domain"]]["positions"].append(entry["position"])

        # Save snapshot
        data_dir = Path("output/data/competitor-tracking")
        data_dir.mkdir(parents=True, exist_ok=True)
        snapshot = {
            "date": str(date.today()),
            "gl": args.gl,
            "hl": args.hl,
            "watched_domains": watched,
            "keywords": keyword_results,
        }
        snapshot_path = data_dir / f"{date.today()}.json"
        snapshot_path.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n")

        if args.raw:
            print(json.dumps(snapshot, indent=2, ensure_ascii=False))
            return

        # Sort domains by frequency
        sorted_domains = sorted(
            domain_stats.items(),
            key=lambda x: (-len(x[1]["keywords"]), sum(x[1]["positions"]) / len(x[1]["positions"]))
        )

        # Print results
        print()
        print(f"## Competitor Tracker")
        print(f"**Date:** {date.today()} | **Keywords:** {len(keywords)} | **Tokens used:** {len(keywords)}")
        print()

        # Domain frequency table
        print("### Domain Frequency (Top 15)")
        print("| Domain | Keywords in Top 10 | Avg Position |")
        print("|--------|-------------------|--------------|")
        for domain, stats in sorted_domains[:15]:
            count = len(stats["keywords"])
            avg_pos = sum(stats["positions"]) / len(stats["positions"])
            marker = " **" if domain in watched else ""
            print(f"| {domain}{marker} | {count}/{len(keywords)} | {avg_pos:.1f} |")
        print()

        # Keyword × Domain matrix for watched domains
        if watched:
            show_domains = [d for d in watched if d in domain_stats]
            if show_domains:
                print("### Keyword × Domain Matrix (watched)")
                header = "| Keyword | " + " | ".join(show_domains) + " |"
                sep = "|---------|" + "|".join("-" * (len(d) + 2) for d in show_domains) + "|"
                print(header)
                print(sep)
                for kw in keywords:
                    row = f"| {kw} "
                    for domain in show_domains:
                        pos = None
                        for r in keyword_results[kw]["top_10"]:
                            if r["domain"] == domain:
                                pos = r["position"]
                                break
                        row += f"| {'#' + str(pos) if pos else '—'} "
                    row += "|"
                    print(row)
                print()

        # Compare with previous
        if args.compare:
            previous = load_previous_snapshot(data_dir)
            if previous:
                print("### Changes (vs previous)")
                prev_domains = defaultdict(set)
                for kw, kw_data in previous.get("keywords", {}).items():
                    for r in kw_data.get("top_10", []):
                        prev_domains[r["domain"]].add(kw)

                for domain in watched or [d for d, _ in sorted_domains[:10]]:
                    curr_kws = set(domain_stats.get(domain, {}).get("keywords", []))
                    prev_kws = prev_domains.get(domain, set())
                    gained = curr_kws - prev_kws
                    lost = prev_kws - curr_kws
                    if gained:
                        print(f"- **{domain}**: gained {', '.join(gained)}")
                    if lost:
                        print(f"- **{domain}**: lost {', '.join(lost)}")
                print()

        print(f"Snapshot saved to: {snapshot_path}")

    except NodeshubError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
