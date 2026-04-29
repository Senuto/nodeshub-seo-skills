#!/usr/bin/env python3
"""
Semantic Keyword Clustering — OpenRouter Embeddings + Cosine Similarity + Louvain.

Algorithm:
  1. Embeddings — fetch vector embeddings for all keywords via OpenRouter API
  2. Cosine similarity — compute pairwise cosine similarity between all embeddings
  3. Louvain community detection — same as SERP-based cluster.py
  4. Multi-level via Louvain resolution parameter
  5. LLM naming — OpenRouter generates cluster names

Compared to cluster.py (SERP-based):
  - No NodesHub tokens needed — pure OpenRouter API cost
  - Clusters by meaning similarity, not shared Google results
  - Works even for brand-new keywords with no SERP history
  - Much faster (no live SERP fetching)
  - Embedding model: google/gemini-embedding-001 (cheapest, ~$0.02/1M tokens)

Usage:
  python3 cluster_semantic.py keywords.csv
  python3 cluster_semantic.py keywords.csv --threshold 0.30 --levels 2
  python3 cluster_semantic.py keywords.csv --threshold 0.20 --model google/gemini-2.5-flash-lite --output out.csv --json
"""

import argparse
import csv
import json
import math
import os
import random
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'nod-nodeshub-api' / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from openrouter_client import OpenRouterClient, OpenRouterError
from clustering.louvain import louvain_communities
from clustering.naming import name_clusters


# ── Embeddings ────────────────────────────────────────────────────

EMBEDDING_MODEL = "google/gemini-embedding-001"
EMBEDDING_BATCH_SIZE = 100  # OpenRouter supports up to ~2048 but 100 is safe


def get_embeddings_batch(texts, api_key, model=EMBEDDING_MODEL):
    """Fetch embeddings for a batch of texts via OpenRouter /api/v1/embeddings.

    Returns list of embedding vectors (list of floats), same order as input.
    Raises urllib.error.HTTPError or ValueError on failure.
    """
    url = "https://openrouter.ai/api/v1/embeddings"
    payload = json.dumps({"model": model, "input": texts}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = json.loads(resp.read().decode("utf-8"))

    if "data" not in body:
        raise ValueError(f"Unexpected response: {body}")

    # Sort by index to guarantee order
    items = sorted(body["data"], key=lambda x: x["index"])
    return [item["embedding"] for item in items]


def get_all_embeddings(keywords, api_key, model=EMBEDDING_MODEL, batch_size=EMBEDDING_BATCH_SIZE):
    """Fetch embeddings for all keywords in batches.

    Returns dict: {keyword: embedding_vector}
    """
    embeddings = {}
    total = len(keywords)
    for batch_start in range(0, total, batch_size):
        batch = keywords[batch_start:batch_start + batch_size]
        end = min(batch_start + batch_size, total)
        print(f"  Embeddings {batch_start + 1}-{end}/{total}...", file=sys.stderr)
        retries = 3
        for attempt in range(retries):
            try:
                vectors = get_embeddings_batch(batch, api_key, model=model)
                for kw, vec in zip(batch, vectors):
                    embeddings[kw] = vec
                break
            except urllib.error.HTTPError as e:
                body_text = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else ""
                if e.code == 429 and attempt < retries - 1:
                    wait = 2 ** attempt
                    print(f"  Rate limited, retrying in {wait}s...", file=sys.stderr)
                    time.sleep(wait)
                else:
                    print(f"  HTTP {e.code} on batch {batch_start}: {body_text[:200]}", file=sys.stderr)
                    break
            except Exception as e:
                print(f"  Error on batch {batch_start}: {e}", file=sys.stderr)
                break
    return embeddings


# ── Cosine Similarity ─────────────────────────────────────────────

def cosine_similarity(a, b):
    """Compute cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# Louvain community detection and LLM naming live in clustering/ — imported above.


# ── Main ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Semantic keyword clustering via OpenRouter embeddings + cosine similarity + Louvain",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 cluster_semantic.py keywords.csv
  python3 cluster_semantic.py keywords.csv --threshold 0.30 --levels 2
  python3 cluster_semantic.py keywords.csv --threshold 0.20 --output clusters.csv --json
  python3 cluster_semantic.py keywords.csv --levels 3 --model google/gemini-2.5-flash-lite

Note:
  Requires OPENROUTER_API_KEY environment variable.
  Embedding model: google/gemini-embedding-001 (~$0.02/1M tokens).
  No NodesHub tokens used — purely semantic, no live SERP data.
        """,
    )
    parser.add_argument("input", help="Input CSV (must have 'keyword' column)")
    parser.add_argument(
        "--threshold", type=float, default=0.25,
        help="Min cosine similarity to create graph edge (default: 0.25)",
    )
    parser.add_argument(
        "--levels", type=int, default=1, choices=[1, 2, 3],
        help="Clustering depth via Louvain resolution (1-3, default: 1)",
    )
    parser.add_argument(
        "--resolution", type=float, default=None,
        help="Override Louvain resolution for all levels (higher = more clusters)",
    )
    parser.add_argument(
        "--embedding-model", default=EMBEDDING_MODEL,
        help=f"OpenRouter embedding model (default: {EMBEDDING_MODEL})",
    )
    parser.add_argument(
        "--model", default="google/gemini-2.5-flash-lite",
        help="LLM model for cluster naming (default: google/gemini-2.5-flash-lite)",
    )
    parser.add_argument(
        "--language", default=None,
        help="Language for cluster names (default: auto-detect Polish/English from --hl)",
    )
    parser.add_argument(
        "--hl", default="pl",
        help="Language hint for cluster naming: pl=Polish, en=English (default: pl)",
    )
    parser.add_argument(
        "--top-n", type=int, default=0,
        help="Only cluster top N keywords (0=all)",
    )
    parser.add_argument(
        "--output", "-o",
        help="Output CSV path (default: <input>_semantic_clustered.csv)",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Also output JSON summary",
    )
    args = parser.parse_args()

    # ── Read CSV ──
    keywords_data = []
    with open(args.input, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            keywords_data.append(row)

    if not keywords_data:
        print("Error: empty CSV", file=sys.stderr)
        sys.exit(1)

    if "keyword" not in keywords_data[0]:
        print("Error: CSV must have 'keyword' column", file=sys.stderr)
        sys.exit(1)

    if args.top_n > 0:
        keywords_data = keywords_data[:args.top_n]

    keywords = [row["keyword"] for row in keywords_data]
    lang = args.language or ("Polish" if args.hl == "pl" else "English")

    print(f"=== Semantic Keyword Clustering (Embeddings + Cosine + Louvain) ===", file=sys.stderr)
    print(f"Keywords: {len(keywords)} | Threshold: {args.threshold} | Levels: {args.levels}", file=sys.stderr)
    print(f"Embedding model: {args.embedding_model} | Naming model: {args.model}", file=sys.stderr)

    # ── Init clients ──
    llm_client = OpenRouterClient()
    api_key = llm_client.api_key  # reuse key from OpenRouterClient

    # ── Phase 1: Fetch embeddings ──
    print(f"\n[Phase 1] Fetching embeddings for {len(keywords)} keywords...", file=sys.stderr)
    t0 = time.time()
    embeddings = get_all_embeddings(keywords, api_key, model=args.embedding_model)
    elapsed = time.time() - t0
    print(f"  Done: {len(embeddings)}/{len(keywords)} embeddings ({elapsed:.1f}s)", file=sys.stderr)

    if len(embeddings) < 2:
        print("Error: not enough embeddings to cluster", file=sys.stderr)
        sys.exit(1)

    # Filter to keywords with embeddings
    kw_list = [kw for kw in keywords if kw in embeddings]

    # ── Phase 2: Compute pairwise cosine similarity ──
    n = len(kw_list)
    print(f"\n[Phase 2] Computing {n*(n-1)//2} cosine similarity pairs...", file=sys.stderr)
    t0 = time.time()

    pair_sims = {}
    for i in range(n):
        for j in range(i + 1, n):
            sim = cosine_similarity(embeddings[kw_list[i]], embeddings[kw_list[j]])
            if sim > 0.01:
                pair_sims[(i, j)] = sim

    elapsed = time.time() - t0
    print(f"  {len(pair_sims)} non-trivial pairs ({elapsed:.1f}s)", file=sys.stderr)

    # ── Phase 3: Louvain per level ──
    level_config = {
        1: [("cluster", args.threshold, 1.0)],
        2: [("L1_broad", args.threshold * 0.6, 0.5), ("L2_specific", args.threshold, 1.0)],
        3: [
            ("L1_broad", args.threshold * 0.5, 0.3),
            ("L2_medium", args.threshold * 0.75, 0.8),
            ("L3_specific", args.threshold, 1.0),
        ],
    }
    levels = level_config[args.levels]
    if args.resolution is not None:
        levels = [(name, thresh, args.resolution) for name, thresh, _ in levels]

    all_level_results = {}

    for level_name, level_threshold, resolution in levels:
        print(
            f"\n[Phase 3] Louvain '{level_name}' "
            f"(threshold={level_threshold:.3f}, resolution={resolution})...",
            file=sys.stderr,
        )

        edges = [
            (kw_list[i], kw_list[j], sim)
            for (i, j), sim in pair_sims.items()
            if sim >= level_threshold
        ]
        print(f"  Edges above threshold: {len(edges)}", file=sys.stderr)

        communities = louvain_communities(kw_list, edges, resolution=resolution)

        # Group into clusters
        clusters = defaultdict(list)
        for kw, cid in communities.items():
            clusters[cid].append(kw)

        sorted_clusters = sorted(clusters.items(), key=lambda x: -len(x[1]))
        multi = sum(1 for _, kws in sorted_clusters if len(kws) >= 2)
        singles = sum(1 for _, kws in sorted_clusters if len(kws) == 1)
        sizes = [len(kws) for _, kws in sorted_clusters]
        print(f"  Clusters: {len(sorted_clusters)} (multi: {multi}, singletons: {singles})", file=sys.stderr)
        if sizes:
            print(f"  Sizes: max={max(sizes)}, avg={sum(sizes)/len(sizes):.1f}", file=sys.stderr)

        # Name clusters via LLM
        print(f"  Naming via LLM...", file=sys.stderr)
        to_name = [(cid, kws) for cid, kws in sorted_clusters if len(kws) >= 2]
        cluster_names = name_clusters(to_name, llm_client, args.model, language=lang)
        # Singletons get keyword as name
        for cid, kws in sorted_clusters:
            if cid not in cluster_names:
                cluster_names[cid] = kws[0][:50]

        all_level_results[level_name] = {
            "clusters": dict(sorted_clusters),
            "names": cluster_names,
            "threshold": level_threshold,
            "resolution": resolution,
        }

    # ── Output CSV ──
    input_stem = Path(args.input).stem
    output_path = args.output or str(
        Path(args.input).parent / f"{input_stem}_semantic_clustered.csv"
    )
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    # Build keyword -> cluster mapping
    kw_to_cluster = {kw: {} for kw in keywords}
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
        fieldnames = list(keywords_data[0].keys()) + cluster_fields
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in keywords_data:
            kw = row["keyword"]
            info = kw_to_cluster.get(kw, {})
            for level_name, _, _ in levels:
                info.setdefault(f"{level_name}_id", -1)
                info.setdefault(f"{level_name}_name", "unclustered")
                info.setdefault(f"{level_name}_size", 0)
            row.update(info)
            writer.writerow(row)

    print(f"\nSaved: {output_path}", file=sys.stderr)

    # ── JSON output ──
    if args.json:
        json_path = output_path.rsplit(".", 1)[0] + ".json"
        json_output = {
            "input": args.input,
            "embedding_model": args.embedding_model,
            "keywords_total": len(keywords),
            "keywords_embedded": len(embeddings),
            "levels": {},
        }
        for level_name, ld in all_level_results.items():
            json_output["levels"][level_name] = {
                "threshold": ld["threshold"],
                "resolution": ld["resolution"],
                "clusters": [
                    {"id": cid, "name": ld["names"].get(cid, ""), "keywords": kws}
                    for cid, kws in sorted(ld["clusters"].items(), key=lambda x: -len(x[1]))
                ],
            }
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(json_output, f, indent=2, ensure_ascii=False)
        print(f"Saved: {json_path}", file=sys.stderr)

    # ── Final summary ──
    print(f"\n{'='*70}", file=sys.stderr)
    print(f"  SEMANTIC CLUSTERING REPORT (Embeddings + Cosine + Louvain)", file=sys.stderr)
    print(f"{'='*70}", file=sys.stderr)
    print(f"  Keywords: {len(keywords)} -> {len(embeddings)} embedded", file=sys.stderr)

    for level_name, ld in all_level_results.items():
        clusters = ld["clusters"]
        names = ld["names"]
        sorted_c = sorted(clusters.items(), key=lambda x: -len(x[1]))
        multi = sum(1 for _, kws in sorted_c if len(kws) >= 2)
        print(
            f"\n  --- {level_name} (threshold: {ld['threshold']:.3f}, resolution: {ld['resolution']}) ---",
            file=sys.stderr,
        )
        print(f"  Clusters: {len(clusters)} | Multi-keyword: {multi}", file=sys.stderr)
        for cid, kws in sorted_c[:10]:
            if len(kws) < 2:
                break
            name = names.get(cid, "?")
            sample = ", ".join(kws[:4])
            more = f" +{len(kws)-4}" if len(kws) > 4 else ""
            print(f"    [{len(kws):>3}] {name}: {sample}{more}", file=sys.stderr)

    print(f"{'='*70}", file=sys.stderr)


if __name__ == "__main__":
    main()
