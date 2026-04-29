"""Standalone Markdown clustering report (no dendrogram, text tree instead)."""

from collections import defaultdict


def generate_md_report(all_level_results, all_serps, all_snippets):
    """Generate a Markdown clustering report."""
    domain_urls = defaultdict(set)
    domain_positions = defaultdict(list)
    for kw, results in all_serps.items():
        for r in results:
            domain_urls[r["domain"]].add(r["url"])
            domain_positions[r["domain"]].append(r["pos"])

    top_domains = sorted(domain_positions.items(), key=lambda x: -len(x[1]))[:20]

    snippet_counts = defaultdict(int)
    for kw, snippets in all_snippets.items():
        for s in snippets:
            snippet_counts[s] += 1

    last_level = list(all_level_results.keys())[-1]
    clusters = all_level_results[last_level]["clusters"]
    cluster_names = all_level_results[last_level]["names"]

    lines = []
    lines.append("# SERP Cluster Report\n")

    # Text hierarchy
    if len(all_level_results) > 1:
        lines.append("## Cluster Hierarchy\n")
        lines.append("```")
        broadest = list(all_level_results.keys())[0]
        bd = all_level_results[broadest]
        for cid, kws in sorted(bd["clusters"].items(), key=lambda x: -len(x[1]))[:15]:
            if len(kws) < 2:
                continue
            name = bd["names"].get(cid, f"Cluster {cid}")
            lines.append(f"{name} ({len(kws)} kws)")
            # Show sub-clusters from next level
            if len(all_level_results) >= 2:
                l2_name = list(all_level_results.keys())[1]
                l2 = all_level_results[l2_name]
                l2_map = {}
                for l2_cid, l2_kws in l2["clusters"].items():
                    for kw in l2_kws:
                        l2_map[kw] = l2_cid
                l2_subs = defaultdict(list)
                for kw in kws:
                    if kw in l2_map:
                        l2_subs[l2_map[kw]].append(kw)
                for l2_cid, l2_kws in sorted(l2_subs.items(), key=lambda x: -len(x[1]))[:5]:
                    l2_n = l2["names"].get(l2_cid, f"Sub {l2_cid}")
                    lines.append(f"  +-- {l2_n} ({len(l2_kws)} kws)")
        lines.append("```\n")

    lines.append("## Top Domains by Visibility\n")
    lines.append("| # | Domain | Appearances | Unique URLs | Avg Position |")
    lines.append("|---|--------|------------|-------------|-------------|")
    for i, (domain, positions) in enumerate(top_domains):
        avg_pos = sum(positions) / len(positions)
        urls = len(domain_urls[domain])
        lines.append(f"| {i+1} | {domain} | {len(positions)} | {urls} | {avg_pos:.1f} |")

    lines.append("\n## SERP Features Distribution\n")
    lines.append("| Feature | Keywords | % |")
    lines.append("|---------|----------|---|")
    total_kws = len(all_serps)
    for snippet, count in sorted(snippet_counts.items(), key=lambda x: -x[1]):
        pct = count / total_kws * 100 if total_kws else 0
        lines.append(f"| {snippet} | {count} | {pct:.0f}% |")

    lines.append("\n## Clusters\n")
    sorted_clusters = sorted(clusters.items(), key=lambda x: -len(x[1]))
    for cid, kws in sorted_clusters:
        if len(kws) < 2:
            continue
        name = cluster_names.get(cid, f"Cluster {cid}")
        lines.append(f"### {name} ({len(kws)} keywords)\n")
        lines.append("Keywords: " + ", ".join(kws[:30]))
        cluster_domains = defaultdict(int)
        for kw in kws:
            for r in all_serps.get(kw, []):
                cluster_domains[r["domain"]] += 1
        top_cd = sorted(cluster_domains.items(), key=lambda x: -x[1])[:5]
        if top_cd:
            lines.append("\nTop domains: " + ", ".join(f"{d} ({c})" for d, c in top_cd))
        lines.append("")

    return "\n".join(lines)
