#!/usr/bin/env python3
"""
Iterative Keyword Research — expands keywords using SERP PAA + Related Searches in loops.

Each loop:
  1. Pick unprocessed keywords from the queue
  2. Run SERP on each (1 token) -> extract PAA questions + Related Searches
  3. Run Fan-out on seed keywords (7.5 tokens) -> extract generated variants
  4. Add all new unique keywords to the queue
  5. Repeat until loops exhausted or queue empty

Presets:
  conservative: 3 loops,  max 5 SERP/loop, fan-out on seed only
  standard:     5 loops,  max 10 SERP/loop, fan-out on top subtopics
  aggressive:  15 loops,  max 15 SERP/loop, fan-out on top subtopics
  beast:       30 loops,  max 20 SERP/loop, fan-out on top subtopics

Usage:
  python3 iterative_research.py "SEO" --gl pl --hl pl --preset standard
  python3 iterative_research.py "SEO" --gl pl --hl pl --loops 10 --serp-per-loop 8
  python3 iterative_research.py "SEO" --gl pl --hl pl --preset aggressive --output keywords.csv
  python3 iterative_research.py "SEO" --gl pl --hl pl --preset aggressive --budget 500
"""

import argparse
import csv
import json
import os
import socket
import sys
import time
import urllib.error
from collections import OrderedDict
from pathlib import Path

# Import shared client
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'nod-nodeshub-api' / 'scripts'))
from client import NodeshubClient, NodeshubError
from report import render_section_wrapper, make_section_id, html_table, summary_card, bar_chart, badge

MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds


def api_call_with_retry(fn, *args, **kwargs):
    """Call an API function with retry on timeout/connection errors."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return fn(*args, **kwargs)
        except (socket.timeout, urllib.error.URLError, OSError) as e:
            if attempt == MAX_RETRIES:
                raise NodeshubError(f"Failed after {MAX_RETRIES} retries: {e}")
            time.sleep(RETRY_DELAY * attempt)
        except NodeshubError:
            raise


PRESETS = {
    "conservative": {"loops": 3,  "serp_per_loop": 5,  "fanout_seeds": 1},
    "standard":     {"loops": 5,  "serp_per_loop": 10, "fanout_seeds": 3},
    "aggressive":   {"loops": 15, "serp_per_loop": 15, "fanout_seeds": 5},
    "beast":        {"loops": 30, "serp_per_loop": 20, "fanout_seeds": 5},
}


def extract_paa(serp_data):
    """Extract People Also Ask questions from SERP response."""
    questions = []
    try:
        snippets = serp_data["data"]["results"].get("snippets", {})
        paa = snippets.get("people_also_ask", {})
        for q in paa.get("questions", []):
            text = q.get("text", "").strip()
            if text:
                questions.append(text)
    except (KeyError, TypeError, AttributeError):
        pass
    return questions


def extract_related_searches(serp_data):
    """Extract Related Searches from SERP response."""
    queries = []
    try:
        snippets = serp_data["data"]["results"].get("snippets", {})
        related = snippets.get("related_searches", {})
        for q in related.get("queries", []):
            if isinstance(q, str) and q.strip():
                queries.append(q.strip())
    except (KeyError, TypeError, AttributeError):
        pass
    return queries


def extract_fanout_keywords(fanout_data):
    """Extract keywords from fan-out response."""
    keywords = []
    try:
        for variant in fanout_data.get("generated_variants", []):
            kw = variant.get("keyword", "").strip()
            if kw:
                keywords.append(kw)
    except (KeyError, TypeError, AttributeError):
        pass
    return keywords


def normalize(keyword):
    """Normalize keyword for deduplication."""
    return keyword.lower().strip()


def estimate_cost(loops, serp_per_loop, fanout_seeds, expand_popular_max=0):
    """Estimate total token cost."""
    serp_cost = loops * serp_per_loop * 1  # 1 token per SERP
    fanout_cost = fanout_seeds * 7.5  # fan-out on initial seeds
    popular_cost = expand_popular_max * 7.5  # fan-out on popular keywords
    return serp_cost + fanout_cost + popular_cost


def render_report_section(data):
    """Convert keyword research data into an HTML report section.

    Args:
        data: Dict with seed_keyword, gl, hl, total_keywords, tokens_used,
              serp_calls, fanout_calls, keywords (list of {keyword, source, type, loop, serp_overlap}).
    """
    from html import escape as e
    parts = []

    parts.append(summary_card([
        (e(str(data.get("seed_keyword", ""))), "Seed Keyword"),
        (str(data.get("total_keywords", 0)), "Keywords Found"),
        (f"{data.get('tokens_used', 0):.0f}", "Tokens Used"),
    ]))

    # Keywords table (top 50)
    keywords = data.get("keywords", [])
    if keywords:
        rows = []
        for kw_info in keywords[:50]:
            rows.append([
                e(str(kw_info.get("keyword", ""))),
                badge(e(str(kw_info.get("type", ""))), "info"),
                e(str(kw_info.get("source", ""))),
                str(kw_info.get("serp_overlap", 0)),
            ])
        if len(keywords) > 50:
            parts.append(f"<p><em>Showing top 50 of {len(keywords)} keywords</em></p>")
        parts.append(html_table(["Keyword", "Type", "Source", "Overlap"], rows))

    # Source breakdown bar chart
    type_counts = {}
    for kw_info in keywords:
        t = kw_info.get("type", "unknown")
        type_counts[t] = type_counts.get(t, 0) + 1
    if type_counts:
        chart_items = [(t, count, str(count))
                       for t, count in sorted(type_counts.items(), key=lambda x: -x[1])]
        parts.append("<h3>Source Breakdown</h3>")
        parts.append(bar_chart(chart_items))

    sid = make_section_id("keyword-research")
    seed = e(str(data.get("seed_keyword", "")))
    return render_section_wrapper(sid, "Keyword Research",
                                  f"Keyword Research: {seed}", "\n".join(parts))


def main():
    parser = argparse.ArgumentParser(
        description="Iterative keyword research using SERP PAA + Related Searches loops"
    )
    parser.add_argument("keyword", help="Seed keyword to start research")
    parser.add_argument("--gl", default="pl", help="Country code (default: pl)")
    parser.add_argument("--hl", default="pl", help="Language code (default: pl)")
    parser.add_argument("--preset", choices=PRESETS.keys(),
                        help="Research intensity preset")
    parser.add_argument("--loops", type=int, help="Number of loops (overrides preset)")
    parser.add_argument("--serp-per-loop", type=int,
                        help="Max SERP calls per loop (overrides preset)")
    parser.add_argument("--fanout-seeds", type=int,
                        help="Number of top keywords to fan-out on (overrides preset)")
    parser.add_argument("--budget", type=float,
                        help="Max tokens to spend (hard stop)")
    parser.add_argument("--output", "-o", help="Output CSV file path")
    parser.add_argument("--json", action="store_true", help="Also output JSON")
    parser.add_argument("--expand-popular", type=int, default=0, metavar="N",
                        help="Run fan-out on top N keywords that appear most often in PAA/Related "
                             "across multiple SERPs. Each costs 7.5 tokens. Set to 0 to disable.")
    parser.add_argument("--popular-threshold", type=int, default=2, metavar="T",
                        help="Min times a keyword must appear in PAA/Related to be considered popular (default: 2)")
    parser.add_argument("--serp-fanout", action="store_true", default=False,
                        help="SERP each fan-out result to extract PAA + Related Searches from it. "
                             "Produces many more keywords but costs 1 token per fan-out result. "
                             "Without this flag, fan-out results only enter the queue for later loops.")
    parser.add_argument("--quiet", "-q", action="store_true",
                        help="Minimal output (just final stats)")
    args = parser.parse_args()

    # Resolve settings from preset + overrides
    preset = PRESETS.get(args.preset, PRESETS["standard"])
    loops = args.loops or preset["loops"]
    serp_per_loop = args.serp_per_loop or preset["serp_per_loop"]
    fanout_seeds = args.fanout_seeds or preset["fanout_seeds"]
    expand_popular = args.expand_popular
    popular_threshold = args.popular_threshold
    budget = args.budget

    estimated = estimate_cost(loops, serp_per_loop, fanout_seeds, expand_popular)

    print(f"=== Iterative Keyword Research ===", file=sys.stderr)
    print(f"Seed: {args.keyword}", file=sys.stderr)
    print(f"Market: gl={args.gl}, hl={args.hl}", file=sys.stderr)
    print(f"Loops: {loops}, SERP/loop: {serp_per_loop}, Fan-out seeds: {fanout_seeds}", file=sys.stderr)
    if expand_popular:
        print(f"Expand popular: top {expand_popular} keywords (threshold: {popular_threshold}+ appearances)", file=sys.stderr)
    if args.serp_fanout:
        print(f"SERP fan-out: ON (every fan-out result gets SERPed for PAA + Related)", file=sys.stderr)
    print(f"Estimated max cost: {estimated} tokens", file=sys.stderr)
    if budget:
        print(f"Budget limit: {budget} tokens", file=sys.stderr)
    print(file=sys.stderr)

    try:
        client = NodeshubClient()
        balance = client.get_balance()
        tokens_left = float(balance.get("left", 0))
        print(f"Balance: {tokens_left} tokens", file=sys.stderr)

        effective_budget = min(budget, tokens_left) if budget else tokens_left
        if estimated > effective_budget:
            print(f"Warning: estimated cost ({estimated}) exceeds {'budget' if budget else 'balance'} ({effective_budget}). "
                  f"Will stop when budget runs out.", file=sys.stderr)
        print(file=sys.stderr)
    except NodeshubError as e:
        print(f"Error checking balance: {e}", file=sys.stderr)
        effective_budget = budget or float("inf")

    # State tracking
    # keyword -> {source, loop, type}
    all_keywords = OrderedDict()
    seen_normalized = set()
    processed_serp = set()  # keywords already SERP-checked
    tokens_used = 0
    serp_calls = 0
    fanout_calls = 0
    loop_stats = []  # per-loop: {loop, new_keywords, serp_calls, fanout_calls, tokens_spent}
    appearance_count = {}  # normalized keyword -> how many SERPs it appeared in (PAA/related)
    expanded_popular = set()  # keywords already fan-outed via expand-popular

    def add_keyword(kw, source, loop_num, kw_type):
        """Add keyword if not seen before. Returns True if new."""
        norm = normalize(kw)
        if norm in seen_normalized:
            return False
        seen_normalized.add(norm)
        all_keywords[kw] = {
            "source": source,
            "loop": loop_num,
            "type": kw_type,
        }
        return True

    def budget_ok(cost):
        """Check if we can afford the next API call."""
        return (tokens_used + cost) <= effective_budget

    def serp_harvest(keywords_to_serp, loop_num, label=""):
        """SERP a list of keywords and extract PAA + Related Searches.
        Returns count of new keywords discovered."""
        nonlocal tokens_used, serp_calls
        total_new = 0
        for kw in keywords_to_serp:
            norm = normalize(kw)
            if norm in processed_serp:
                continue
            if not budget_ok(1):
                break
            try:
                serp = api_call_with_retry(client.search, kw, gl=args.gl, hl=args.hl)
                tokens_used += 1
                serp_calls += 1
                processed_serp.add(norm)

                paa = extract_paa(serp)
                related = extract_related_searches(serp)

                for q in paa:
                    appearance_count[normalize(q)] = appearance_count.get(normalize(q), 0) + 1
                    if add_keyword(q, "paa", loop_num, "paa_question"):
                        total_new += 1
                for q in related:
                    appearance_count[normalize(q)] = appearance_count.get(normalize(q), 0) + 1
                    if add_keyword(q, "related_search", loop_num, "related_search"):
                        total_new += 1

                time.sleep(0.1)
            except (NodeshubError, socket.timeout, OSError) as e:
                if not args.quiet:
                    print(f"    SERP error for '{kw}': {e}", file=sys.stderr)
                processed_serp.add(norm)
                continue
        if total_new and not args.quiet and label:
            print(f"    {label} SERP harvest: +{total_new} new from {len(keywords_to_serp)} SERPs", file=sys.stderr)
        return total_new

    # === PHASE 1: Fan-out on seed keyword ===
    if not args.quiet:
        print(f"[Phase 1] Fan-out on seed: {args.keyword}", file=sys.stderr)

    add_keyword(args.keyword, "seed", 0, "seed")

    if budget_ok(7.5):
        try:
            fanout = api_call_with_retry(client.query_fanout, args.keyword, hl=args.hl, mode="standard",
                                         add_questions=True, add_topic_leaders=True)
            tokens_used += 7.5
            fanout_calls += 1
            fanout_kws = extract_fanout_keywords(fanout)
            new_count = 0
            for kw in fanout_kws:
                if add_keyword(kw, "fanout", 0, "fanout_variant"):
                    new_count += 1
            if not args.quiet:
                print(f"  Fan-out: +{new_count} new keywords", file=sys.stderr)
            # SERP harvest on fan-out results (if enabled)
            if args.serp_fanout:
                fanout_new_kws = [kw for kw in fanout_kws if normalize(kw) not in processed_serp]
                serp_harvest(fanout_new_kws, 0, label="Seed fan-out")
        except NodeshubError as e:
            print(f"  Fan-out error: {e}", file=sys.stderr)

    # === PHASE 2: SERP on seed keyword ===
    if budget_ok(1):
        try:
            serp = api_call_with_retry(client.search, args.keyword, gl=args.gl, hl=args.hl)
            tokens_used += 1
            serp_calls += 1
            processed_serp.add(normalize(args.keyword))

            paa = extract_paa(serp)
            related = extract_related_searches(serp)

            paa_new = 0
            for q in paa:
                appearance_count[normalize(q)] = appearance_count.get(normalize(q), 0) + 1
                if add_keyword(q, "paa", 0, "paa_question"):
                    paa_new += 1
            rel_new = 0
            for q in related:
                appearance_count[normalize(q)] = appearance_count.get(normalize(q), 0) + 1
                if add_keyword(q, "related_search", 0, "related_search"):
                    rel_new += 1

            if not args.quiet:
                print(f"  SERP seed: PAA +{paa_new}, Related +{rel_new}", file=sys.stderr)
        except NodeshubError as e:
            print(f"  SERP error: {e}", file=sys.stderr)

    # Record phase 0 stats
    phase0_kws = sum(1 for m in all_keywords.values() if m["loop"] == 0)
    loop_stats.append({
        "loop": 0, "label": "seed+fanout+SERP",
        "new_keywords": phase0_kws,
        "serp_calls": serp_calls, "fanout_calls": fanout_calls,
        "tokens_spent": tokens_used,
    })

    # === PHASE 3: Iterative SERP loops ===
    for loop_num in range(1, loops + 1):
        # Get unprocessed keywords, prioritize PAA and related_search types
        queue = [kw for kw in all_keywords
                 if normalize(kw) not in processed_serp]

        # Prioritize: paa_question > related_search > fanout_variant > seed
        priority = {"paa_question": 0, "related_search": 1, "fanout_variant": 2, "seed": 3}
        queue.sort(key=lambda kw: priority.get(all_keywords[kw]["type"], 9))

        if not queue:
            if not args.quiet:
                print(f"\n[Loop {loop_num}] Queue empty — stopping early.", file=sys.stderr)
            break

        batch = queue[:serp_per_loop]

        if not args.quiet:
            print(f"\n[Loop {loop_num}/{loops}] Processing {len(batch)} keywords "
                  f"(queue: {len(queue)}, total: {len(all_keywords)}, "
                  f"tokens: {tokens_used:.1f})", file=sys.stderr)

        loop_new = 0
        for kw in batch:
            if not budget_ok(1):
                print(f"  Budget exhausted at {tokens_used:.1f} tokens.", file=sys.stderr)
                break

            try:
                serp = api_call_with_retry(client.search, kw, gl=args.gl, hl=args.hl)
                tokens_used += 1
                serp_calls += 1
                processed_serp.add(normalize(kw))

                paa = extract_paa(serp)
                related = extract_related_searches(serp)

                for q in paa:
                    appearance_count[normalize(q)] = appearance_count.get(normalize(q), 0) + 1
                    if add_keyword(q, "paa", loop_num, "paa_question"):
                        loop_new += 1
                for q in related:
                    appearance_count[normalize(q)] = appearance_count.get(normalize(q), 0) + 1
                    if add_keyword(q, "related_search", loop_num, "related_search"):
                        loop_new += 1

            except (NodeshubError, socket.timeout, OSError) as e:
                print(f"  SERP error for '{kw}': {e}", file=sys.stderr)
                processed_serp.add(normalize(kw))  # don't retry
                continue

            # Small delay to be nice to the API
            time.sleep(0.1)

        if not args.quiet:
            print(f"  Loop {loop_num}: +{loop_new} new keywords", file=sys.stderr)

        # Optional: fan-out on top new keywords from this loop
        if loop_num <= 2 and fanout_seeds > 1:
            new_this_loop = [kw for kw, meta in all_keywords.items()
                            if meta["loop"] == loop_num and meta["type"] in ("paa_question", "related_search")]
            fanout_batch = new_this_loop[:fanout_seeds - 1]  # -1 because seed already done
            for kw in fanout_batch:
                if not budget_ok(7.5):
                    break
                try:
                    fanout = api_call_with_retry(client.query_fanout, kw, hl=args.hl, mode="standard",
                                                 add_questions=True)
                    tokens_used += 7.5
                    fanout_calls += 1
                    fanout_kws = extract_fanout_keywords(fanout)
                    fo_new = sum(1 for k in fanout_kws
                                if add_keyword(k, "fanout", loop_num, "fanout_variant"))
                    if not args.quiet:
                        print(f"  Fan-out '{kw}': +{fo_new} new", file=sys.stderr)
                    # SERP harvest on fan-out results (if enabled)
                    if args.serp_fanout:
                        fo_to_serp = [k for k in fanout_kws if normalize(k) not in processed_serp]
                        harvest = serp_harvest(fo_to_serp, loop_num, label=f"Fan-out '{kw}'")
                        loop_new += harvest
                except NodeshubError as e:
                    print(f"  Fan-out error for '{kw}': {e}", file=sys.stderr)

        # Record loop stats
        loop_serp = len([kw for kw in batch if normalize(kw) in processed_serp])
        loop_fanout = 0
        loop_tokens = loop_serp * 1  # 1 token per SERP
        if loop_num <= 2 and fanout_seeds > 1:
            new_this_loop_count = len([kw for kw, m in all_keywords.items()
                                       if m["loop"] == loop_num and m["type"] in ("paa_question", "related_search")])
            loop_fanout_batch = min(fanout_seeds - 1, new_this_loop_count)
            # fanout_calls were already tracked, approximate
        loop_stats.append({
            "loop": loop_num, "label": f"loop {loop_num}",
            "new_keywords": loop_new,
            "serp_calls": len(batch),
            "fanout_calls": 0,
            "tokens_spent": len(batch) * 1,
        })

        if not budget_ok(1):
            print(f"\nBudget limit reached ({tokens_used:.1f} tokens). Stopping.", file=sys.stderr)
            break

    # === PHASE 4: Expand popular keywords with fan-out ===
    if expand_popular > 0:
        # Find keywords that appeared in multiple SERPs (popular = high relevance)
        popular = sorted(
            [(kw, count) for kw, count in appearance_count.items() if count >= popular_threshold],
            key=lambda x: -x[1]
        )[:expand_popular]

        if popular:
            if not args.quiet:
                print(f"\n[Expand Popular] Found {len(popular)} keywords appearing {popular_threshold}+ times", file=sys.stderr)

            expand_new = 0
            expand_fanout = 0
            expand_tokens = 0.0
            for norm_kw, count in popular:
                if not budget_ok(7.5):
                    print(f"  Budget exhausted.", file=sys.stderr)
                    break
                # Find original casing
                original_kw = next((kw for kw in all_keywords if normalize(kw) == norm_kw), norm_kw)
                if norm_kw in expanded_popular:
                    continue
                expanded_popular.add(norm_kw)
                try:
                    fanout = api_call_with_retry(client.query_fanout, original_kw, hl=args.hl,
                                                 mode="standard", add_questions=True)
                    tokens_used += 7.5
                    expand_tokens += 7.5
                    fanout_calls += 1
                    expand_fanout += 1
                    fanout_kws = extract_fanout_keywords(fanout)
                    fo_new = sum(1 for k in fanout_kws
                                if add_keyword(k, "fanout_popular", 99, "fanout_popular"))
                    expand_new += fo_new
                    if not args.quiet:
                        print(f"  Fan-out '{original_kw}' (appeared {count}x): +{fo_new} new", file=sys.stderr)
                    # SERP harvest on expand-popular fan-out results (if enabled)
                    if args.serp_fanout:
                        ep_to_serp = [k for k in fanout_kws if normalize(k) not in processed_serp]
                        harvest = serp_harvest(ep_to_serp, 99, label=f"Popular '{original_kw}'")
                        expand_new += harvest
                except (NodeshubError, socket.timeout, OSError) as e:
                    print(f"  Fan-out error for '{original_kw}': {e}", file=sys.stderr)

            loop_stats.append({
                "loop": 99, "label": "expand-popular",
                "new_keywords": expand_new,
                "serp_calls": 0,
                "fanout_calls": expand_fanout,
                "tokens_spent": expand_tokens,
            })

            if not args.quiet:
                print(f"  Expand popular total: +{expand_new} new keywords ({expand_tokens:.1f} tokens)", file=sys.stderr)
        else:
            if not args.quiet:
                print(f"\n[Expand Popular] No keywords appeared {popular_threshold}+ times — skipping.", file=sys.stderr)

    # Show top popular keywords in report (always, for visibility)
    top_popular = sorted(appearance_count.items(), key=lambda x: -x[1])[:10]

    # === OUTPUT: Per-loop Report ===
    print(f"\n{'='*70}", file=sys.stderr)
    print(f"  KEYWORD RESEARCH REPORT", file=sys.stderr)
    print(f"{'='*70}", file=sys.stderr)
    print(f"  Seed: {args.keyword} | Market: gl={args.gl}, hl={args.hl}", file=sys.stderr)
    print(f"  Total unique keywords: {len(all_keywords)}", file=sys.stderr)
    print(f"  Total tokens used: {tokens_used:.1f}", file=sys.stderr)
    print(f"  SERP calls: {serp_calls} | Fan-out calls: {fanout_calls}", file=sys.stderr)
    print(f"{'='*70}", file=sys.stderr)

    # Per-loop table
    print(f"\n  {'Loop':<20} {'New KWs':>10} {'SERP':>8} {'Tokens':>10} {'Cumulative':>12}", file=sys.stderr)
    print(f"  {'-'*20} {'-'*10} {'-'*8} {'-'*10} {'-'*12}", file=sys.stderr)
    cumulative_kws = 0
    cumulative_tokens = 0.0
    for ls in loop_stats:
        cumulative_kws += ls["new_keywords"]
        cumulative_tokens += ls["tokens_spent"]
        print(f"  {ls['label']:<20} {ls['new_keywords']:>10} {ls['serp_calls']:>8} "
              f"{ls['tokens_spent']:>10.1f} {cumulative_kws:>8} kws", file=sys.stderr)

    # Type breakdown
    type_counts = {}
    for meta in all_keywords.values():
        t = meta["type"]
        type_counts[t] = type_counts.get(t, 0) + 1
    print(f"\n  By source:", file=sys.stderr)
    for t, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"    {t}: {count}", file=sys.stderr)

    # Popular keywords (appeared in multiple SERPs)
    if top_popular and top_popular[0][1] >= 2:
        print(f"\n  Most popular keywords (appeared in multiple SERPs):", file=sys.stderr)
        for kw, count in top_popular:
            if count < 2:
                break
            expanded_marker = " [expanded]" if kw in expanded_popular else ""
            print(f"    {count}x  {kw}{expanded_marker}", file=sys.stderr)

    print(f"{'='*70}", file=sys.stderr)

    # CSV output
    output_path = args.output
    if not output_path:
        safe_name = args.keyword.replace(" ", "_").replace("/", "_")[:30]
        output_path = f"output/keywords_{safe_name}_{args.gl}.csv"

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["keyword", "source", "type", "discovered_in_loop", "serp_overlap"])
        for kw, meta in all_keywords.items():
            overlap = appearance_count.get(normalize(kw), 0)
            writer.writerow([kw, meta["source"], meta["type"], meta["loop"], overlap])

    print(f"\nSaved to: {output_path}", file=sys.stderr)

    # JSON output
    if args.json:
        json_path = output_path.rsplit(".", 1)[0] + ".json"
        json_output = {
            "seed_keyword": args.keyword,
            "gl": args.gl,
            "hl": args.hl,
            "loops_completed": min(loop_num, loops) if 'loop_num' in dir() else 0,
            "total_keywords": len(all_keywords),
            "tokens_used": tokens_used,
            "serp_calls": serp_calls,
            "fanout_calls": fanout_calls,
            "keywords": [
                {"keyword": kw, **meta, "serp_overlap": appearance_count.get(normalize(kw), 0)}
                for kw, meta in all_keywords.items()
            ],
        }
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(json_output, f, indent=2, ensure_ascii=False)
        print(f"Saved JSON: {json_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
