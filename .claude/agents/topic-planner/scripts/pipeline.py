#!/usr/bin/env python3
"""
Topic Research Pipeline — seed keyword → keywords → clusters → competitor crawl → briefs.

Orchestrates 3 steps:
  1. Keyword Research (iterative SERP mining)
  2. SERP Clustering (Weighted Jaccard + Louvain)
  3. Competitor Crawl + Content Brief (Jina Reader + LLM)

Each step saves output to data/topics/[slug]/ — resumable from any step.

Usage:
  python3 pipeline.py "pozycjonowanie stron" --gl pl --hl pl
  python3 pipeline.py "SEO tools" --gl us --hl en --skip-to 2
  python3 pipeline.py "content marketing" --gl pl --hl pl --brief-clusters 5
"""

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[2]
NODESHUB_SCRIPTS = SCRIPTS_DIR / "nod-nodeshub-api" / "scripts"
KW_RESEARCH_SCRIPT = SCRIPTS_DIR / "nod-keyword-research" / "scripts" / "iterative_research.py"
CLUSTER_SCRIPT = SCRIPTS_DIR / "nod-serp-clusters" / "scripts" / "cluster.py"

sys.path.insert(0, str(NODESHUB_SCRIPTS))


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower().strip()).strip("-")[:50]


def run_step(cmd, step_name):
    """Run a subprocess and stream output."""
    print(f"\n{'='*60}", file=sys.stderr)
    print(f"  STEP: {step_name}", file=sys.stderr)
    print(f"{'='*60}\n", file=sys.stderr)

    result = subprocess.run(cmd, capture_output=False, text=True)
    if result.returncode != 0:
        print(f"\n  WARNING: {step_name} exited with code {result.returncode}", file=sys.stderr)
        return False
    return True


def main():
    parser = argparse.ArgumentParser(description="Topic Research Pipeline: keyword → clusters → briefs")
    parser.add_argument("keyword", help="Seed keyword / topic")
    parser.add_argument("--gl", default="pl", help="Country code (default: pl)")
    parser.add_argument("--hl", default="pl", help="Language code (default: pl)")
    parser.add_argument("--output-dir", help="Output directory (default: data/topics/[slug]/)")
    parser.add_argument("--skip-to", type=int, default=1, choices=[1, 2, 3],
                        help="Skip to step N (1=keywords, 2=clusters, 3=briefs)")
    # Step 1 params
    parser.add_argument("--kw-loops", type=int, default=3, help="Keyword research loops (default: 3)")
    parser.add_argument("--kw-serp-per-loop", type=int, default=5, help="SERPs per loop (default: 5)")
    parser.add_argument("--kw-expand-popular", type=int, default=3, help="Expand popular keywords (default: 3)")
    # Step 2 params
    parser.add_argument("--cluster-levels", type=int, default=3, choices=[1, 2, 3],
                        help="Clustering levels (default: 3)")
    parser.add_argument("--cluster-threshold", type=float, default=0.55, help="Jaccard threshold (default: 0.55)")
    # Step 3 params
    parser.add_argument("--brief-clusters", type=int, default=5,
                        help="Generate briefs for top N clusters (default: 5)")
    parser.add_argument("--brief-competitors", type=int, default=3,
                        help="Crawl top N competitor URLs per cluster (default: 3)")
    args = parser.parse_args()

    slug = slugify(args.keyword)
    output_dir = Path(args.output_dir) if args.output_dir else Path(f"data/topics/{slug}")
    output_dir.mkdir(parents=True, exist_ok=True)

    kw_csv = output_dir / "01_keywords.csv"
    cluster_csv = output_dir / "02_clusters.csv"
    cluster_json = output_dir / "02_clusters.json"
    cluster_report = output_dir / "02_clusters_report.html"
    briefs_dir = output_dir / "03_briefs"

    print(f"=== Topic Research Pipeline ===", file=sys.stderr)
    print(f"Topic: {args.keyword}", file=sys.stderr)
    print(f"Market: gl={args.gl}, hl={args.hl}", file=sys.stderr)
    print(f"Output: {output_dir}/", file=sys.stderr)
    print(f"Skip to step: {args.skip_to}", file=sys.stderr)

    # ── STEP 1: Keyword Research ──
    if args.skip_to <= 1:
        cmd = [
            sys.executable, str(KW_RESEARCH_SCRIPT),
            args.keyword,
            "--gl", args.gl, "--hl", args.hl,
            "--loops", str(args.kw_loops),
            "--serp-per-loop", str(args.kw_serp_per_loop),
            "--expand-popular", str(args.kw_expand_popular),
            "--output", str(kw_csv),
            "--json",
        ]
        if not run_step(cmd, "Keyword Research"):
            print("Step 1 failed. Fix and rerun, or --skip-to 2 with existing CSV.", file=sys.stderr)
            sys.exit(1)
    else:
        if not kw_csv.exists():
            print(f"ERROR: {kw_csv} not found. Run step 1 first.", file=sys.stderr)
            sys.exit(1)
        print(f"\nSkipping step 1 — using {kw_csv}", file=sys.stderr)

    # Count keywords
    with open(kw_csv) as f:
        kw_count = sum(1 for _ in f) - 1
    print(f"\nKeywords: {kw_count}", file=sys.stderr)

    # ── STEP 2: Clustering ──
    if args.skip_to <= 2:
        cmd = [
            sys.executable, str(CLUSTER_SCRIPT),
            str(kw_csv),
            "--gl", args.gl, "--hl", args.hl,
            "--levels", str(args.cluster_levels),
            "--threshold", str(args.cluster_threshold),
            "--workers", "3",
            "--report", "html",
            "--output", str(cluster_csv),
            "--json",
        ]
        if not run_step(cmd, "SERP Clustering"):
            print("Step 2 failed. Fix and rerun, or --skip-to 3 with existing clusters.", file=sys.stderr)
            sys.exit(1)
    else:
        if not cluster_csv.exists():
            print(f"ERROR: {cluster_csv} not found. Run step 2 first.", file=sys.stderr)
            sys.exit(1)
        print(f"\nSkipping step 2 — using {cluster_csv}", file=sys.stderr)

    # ── STEP 3: Competitor Crawl + Brief ──
    if args.skip_to <= 3:
        print(f"\n{'='*60}", file=sys.stderr)
        print(f"  STEP: Competitor Crawl + Content Briefs", file=sys.stderr)
        print(f"{'='*60}\n", file=sys.stderr)

        briefs_dir.mkdir(parents=True, exist_ok=True)

        # Load cluster JSON to get top clusters + their URLs
        if cluster_json.exists():
            with open(cluster_json) as f:
                cluster_data = json.load(f)
        else:
            print("No cluster JSON — generating basic briefs from CSV only.", file=sys.stderr)
            cluster_data = None

        # Import clients
        from jina_client import JinaClient
        from openrouter_client import OpenRouterClient

        jina = JinaClient()
        llm = OpenRouterClient()

        # Get top clusters from the most specific level
        top_clusters = []
        if cluster_data and "levels" in cluster_data:
            last_level = list(cluster_data["levels"].keys())[-1]
            clusters = cluster_data["levels"][last_level]["clusters"]
            # Sort by size, take top N with 2+ keywords
            top_clusters = sorted(clusters, key=lambda c: -len(c["keywords"]))
            top_clusters = [c for c in top_clusters if len(c["keywords"]) >= 2][:args.brief_clusters]

        if not top_clusters:
            # Fallback: read CSV and group
            print("No multi-keyword clusters found. Generating single brief for topic.", file=sys.stderr)
            top_clusters = [{"id": 0, "name": args.keyword, "keywords": [args.keyword]}]

        # Load SERP data from cluster cache (if available) for competitor URLs
        serp_cache_path = str(cluster_csv).replace(".csv", "_serp_cache.json")
        serp_cache = {}
        if os.path.exists(serp_cache_path):
            with open(serp_cache_path) as f:
                serp_cache = json.load(f)
            print(f"Loaded SERP cache: {len(serp_cache.get('all_serps', {}))} keywords", file=sys.stderr)

        all_serps = serp_cache.get("all_serps", {})

        for i, cluster in enumerate(top_clusters):
            cname = cluster.get("name", f"Cluster {cluster['id']}")
            kws = cluster["keywords"]
            print(f"\n--- Brief {i+1}/{len(top_clusters)}: {cname} ({len(kws)} kws) ---", file=sys.stderr)

            # Find top competitor URLs from SERP data
            domain_urls = {}
            for kw in kws:
                for r in all_serps.get(kw, []):
                    url = r.get("url", "")
                    domain = r.get("domain", "")
                    if url and domain:
                        if domain not in domain_urls:
                            domain_urls[domain] = {"url": url, "count": 0}
                        domain_urls[domain]["count"] += 1

            top_urls = sorted(domain_urls.values(), key=lambda x: -x["count"])[:args.brief_competitors]
            urls_to_crawl = [u["url"] for u in top_urls]

            # Crawl competitors
            competitor_content = ""
            if urls_to_crawl:
                print(f"  Crawling {len(urls_to_crawl)} competitor URLs...", file=sys.stderr)
                results = jina.read_batch(urls_to_crawl, workers=2)
                consolidated = jina.consolidate(results)
                competitor_content = consolidated["consolidated_md"]
                print(f"  OK: {consolidated['ok_count']}, Skip: {consolidated['skip_count']}, "
                      f"Error: {consolidated['error_count']}", file=sys.stderr)

            # Generate brief via LLM
            kw_list = ", ".join(kws[:20])
            lang = "Polish" if args.hl == "pl" else "English"

            prompt = f"""Generate a content brief in {lang} for the following keyword cluster.

Cluster name: {cname}
Keywords ({len(kws)}): {kw_list}

{"Competitor content analysis:" + chr(10) + competitor_content[:3000] if competitor_content else "No competitor content available."}

Create a content brief with:
1. Target keyword & intent
2. Suggested H1 title
3. H2/H3 structure (use the keywords as inspiration)
4. Key points to cover per section
5. Estimated word count
6. SEO checklist
7. Differentiation angle (what's missing from competitors)

Write the brief in markdown format."""

            try:
                print(f"  Generating brief via LLM...", file=sys.stderr)
                brief = llm.chat(prompt, model="google/gemini-2.5-flash-lite",
                                temperature=0.3, max_tokens=3000)

                # Save brief
                safe_name = re.sub(r"[^a-z0-9]+", "-", cname.lower())[:40]
                brief_path = briefs_dir / f"brief_{i+1}_{safe_name}.md"
                brief_path.write_text(f"# Content Brief: {cname}\n\n"
                                     f"**Keywords:** {kw_list}\n\n"
                                     f"---\n\n{brief}\n")
                print(f"  Saved: {brief_path}", file=sys.stderr)

            except Exception as e:
                print(f"  LLM error: {e}", file=sys.stderr)

    # ── Summary ──
    print(f"\n{'='*60}", file=sys.stderr)
    print(f"  PIPELINE COMPLETE", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)
    print(f"  Topic: {args.keyword}", file=sys.stderr)
    print(f"  Output: {output_dir}/", file=sys.stderr)
    print(f"  Files:", file=sys.stderr)
    for f in sorted(output_dir.rglob("*")):
        if f.is_file():
            size = f.stat().st_size
            print(f"    {f.relative_to(output_dir)} ({size:,} bytes)", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)


if __name__ == "__main__":
    main()
