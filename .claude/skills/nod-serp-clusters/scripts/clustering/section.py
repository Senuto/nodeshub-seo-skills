"""Render clustering data as a branded report section.

Plugs into the shared report system (report.py from nod-nodeshub-api).
"""

from collections import defaultdict
from html import escape

from report import (render_section_wrapper, make_section_id, html_table,
                    summary_card, bar_chart, badge)

from .hierarchy import build_hierarchy_tree
from .dendrogram import dendrogram_js


def render_report_section(all_level_results, all_serps, all_snippets):
    """Render SERP clusters data as a branded HTML report section.

    Args:
        all_level_results: Dict of level_name -> {clusters, names, threshold, resolution}
        all_serps: Dict of keyword -> [organic results]
        all_snippets: Dict of keyword -> [snippet types]

    Returns:
        Tuple of (section_html, extra_head) where extra_head contains the D3.js script tag.
    """
    sid = make_section_id("serp-clusters")

    total_kws = len(all_serps)
    last_level = list(all_level_results.keys())[-1]
    clusters = all_level_results[last_level]["clusters"]
    cluster_names = all_level_results[last_level]["names"]
    multi_clusters = sum(1 for kws in clusters.values() if len(kws) >= 2)

    # Summary
    content = summary_card([
        (str(total_kws), "Keywords"),
        (str(multi_clusters), "Clusters"),
        (str(len(all_level_results)), "Levels"),
    ])

    # D3 Dendrogram
    tree_data = build_hierarchy_tree(all_level_results)
    container_id = f"dendro-{sid}"
    content += f"\n<h3>Cluster Hierarchy</h3>\n"
    content += dendrogram_js(tree_data, container_id)

    # Domain visibility table
    domain_urls = defaultdict(set)
    domain_positions = defaultdict(list)
    for kw, results in all_serps.items():
        for r in results:
            domain_urls[r["domain"]].add(r["url"])
            domain_positions[r["domain"]].append(r["pos"])
    top_domains = sorted(domain_positions.items(), key=lambda x: -len(x[1]))[:15]

    if top_domains:
        rows = []
        for i, (domain, positions) in enumerate(top_domains):
            avg_pos = sum(positions) / len(positions)
            rows.append([
                str(i + 1), f"<strong>{escape(domain)}</strong>",
                str(len(positions)), str(len(domain_urls[domain])),
                f"{avg_pos:.1f}"
            ])
        content += "\n<h3>Top Domains by Visibility</h3>\n"
        content += html_table(["#", "Domain", "Appearances", "Unique URLs", "Avg Pos"], rows)

    # SERP features distribution
    snippet_counts = defaultdict(int)
    for kw, snippets in all_snippets.items():
        for s in snippets:
            snippet_counts[s] += 1
    if snippet_counts:
        feat_items = [(name, count, f"{count} ({count/total_kws*100:.0f}%)")
                      for name, count in sorted(snippet_counts.items(), key=lambda x: -x[1])]
        content += "\n<h3>SERP Features Distribution</h3>\n"
        content += bar_chart(feat_items, max_val=total_kws)

    # Cluster cards
    sorted_clusters = sorted(clusters.items(), key=lambda x: -len(x[1]))
    cluster_cards = []
    for cid, kws in sorted_clusters:
        if len(kws) < 2:
            continue
        name = cluster_names.get(cid, f"Cluster {cid}")
        tags = " ".join(f'{badge(escape(kw), "info")}' for kw in kws[:30])
        # Top domains for this cluster
        cluster_domains = defaultdict(int)
        for kw in kws:
            for r in all_serps.get(kw, []):
                cluster_domains[r["domain"]] += 1
        top_cd = sorted(cluster_domains.items(), key=lambda x: -x[1])[:5]
        domain_tags = " ".join(f'{badge(escape(d) + f" ({c})", "warning")}' for d, c in top_cd) if top_cd else ""
        cluster_cards.append(f"""<div class="brand-card" style="margin:10px 0">
  <h4>{escape(name)} ({len(kws)} keywords)</h4>
  <p style="margin:8px 0">{tags}</p>
  {f'<p><strong>Top domains:</strong> {domain_tags}</p>' if domain_tags else ''}
</div>""")

    if cluster_cards:
        content += "\n<h3>Clusters</h3>\n" + "\n".join(cluster_cards[:20])

    section_html = render_section_wrapper(sid, "SERP Clusters", "SERP Keyword Clusters", content)
    extra_head = "  <script src='https://d3js.org/d3.v7.min.js'></script>"
    return section_html, extra_head
