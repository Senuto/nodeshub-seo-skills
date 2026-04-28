#!/usr/bin/env python3
"""SERP-based Keyword Clustering — Weighted Jaccard + Louvain (CLI entry).

Algorithm:
  1. SERP fetch — top-10 organic URLs per keyword (concurrent)
  2. Weighted Jaccard similarity — position-weighted URL matching + domain soft match
  3. Dynamic domain weighting — reduce impact of ubiquitous domains (Wikipedia, etc.)
  4. Louvain community detection — avoids chain clustering of naive agglomerative
  5. Multi-level via Louvain resolution parameter
  6. LLM naming — OpenRouter generates cluster names
  7. Optional HTML/MD report with domain visibility, snippets analysis

Usage:
  python3 cluster.py keywords.csv --gl pl --hl pl
  python3 cluster.py keywords.csv --gl pl --hl pl --levels 3 --report html
  python3 cluster.py keywords.csv --gl pl --hl pl --threshold 0.4 --workers 8

Algorithm modules live in clustering/. This file is the CLI entry only.
"""

import argparse
import csv
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'nod-nodeshub-api' / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from client import NodeshubClient
from openrouter_client import OpenRouterClient

from clustering.pipeline import run_clustering
from clustering.report_html import generate_html_report
from clustering.report_md import generate_md_report


def _read_keywords_csv(path, top_n=0):
    """Read keywords CSV, sort by serp_overlap if present, optionally trim."""
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append(row)
    if not rows:
        print("Error: empty CSV", file=sys.stderr)
        sys.exit(1)
    if "serp_overlap" in rows[0]:
        rows.sort(key=lambda r: -int(r.get("serp_overlap", 0)))
    if top_n > 0:
        rows = rows[:top_n]
    return rows


def _write_clustered_csv(output_path, rows, all_level_results, levels):
    """Write enriched CSV with one cluster_id/name/size column triple per level."""
    kw_to_cluster = {row["keyword"]: {} for row in rows}
    for level_name, level_data in all_level_results.items():
        for cid, kws in level_data["clusters"].items():
            for kw in kws:
                if kw in kw_to_cluster:
                    kw_to_cluster[kw][f"{level_name}_id"] = cid
                    kw_to_cluster[kw][f"{level_name}_name"] = level_data["names"].get(cid, "")
                    kw_to_cluster[kw][f"{level_name}_size"] = len(kws)

    cluster_fields = []
    for level_name, _, _ in levels:
        cluster_fields.extend([f"{level_name}_id", f"{level_name}_name", f"{level_name}_size"])

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        fieldnames = list(rows[0].keys()) + cluster_fields
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            kw = row["keyword"]
            info = kw_to_cluster.get(kw, {})
            for level_name, _, _ in levels:
                info.setdefault(f"{level_name}_id", -1)
                info.setdefault(f"{level_name}_name", "unclustered")
                info.setdefault(f"{level_name}_size", 0)
            row.update(info)
            writer.writerow(row)


def _write_json_summary(json_path, args, result):
    """Write JSON summary of all levels."""
    out = {
        "input": args.input, "gl": args.gl, "hl": args.hl,
        "tokens_used": result["tokens_used"],
        "keywords_with_serp": len(result["all_serps"]),
        "levels": {},
    }
    for level_name, ld in result["all_level_results"].items():
        out["levels"][level_name] = {
            "threshold": ld["threshold"], "resolution": ld["resolution"],
            "clusters": [{"id": cid, "name": ld["names"].get(cid, ""), "keywords": kws}
                         for cid, kws in sorted(ld["clusters"].items(), key=lambda x: -len(x[1]))],
        }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)


def _print_summary(result, keywords):
    """Stderr summary block — kept for backward CLI compatibility."""
    log = lambda msg: print(msg, file=sys.stderr)
    log(f"\n{'='*70}")
    log(f"  SERP CLUSTERING REPORT (Weighted Jaccard + Louvain)")
    log(f"{'='*70}")
    log(f"  Keywords: {len(keywords)} -> {len(result['all_serps'])} with SERP | Tokens: {result['tokens_used']}")
    for level_name, ld in result["all_level_results"].items():
        clusters = ld["clusters"]
        names = ld["names"]
        sorted_c = sorted(clusters.items(), key=lambda x: -len(x[1]))
        multi = sum(1 for _, kws in sorted_c if len(kws) >= 2)
        log(f"\n  --- {level_name} (threshold: {ld['threshold']:.2f}, resolution: {ld['resolution']}) ---")
        log(f"  Clusters: {len(clusters)} | Multi: {multi}")
        for cid, kws in sorted_c[:10]:
            if len(kws) < 2:
                break
            name = names.get(cid, "?")
            sample = ", ".join(kws[:4])
            more = f" +{len(kws)-4}" if len(kws) > 4 else ""
            log(f"    [{len(kws):>3}] {name}: {sample}{more}")
    log(f"{'='*70}")


def main():
    parser = argparse.ArgumentParser(description="SERP-based keyword clustering (Weighted Jaccard + Louvain)")
    parser.add_argument("input", help="Input CSV (must have 'keyword' column)")
    parser.add_argument("--gl", default="pl", help="Country code (default: pl)")
    parser.add_argument("--hl", default="pl", help="Language code (default: pl)")
    parser.add_argument("--threshold", type=float, default=0.55,
                        help="Min weighted Jaccard to create edge (default: 0.55 ≈ 7/10 shared)")
    parser.add_argument("--levels", type=int, default=1, choices=[1, 2, 3],
                        help="Clustering depth via Louvain resolution (1-3)")
    parser.add_argument("--domain-bonus", type=float, default=0.3,
                        help="Bonus for same-domain different-URL match (default: 0.3)")
    parser.add_argument("--min-shared-urls", type=int, default=2,
                        help="Min exact URL overlap to even compute similarity (default: 2)")
    parser.add_argument("--min-cluster-size", type=int, default=1,
                        help="Min keywords per cluster in report/dendrogram. Singletons stay in CSV but are hidden in visuals (default: 1)")
    parser.add_argument("--high-coverage", type=float, default=0.10,
                        help="Domain coverage threshold for weight reduction (default: 0.10)")
    parser.add_argument("--very-high-coverage", type=float, default=0.30,
                        help="Domain coverage threshold for mega-domain extra penalty (default: 0.30)")
    parser.add_argument("--max-pairs-per-domain", type=int, default=20000,
                        help="Max keyword pairs evaluated per domain (default: 20000)")
    parser.add_argument("--top-n", type=int, default=0,
                        help="Only cluster top N keywords (0=all)")
    parser.add_argument("--workers", type=int, default=3,
                        help="Concurrent SERP requests (default: 3)")
    parser.add_argument("--resolution", type=float, default=None,
                        help="Override Louvain resolution for all levels (higher=more clusters)")
    parser.add_argument("--budget", type=float, help="Max NodesHub tokens")
    parser.add_argument("--model", default="google/gemini-2.5-flash-lite")
    parser.add_argument("--report", choices=["html", "md"], default=None,
                        help="Generate analysis report (html or md)")
    parser.add_argument("--output", "-o", help="Output CSV path")
    parser.add_argument("--json", action="store_true", help="Also output JSON")
    parser.add_argument("--no-cache", action="store_true", help="Force fresh SERP fetch, ignoring existing cache")
    args = parser.parse_args()

    rows = _read_keywords_csv(args.input, top_n=args.top_n)
    keywords = [row["keyword"] for row in rows]

    print(f"=== SERP Clustering (Weighted Jaccard + Louvain) ===", file=sys.stderr)
    print(f"Keywords: {len(keywords)} | Threshold: {args.threshold} | Levels: {args.levels}", file=sys.stderr)
    print(f"Workers: {args.workers} | Domain bonus: {args.domain_bonus}", file=sys.stderr)

    serp_client = NodeshubClient()
    llm_client = OpenRouterClient()

    balance = serp_client.get_balance()
    tokens_left = float(balance.get("left", 0))
    print(f"Balance: {tokens_left} tokens", file=sys.stderr)
    effective_budget = min(args.budget, tokens_left) if args.budget else tokens_left

    output_stem = Path(args.output).stem if args.output else f"{Path(args.input).stem}_clustered"
    output_dir = Path(args.output).parent if args.output else Path(args.input).parent
    cache_path = output_dir / f"{output_stem}_serp_cache.json"

    batch_kws = keywords[:int(effective_budget)]

    result = run_clustering(
        batch_kws, serp_client, llm_client,
        gl=args.gl, hl=args.hl,
        threshold=args.threshold, levels=args.levels,
        domain_bonus=args.domain_bonus, min_shared_urls=args.min_shared_urls,
        high_coverage=args.high_coverage, very_high_coverage=args.very_high_coverage,
        max_pairs_per_domain=args.max_pairs_per_domain,
        workers=args.workers, resolution=args.resolution,
        cache_path=str(cache_path), no_cache=args.no_cache,
        model=args.model,
    )

    output_path = args.output or str(Path(args.input).parent / f"{Path(args.input).stem}_clustered.csv")
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    _write_clustered_csv(output_path, rows, result["all_level_results"], result["levels"])
    print(f"\nSaved: {output_path}", file=sys.stderr)

    if args.json:
        json_path = output_path.rsplit(".", 1)[0] + ".json"
        _write_json_summary(json_path, args, result)
        print(f"Saved: {json_path}", file=sys.stderr)

    if args.report:
        if args.report == "html":
            report = generate_html_report(result["all_level_results"],
                                          result["all_serps"], result["all_snippets"])
            ext = "html"
        else:
            report = generate_md_report(result["all_level_results"],
                                        result["all_serps"], result["all_snippets"])
            ext = "md"
        report_path = output_path.rsplit(".", 1)[0] + f"_report.{ext}"
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"Saved report: {report_path}", file=sys.stderr)

    _print_summary(result, keywords)


if __name__ == "__main__":
    main()
