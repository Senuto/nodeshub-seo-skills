"""Weighted Jaccard similarity with dynamic domain weighting.

Position weight: 1/log2(pos+2). Pos 1 → 1.44, pos 10 → 0.43.
Mega-domains (Wikipedia etc.) get reduced weight via coverage thresholds.
"""

import math
from collections import defaultdict


def position_weight(pos):
    """Weight by position: 1/log2(pos+2). Pos 1→1.44, pos 10→0.43."""
    return 1.0 / math.log2(pos + 2)


def compute_domain_coverage(all_serps):
    """Compute what fraction of keywords each domain appears in."""
    domain_count = defaultdict(int)
    total = len(all_serps)
    for kw, results in all_serps.items():
        seen = set()
        for r in results:
            d = r["domain"]
            if d and d not in seen:
                domain_count[d] += 1
                seen.add(d)
    return {d: count / total for d, count in domain_count.items()} if total > 0 else {}


def compute_domain_weights(coverage, high_thresh=0.10, very_high_thresh=0.30, min_weight=0.2):
    """Dynamic domain weighting with two thresholds.

    < high_thresh: weight = 1.0 (full impact)
    high_thresh..very_high_thresh: weight = 1/sqrt(coverage)
    > very_high_thresh: weight = 1/sqrt(coverage), more aggressive reduction
    All capped at min_weight floor.
    """
    weights = {}
    for domain, cov in coverage.items():
        if cov < high_thresh:
            weights[domain] = 1.0
        elif cov < very_high_thresh:
            w = 1.0 / math.sqrt(cov)
            weights[domain] = max(w, min_weight)
        else:
            # Mega-domain: extra penalty
            w = 1.0 / (math.sqrt(cov) * 1.5)
            weights[domain] = max(w, min_weight)
    return weights


def weighted_jaccard(results_a, results_b, domain_weights, domain_bonus=0.3, min_shared_urls=2):
    """Weighted Jaccard between two SERP result lists."""
    if not results_a or not results_b:
        return 0.0

    # Quick check: count raw URL overlap first
    urls_set_a = {r["url"] for r in results_a}
    urls_set_b = {r["url"] for r in results_b}
    raw_overlap = len(urls_set_a & urls_set_b)
    if raw_overlap < min_shared_urls:
        return 0.0

    # Build lookup: url -> (pos, domain), domain -> [(url, pos)]
    urls_a = {r["url"]: r for r in results_a}
    urls_b = {r["url"]: r for r in results_b}
    domains_a = defaultdict(list)
    domains_b = defaultdict(list)
    for r in results_a:
        domains_a[r["domain"]].append(r)
    for r in results_b:
        domains_b[r["domain"]].append(r)

    intersection_score = 0.0
    matched_a = set()
    matched_b = set()

    # Exact URL matches
    for url in urls_a:
        if url in urls_b:
            ra, rb = urls_a[url], urls_b[url]
            w = (position_weight(ra["pos"]) + position_weight(rb["pos"])) / 2
            dw = domain_weights.get(ra["domain"], 1.0)
            intersection_score += w * dw
            matched_a.add(url)
            matched_b.add(url)

    # Domain soft matches (same domain, different URL)
    for domain in domains_a:
        if domain in domains_b:
            for ra in domains_a[domain]:
                if ra["url"] in matched_a:
                    continue
                for rb in domains_b[domain]:
                    if rb["url"] in matched_b:
                        continue
                    w = (position_weight(ra["pos"]) + position_weight(rb["pos"])) / 2
                    dw = domain_weights.get(domain, 1.0)
                    intersection_score += w * dw * domain_bonus
                    matched_a.add(ra["url"])
                    matched_b.add(rb["url"])
                    break  # one soft match per URL

    # Union score
    union_score = 0.0
    for r in results_a:
        dw = domain_weights.get(r["domain"], 1.0)
        union_score += position_weight(r["pos"]) * dw
    for r in results_b:
        dw = domain_weights.get(r["domain"], 1.0)
        union_score += position_weight(r["pos"]) * dw
    union_score -= intersection_score  # subtract double-counted intersection

    if union_score <= 0:
        return 0.0
    return intersection_score / union_score
