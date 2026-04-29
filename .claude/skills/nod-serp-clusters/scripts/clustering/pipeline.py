"""Run the full SERP clustering pipeline (fetch → weights → similarity → Louvain).

Pure-Python orchestration with no argparse, no print-to-stderr formatting
beyond progress logging. Callers (cluster.py CLI, agent pipelines) pass
configured clients and a config dict; receive a structured result dict.
"""

import json
import math
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

from .serp_parse import extract_organic, extract_snippets
from .similarity import (compute_domain_coverage, compute_domain_weights,
                         weighted_jaccard)
from .louvain import louvain_communities
from .naming import name_clusters


# Multi-level threshold/resolution presets for the `levels` shortcut.
LEVEL_PRESETS = {
    1: [("cluster", 1.0, 1.0)],
    2: [("L1_broad", 0.5, 0.5), ("L2_specific", 1.0, 1.0)],
    3: [("L1_broad", 0.4, 0.3), ("L2_medium", 0.7, 0.8), ("L3_specific", 1.0, 1.0)],
}


def _build_levels(levels_arg, threshold, resolution_override):
    """Resolve the levels argument into a [(name, threshold, resolution)] list.

    Accepts an int (1-3) for a preset or a pre-built list of tuples.
    Threshold multipliers from the preset are applied to the base threshold.
    """
    if isinstance(levels_arg, int):
        preset = LEVEL_PRESETS[levels_arg]
        levels = [(name, threshold * tm, resolution_override or rm)
                  for name, tm, rm in preset]
    else:
        levels = list(levels_arg)
        if resolution_override is not None:
            levels = [(name, thresh, resolution_override) for name, thresh, _ in levels]
    return levels


def fetch_serps(serp_client, keywords, *, gl, hl, workers, cache_path=None,
                no_cache=False, log=None):
    """Phase 1: fetch SERPs for keywords (with optional disk cache).

    Returns (all_serps, all_snippets, tokens_used, errors).
    """
    log = log or (lambda msg: print(msg, file=sys.stderr))
    all_serps = {}
    all_snippets = {}
    tokens_used = 0
    errors = 0

    if cache_path and not no_cache and Path(cache_path).exists():
        log(f"\n[Phase 1] Loading SERPs from cache: {cache_path}")
        with open(cache_path, "r", encoding="utf-8") as f:
            cached = json.load(f)
        all_serps = cached.get("serps", {})
        all_snippets = cached.get("snippets", {})
        tokens_used = len(all_serps)
        log(f"  Loaded {len(all_serps)} keywords from cache")
        return all_serps, all_snippets, tokens_used, errors

    log(f"\n[Phase 1] Fetching SERPs ({workers} concurrent, {len(keywords)} keywords)...")
    phase1_start = time.time()
    count = [0]

    def on_result(kw, serp):
        nonlocal tokens_used
        tokens_used += 1
        count[0] += 1
        organic = extract_organic(serp)
        if organic:
            all_serps[kw] = organic
        all_snippets[kw] = extract_snippets(serp)
        if count[0] % 50 == 0:
            elapsed = time.time() - phase1_start
            speed = count[0] / (elapsed / 60) if elapsed > 0 else 0
            remaining = len(keywords) - count[0]
            eta_min = remaining / speed if speed > 0 else 0
            log(f"  {count[0]}/{len(keywords)} fetched ({speed:.1f} kw/min, ETA: {eta_min:.1f} min)")

    def on_error(kw, e):
        nonlocal errors
        errors += 1

    serp_client.search_batch(keywords, gl=gl, hl=hl,
                              max_workers=workers,
                              on_result=on_result, on_error=on_error)
    log(f"  Done: {len(all_serps)} with data ({errors} errors, {tokens_used} tokens)")

    if cache_path:
        os.makedirs(str(Path(cache_path).parent), exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump({"serps": all_serps, "snippets": all_snippets}, f, ensure_ascii=False)
        log(f"  Cache saved: {cache_path}")

    return all_serps, all_snippets, tokens_used, errors


def compute_pairwise_similarities(all_serps, domain_weights, *,
                                  domain_bonus, min_shared_urls, log=None):
    """Phase 3a: compute weighted Jaccard for all keyword pairs.

    Returns dict of {(i, j): sim} for non-trivial pairs (sim > 0.01) and
    the keyword list (preserving iteration order).
    """
    log = log or (lambda msg: print(msg, file=sys.stderr))
    kw_list = list(all_serps.keys())
    n = len(kw_list)
    log(f"\n[Phase 3] Computing {n*(n-1)//2} pairwise similarities...")

    pair_sims = {}
    t0 = time.time()
    for i in range(n):
        for j in range(i + 1, n):
            sim = weighted_jaccard(all_serps[kw_list[i]], all_serps[kw_list[j]],
                                    domain_weights, domain_bonus=domain_bonus,
                                    min_shared_urls=min_shared_urls)
            if sim > 0.01:
                pair_sims[(i, j)] = sim
    elapsed = time.time() - t0
    log(f"  {len(pair_sims)} non-trivial pairs ({elapsed:.1f}s)")
    return pair_sims, kw_list


def cluster_at_levels(pair_sims, kw_list, levels, llm_client, model, *,
                      hl="en", log=None):
    """Phase 3b: run Louvain at each level threshold; name clusters via LLM.

    Returns dict of {level_name: {clusters, names, threshold, resolution}}.
    """
    log = log or (lambda msg: print(msg, file=sys.stderr))
    lang = "Polish" if hl == "pl" else "English"

    all_level_results = {}
    for level_name, level_threshold, resolution in levels:
        log(f"\n[Phase 3] Louvain '{level_name}' (threshold={level_threshold:.2f}, resolution={resolution})...")

        edges = [(kw_list[i], kw_list[j], sim)
                 for (i, j), sim in pair_sims.items() if sim >= level_threshold]
        log(f"  Edges above threshold: {len(edges)}")

        communities = louvain_communities(kw_list, edges, resolution=resolution)

        clusters = defaultdict(list)
        for kw, cid in communities.items():
            clusters[cid].append(kw)

        sorted_clusters = sorted(clusters.items(), key=lambda x: -len(x[1]))
        multi = sum(1 for _, kws in sorted_clusters if len(kws) >= 2)
        singles = sum(1 for _, kws in sorted_clusters if len(kws) == 1)
        sizes = [len(kws) for _, kws in sorted_clusters]
        log(f"  Clusters: {len(sorted_clusters)} (multi: {multi}, singletons: {singles})")
        if sizes:
            log(f"  Sizes: max={max(sizes)}, avg={sum(sizes)/len(sizes):.1f}")

        log(f"  Naming via LLM...")
        to_name = [(cid, kws) for cid, kws in sorted_clusters if len(kws) >= 2]
        cluster_names = name_clusters(to_name, llm_client, model, language=lang)
        for cid, kws in sorted_clusters:
            if cid not in cluster_names:
                cluster_names[cid] = kws[0][:50]

        all_level_results[level_name] = {
            "clusters": dict(sorted_clusters),
            "names": cluster_names,
            "threshold": level_threshold,
            "resolution": resolution,
        }

    return all_level_results


def run_clustering(keywords, serp_client, llm_client, *,
                   gl="us", hl="en",
                   threshold=0.55, levels=1,
                   domain_bonus=0.3, min_shared_urls=2,
                   high_coverage=0.10, very_high_coverage=0.30,
                   max_pairs_per_domain=20000,
                   workers=3, resolution=None,
                   cache_path=None, no_cache=False,
                   model="google/gemini-2.5-flash-lite",
                   log=None):
    """Run the full clustering pipeline. See module docstring."""
    log = log or (lambda msg: print(msg, file=sys.stderr))

    # Phase 1 — fetch
    all_serps, all_snippets, tokens_used, errors = fetch_serps(
        serp_client, keywords, gl=gl, hl=hl, workers=workers,
        cache_path=cache_path, no_cache=no_cache, log=log,
    )

    # Phase 2 — domain weights
    log(f"\n[Phase 2] Computing domain weights...")
    coverage = compute_domain_coverage(all_serps)
    domain_weights = compute_domain_weights(coverage,
                                             high_thresh=high_coverage,
                                             very_high_thresh=very_high_coverage)
    high_cov = [(d, c) for d, c in sorted(coverage.items(), key=lambda x: -x[1])[:5]]
    for d, c in high_cov:
        log(f"  {d}: coverage={c:.1%}, weight={domain_weights[d]:.2f}")

    # Phase 3 — similarity + Louvain per level
    levels_resolved = _build_levels(levels, threshold, resolution)
    pair_sims, kw_list = compute_pairwise_similarities(
        all_serps, domain_weights,
        domain_bonus=domain_bonus, min_shared_urls=min_shared_urls, log=log,
    )
    all_level_results = cluster_at_levels(
        pair_sims, kw_list, levels_resolved, llm_client, model, hl=hl, log=log,
    )

    return {
        "all_serps": all_serps,
        "all_snippets": all_snippets,
        "all_level_results": all_level_results,
        "tokens_used": tokens_used,
        "errors": errors,
        "levels": levels_resolved,
    }
