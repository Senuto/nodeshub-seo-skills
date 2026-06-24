#!/usr/bin/env python3
"""Brief Builder — turn a user-provided keyword list into content briefs.

This skill is mostly orchestration. It reuses two existing skills:

  * nod-serp-clusters  — clusters the keyword list (each cluster = a candidate
    page). SERP method imports `run_clustering` directly; semantic method runs
    the `cluster_semantic.py` CLI as a subprocess.
  * nod-content-brief  — for each cluster it reuses `research.py` (SERP + Query
    Fan-out research) on the cluster's primary keyword, folding the remaining
    cluster keywords in as secondary targets.

Pipeline:
  1. Cluster the input keyword list (--method serp|semantic).
  2. Map every keyword to its cluster and pick a primary keyword per cluster.
  3. For each cluster (up to --max-briefs) generate a brief from research.

Outputs land in data/briefs/{slug}/:
  * mapping.json            — keyword -> cluster -> page mapping
  * brief-{cluster}.md      — one brief per cluster

Cost (be explicit with the user before running):
  * Clustering (serp method) = 1 NodesHub token per keyword.
  * Clustering (semantic method) = no NodesHub tokens (OpenRouter embeddings only).
  * Each brief = ~8.5 NodesHub tokens (standard) or ~31 (reasoning).

  --dry-run  does clustering + mapping only (clustering cost, no briefs).
  --demo     runs on a tiny built-in keyword list with mocked clustering and
             mocked research, so it is fully testable without any API keys.

Usage:
  python3 build.py --file keywords.txt --method serp --gl us --hl en
  python3 build.py --keywords "crm software,best crm,crm pricing" --max-briefs 3
  python3 build.py --file keywords.txt --dry-run
  python3 build.py --demo
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Skill roots — reused, never edited.
SKILLS_DIR = Path(__file__).resolve().parents[2]
NODESHUB_SCRIPTS = SKILLS_DIR / "nod-nodeshub-api" / "scripts"
CLUSTERS_SCRIPTS = SKILLS_DIR / "nod-serp-clusters" / "scripts"
BRIEF_SCRIPTS = SKILLS_DIR / "nod-content-brief" / "scripts"

REPO_ROOT = SKILLS_DIR.parents[1]  # repo root (two levels up from .claude/skills)
OUTPUT_BASE = REPO_ROOT / "data" / "briefs"

BRIEF_TOKENS = {"standard": 8.5, "reasoning": 31}


def _log(msg: str) -> None:
    print(msg, file=sys.stderr)


def slugify(text: str) -> str:
    """Filesystem-safe slug from arbitrary text."""
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-") or "cluster"


def read_keywords(args) -> list:
    """Collect the input keyword list from --file or --keywords (deduped, ordered)."""
    raw = []
    if args.file:
        path = Path(args.file)
        if not path.exists():
            _log(f"Error: file not found: {args.file}")
            sys.exit(1)
        raw = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    elif args.keywords:
        raw = [k.strip() for k in args.keywords.split(",")]
    seen = set()
    keywords = []
    for kw in raw:
        if kw and kw.lower() not in seen:
            seen.add(kw.lower())
            keywords.append(kw)
    return keywords


# ──────────────────────────────────────────────────────────────────────────
# Step 1 — Clustering (reuse nod-serp-clusters)
# ──────────────────────────────────────────────────────────────────────────

def _normalize_clusters(clusters: list) -> list:
    """Coerce clusters into [{'name': str, 'keywords': [str, ...]}], dropping empties."""
    out = []
    for c in clusters:
        kws = [k for k in c.get("keywords", []) if k]
        if kws:
            out.append({"name": c.get("name") or kws[0], "keywords": kws})
    out.sort(key=lambda c: -len(c["keywords"]))
    return out


def cluster_serp(keywords: list, args) -> dict:
    """Cluster via nod-serp-clusters by importing run_clustering directly."""
    sys.path.insert(0, str(NODESHUB_SCRIPTS))
    sys.path.insert(0, str(CLUSTERS_SCRIPTS))
    from client import NodeshubClient  # noqa: E402
    from openrouter_client import OpenRouterClient  # noqa: E402
    from clustering.pipeline import run_clustering  # noqa: E402

    serp_client = NodeshubClient()
    llm_client = OpenRouterClient()

    result = run_clustering(
        keywords, serp_client, llm_client,
        gl=args.gl, hl=args.hl,
        threshold=args.threshold, levels=1,
        workers=args.workers,
        log=_log,
    )

    # Single flat level ("cluster") — collapse to name/keywords pairs.
    level = next(iter(result["all_level_results"].values()))
    clusters = [
        {"name": level["names"].get(cid, ""), "keywords": kws}
        for cid, kws in level["clusters"].items()
    ]
    return {
        "clusters": _normalize_clusters(clusters),
        "tokens_used": result.get("tokens_used", 0),
        "method": "serp",
    }


def cluster_semantic(keywords: list, args, work_dir: Path) -> dict:
    """Cluster via nod-serp-clusters' semantic CLI (subprocess + JSON parse)."""
    in_csv = work_dir / "_input.csv"
    in_csv.write_text("keyword\n" + "\n".join(keywords) + "\n", encoding="utf-8")
    out_csv = work_dir / "_semantic_clustered.csv"

    cmd = [
        sys.executable, str(CLUSTERS_SCRIPTS / "cluster_semantic.py"), str(in_csv),
        "--threshold", str(args.semantic_threshold),
        "--levels", "1", "--hl", args.hl,
        "--output", str(out_csv), "--json",
    ]
    _log(f"[semantic] running: {' '.join(cmd)}")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        _log(proc.stderr)
        _log("Error: semantic clustering failed")
        sys.exit(1)

    json_path = out_csv.with_suffix(".json")
    if not json_path.exists():
        _log("Error: semantic clustering produced no JSON summary")
        sys.exit(1)
    summary = json.loads(json_path.read_text(encoding="utf-8"))
    level = next(iter(summary.get("levels", {}).values()), {"clusters": []})
    clusters = [
        {"name": c.get("name", ""), "keywords": c.get("keywords", [])}
        for c in level.get("clusters", [])
    ]
    return {
        "clusters": _normalize_clusters(clusters),
        "tokens_used": 0,
        "method": "semantic",
    }


def cluster_demo(keywords: list) -> dict:
    """Deterministic mocked clustering — groups by shared first word. No API."""
    buckets = {}
    for kw in keywords:
        key = kw.split()[0].lower() if kw.split() else kw.lower()
        buckets.setdefault(key, []).append(kw)
    clusters = [{"name": f"{key.title()} cluster (mocked)", "keywords": kws}
                for key, kws in buckets.items()]
    return {"clusters": _normalize_clusters(clusters), "tokens_used": 0, "method": "demo"}


# ──────────────────────────────────────────────────────────────────────────
# Step 2 — Mapping
# ──────────────────────────────────────────────────────────────────────────

def pick_primary(cluster: dict, volumes: dict) -> str:
    """Primary keyword = highest volume if known, else first keyword in cluster."""
    kws = cluster["keywords"]
    if volumes:
        ranked = sorted(kws, key=lambda k: -float(volumes.get(k, 0)))
        if float(volumes.get(ranked[0], 0)) > 0:
            return ranked[0]
    return kws[0]


def build_mapping(clusters: list, volumes: dict) -> dict:
    """Build the keyword -> cluster -> page mapping structure."""
    pages = []
    keyword_index = {}
    for i, cluster in enumerate(clusters):
        primary = pick_primary(cluster, volumes)
        secondary = [k for k in cluster["keywords"] if k != primary]
        slug = slugify(cluster["name"] or primary)
        page = {
            "cluster_id": i,
            "cluster_name": cluster["name"],
            "page_slug": slug,
            "primary_keyword": primary,
            "secondary_keywords": secondary,
            "keyword_count": len(cluster["keywords"]),
        }
        pages.append(page)
        for kw in cluster["keywords"]:
            keyword_index[kw] = {
                "cluster_id": i,
                "cluster_name": cluster["name"],
                "page_slug": slug,
                "role": "primary" if kw == primary else "secondary",
            }
    return {"pages": pages, "keyword_to_page": keyword_index}


# ──────────────────────────────────────────────────────────────────────────
# Step 3 — Briefs (reuse nod-content-brief research)
# ──────────────────────────────────────────────────────────────────────────

def research_real(primary: str, args) -> dict:
    """Reuse nod-content-brief's research.py to fetch SERP + Fan-out data."""
    sys.path.insert(0, str(NODESHUB_SCRIPTS))
    sys.path.insert(0, str(BRIEF_SCRIPTS))
    import research  # noqa: E402  (research.py from nod-content-brief)
    from client import NodeshubClient  # noqa: E402

    client = NodeshubClient()
    serp_raw = client.search(primary, gl=args.gl, hl=args.hl)
    serp_insights = research.extract_serp_insights(serp_raw)
    fanout_raw = client.query_fanout(
        primary, hl=args.hl, mode=args.mode,
        add_questions=True, add_topic_leaders=True,
    )
    return {
        "keyword": primary,
        "serp": serp_insights,
        "fanout": fanout_raw,
        "tokens_used": BRIEF_TOKENS.get(args.mode, BRIEF_TOKENS["standard"]),
        "mocked": False,
    }


def research_mock(primary: str) -> dict:
    """Mocked research payload — clearly labelled, no API calls."""
    return {
        "keyword": primary,
        "serp": {
            "dominant_intent": "informational",
            "serp_features": ["people_also_ask", "related_searches"],
            "domains": ["example.com", "competitor.org", "guide.io"],
            "organic_results": [
                {"title": f"The complete guide to {primary}", "domain": "example.com"},
                {"title": f"{primary}: everything you need to know", "domain": "competitor.org"},
            ],
        },
        "fanout": {
            "related_queries": [f"{primary} tips", f"{primary} examples", f"best {primary}"],
            "questions": [f"What is {primary}?", f"How does {primary} work?",
                          f"Why is {primary} important?"],
            "topic_leaders": ["example.com", "competitor.org"],
        },
        "tokens_used": 0,
        "mocked": True,
    }


def render_brief_md(page: dict, research: dict) -> str:
    """Render a content brief in markdown, folding secondary keywords in."""
    serp = research.get("serp", {})
    fanout = research.get("fanout", {})
    primary = page["primary_keyword"]
    secondary = page["secondary_keywords"]
    mocked = research.get("mocked")

    questions = fanout.get("questions", []) or []
    related = fanout.get("related_queries", []) or []
    features = serp.get("serp_features", []) or []
    domains = serp.get("domains") or serp.get("top_domains") or []
    intent = serp.get("dominant_intent", "unknown")

    lines = [f"# Content Brief: {page['cluster_name']}", ""]
    if mocked:
        lines += ["> NOTE: MOCKED DEMO OUTPUT — research data is fabricated, "
                  "not from live NodesHub APIs.", ""]
    lines += [
        f"**Page slug:** `{page['page_slug']}`  ",
        f"**Primary keyword:** {primary}  ",
        f"**Intent:** {intent}",
        "",
        "## Target Keywords",
        f"- **Primary:** {primary}",
    ]
    if secondary:
        lines.append("- **Secondary (same page):**")
        lines += [f"  - {kw}" for kw in secondary]
    else:
        lines.append("- **Secondary (same page):** none — single-keyword cluster")

    lines += ["", "## Search Landscape",
              f"- **SERP features:** {', '.join(features) if features else 'none detected'}",
              f"- **Top domains:** {', '.join(domains) if domains else 'n/a'}", ""]

    lines.append("## Questions to Answer")
    if questions:
        lines += [f"- {q}" for q in questions]
    else:
        lines.append("- (no questions returned)")
    lines.append("")

    lines += ["## Suggested Structure",
              f"**H1:** {primary.capitalize()}", ""]
    for q in questions[:4]:
        lines.append(f"**H2:** {q}")
    for r in related[:3]:
        lines.append(f"**H2:** {r.capitalize()}")
    if secondary:
        lines.append("**H2:** Related topics")
        lines += [f"- cover: {kw}" for kw in secondary]
    lines += ["**H2:** FAQ"] + [f"- {q}" for q in questions[:3]]

    lines += ["", "## Notes",
              "- This brief is one of several generated from a keyword list by "
              "nod-brief-builder (reusing nod-content-brief research).",
              f"- All {page['keyword_count']} cluster keyword(s) map to this single page."]
    return "\n".join(lines) + "\n"


# ──────────────────────────────────────────────────────────────────────────
# Orchestration
# ──────────────────────────────────────────────────────────────────────────

def print_summary(mapping: dict, clusters_meta: dict, briefs_written: list, args) -> None:
    print("\n" + "=" * 70)
    print("  BRIEF BUILDER SUMMARY")
    print("=" * 70)
    method = clusters_meta["method"]
    print(f"  Method: {method}{'  (MOCKED DEMO)' if args.demo else ''}")
    print(f"  Clusters / candidate pages: {len(mapping['pages'])}")
    print(f"  Keywords mapped: {len(mapping['keyword_to_page'])}")
    print(f"  Clustering tokens: {clusters_meta['tokens_used']}")
    print("\n  Keyword -> page mapping:")
    for page in mapping["pages"]:
        print(f"    [{page['cluster_id']}] {page['cluster_name']} "
              f"-> /{page['page_slug']}")
        print(f"        primary:   {page['primary_keyword']}")
        if page["secondary_keywords"]:
            print(f"        secondary: {', '.join(page['secondary_keywords'])}")
    if args.dry_run:
        print("\n  --dry-run: clustering + mapping only, no briefs generated.")
    else:
        print(f"\n  Briefs generated: {len(briefs_written)}")
        for path in briefs_written:
            print(f"    - {path}")
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(
        description="Brief Builder — keyword list -> clusters -> mapping -> briefs")
    parser.add_argument("--file", help="Path to keyword list (one keyword per line)")
    parser.add_argument("--keywords", help="Comma-separated keyword list")
    parser.add_argument("--method", choices=["serp", "semantic"], default="serp",
                        help="Clustering method (default: serp)")
    parser.add_argument("--gl", default="us", help="Country code (default: us)")
    parser.add_argument("--hl", default="en", help="Language code (default: en)")
    parser.add_argument("--threshold", type=float, default=0.55,
                        help="SERP clustering similarity threshold (default: 0.55)")
    parser.add_argument("--semantic-threshold", type=float, default=0.25,
                        help="Semantic clustering cosine threshold (default: 0.25)")
    parser.add_argument("--workers", type=int, default=3,
                        help="Concurrent SERP requests for clustering (default: 3)")
    parser.add_argument("--mode", choices=["standard", "reasoning"], default="standard",
                        help="Brief research mode (default: standard)")
    parser.add_argument("--max-briefs", type=int, default=0,
                        help="Max briefs to generate (0 = one per cluster)")
    parser.add_argument("--slug", help="Run slug for output folder (default: timestamp)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Clustering + mapping only, no briefs")
    parser.add_argument("--demo", action="store_true",
                        help="Run on a built-in keyword list with mocked clustering + research")
    args = parser.parse_args()

    if args.demo:
        keywords = [
            "crm software", "best crm", "crm pricing", "crm for startups",
            "email marketing", "email automation", "email campaign tools",
        ]
        _log("[demo] using built-in mocked keyword list (no API keys needed)")
    else:
        keywords = read_keywords(args)
    if not keywords:
        _log("Error: no keywords provided. Use --file, --keywords, or --demo.")
        sys.exit(1)

    run_slug = slugify(args.slug) if args.slug else (
        "demo" if args.demo else datetime.now(timezone.utc).strftime("run-%Y%m%d-%H%M%S"))
    work_dir = OUTPUT_BASE / run_slug
    work_dir.mkdir(parents=True, exist_ok=True)

    _log(f"Keywords: {len(keywords)} | Method: {args.method} | Output: {work_dir}")

    # Step 1 — cluster
    if args.demo:
        clusters_meta = cluster_demo(keywords)
    elif args.method == "semantic":
        clusters_meta = cluster_semantic(keywords, args, work_dir)
    else:
        clusters_meta = cluster_serp(keywords, args)
    clusters = clusters_meta["clusters"]
    if not clusters:
        _log("Error: clustering produced no clusters.")
        sys.exit(1)

    # Step 2 — map
    volumes = {}  # volume column not guaranteed in plain keyword lists
    mapping = build_mapping(clusters, volumes)
    mapping_out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "method": clusters_meta["method"],
        "input_keyword_count": len(keywords),
        "clustering_tokens": clusters_meta["tokens_used"],
        **mapping,
    }
    (work_dir / "mapping.json").write_text(
        json.dumps(mapping_out, indent=2, ensure_ascii=False), encoding="utf-8")
    _log(f"Saved mapping: {work_dir / 'mapping.json'}")

    # Step 3 — briefs
    briefs_written = []
    if not args.dry_run:
        pages = mapping["pages"]
        if args.max_briefs and args.max_briefs > 0:
            pages = pages[:args.max_briefs]
        for page in pages:
            primary = page["primary_keyword"]
            _log(f"[brief] {page['cluster_name']} (primary: {primary})")
            if args.demo:
                research = research_mock(primary)
            else:
                research = research_real(primary, args)
            md = render_brief_md(page, research)
            brief_path = work_dir / f"brief-{page['page_slug']}.md"
            brief_path.write_text(md, encoding="utf-8")
            briefs_written.append(str(brief_path))

    print_summary(mapping, clusters_meta, briefs_written, args)


if __name__ == "__main__":
    main()
