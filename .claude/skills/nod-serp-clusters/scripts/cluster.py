#!/usr/bin/env python3
"""
SERP-based Keyword Clustering — Weighted Jaccard + Louvain community detection.

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
"""

import argparse
import csv
import json
import math
import os
import random
import socket
import sys
import time
import urllib.error
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'nod-nodeshub-api' / 'scripts'))
from client import NodeshubClient, NodeshubError
from openrouter_client import OpenRouterClient, OpenRouterError
from report import (render_section_wrapper, make_section_id, html_table,
                    summary_card, bar_chart, badge)

# ── SERP extraction ──────────────────────────────────────────────

def extract_organic(serp_data):
    """Extract organic results with url, domain, position."""
    results = []
    try:
        organic = serp_data["data"]["results"].get("organic_results", [])
        for r in organic[:10]:
            url = r.get("url", "").strip().rstrip("/").lower()
            domain = r.get("domain", "").strip().lower()
            pos = r.get("pos", r.get("pos_internal", 0))
            title = r.get("title", "")
            if url:
                results.append({"url": url, "domain": domain, "pos": pos, "title": title})
    except (KeyError, TypeError, AttributeError):
        pass
    return results


def extract_snippets(serp_data):
    """Extract snippet types from SERP."""
    snippet_types = []
    try:
        snippets = serp_data["data"]["results"].get("snippets", {})
        if isinstance(snippets, dict):
            snippet_types = list(snippets.keys())
    except (KeyError, TypeError):
        pass
    return snippet_types


# ── Weighted Jaccard Similarity ──────────────────────────────────

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


# ── Louvain Community Detection ──────────────────────────────────

def louvain_communities(nodes, edges, resolution=1.0):
    """Simplified Louvain modularity optimization.

    Args:
        nodes: list of node IDs
        edges: list of (node_a, node_b, weight)
        resolution: higher = more clusters

    Returns:
        dict of {node: community_id}
    """
    if not nodes:
        return {}

    # Build adjacency
    adj = defaultdict(lambda: defaultdict(float))
    node_strength = defaultdict(float)  # weighted degree
    total_weight = 0.0

    for a, b, w in edges:
        adj[a][b] += w
        adj[b][a] += w
        node_strength[a] += w
        node_strength[b] += w
        total_weight += w

    if total_weight == 0:
        return {n: i for i, n in enumerate(nodes)}

    m2 = 2 * total_weight

    # Initialize: each node in its own community
    community = {n: i for i, n in enumerate(nodes)}
    comm_internal = defaultdict(float)  # sum of internal edge weights
    comm_total = defaultdict(float)  # sum of all edge weights to community

    for n in nodes:
        comm_total[community[n]] = node_strength.get(n, 0.0)

    for a, b, w in edges:
        if community[a] == community[b]:
            comm_internal[community[a]] += w

    # Iterate
    improved = True
    max_iterations = 50
    iteration = 0

    while improved and iteration < max_iterations:
        improved = False
        iteration += 1
        node_order = list(nodes)
        random.shuffle(node_order)

        for node in node_order:
            current_comm = community[node]
            ki = node_strength.get(node, 0.0)

            # Compute weights to neighboring communities
            neighbor_comms = defaultdict(float)
            for neighbor, w in adj[node].items():
                neighbor_comms[community[neighbor]] += w

            # Weight to current community (excluding self-loops)
            ki_in = neighbor_comms.get(current_comm, 0.0)

            # Remove node from current community
            comm_total[current_comm] -= ki
            comm_internal[current_comm] -= ki_in

            # Find best community
            best_comm = current_comm
            best_delta = 0.0

            for comm, ki_comm in neighbor_comms.items():
                sigma_tot = comm_total[comm]
                delta = ki_comm - resolution * sigma_tot * ki / m2
                if delta > best_delta:
                    best_delta = delta
                    best_comm = comm

            # Also check staying in current (now empty of this node)
            sigma_tot_current = comm_total[current_comm]
            delta_current = ki_in - resolution * sigma_tot_current * ki / m2
            if delta_current >= best_delta:
                best_comm = current_comm
                best_delta = delta_current

            # Move node
            community[node] = best_comm
            comm_total[best_comm] += ki
            comm_internal[best_comm] += neighbor_comms.get(best_comm, 0.0)

            if best_comm != current_comm:
                improved = True

    # Renumber communities to 0..N
    unique_comms = sorted(set(community.values()))
    remap = {c: i for i, c in enumerate(unique_comms)}
    return {n: remap[c] for n, c in community.items()}


# ── LLM Cluster Naming ──────────────────────────────────────────

def name_clusters(clusters, llm_client, model, language="Polish"):
    """Use LLM to generate cluster names."""
    names = {}
    batch_size = 10
    for batch_start in range(0, len(clusters), batch_size):
        batch = clusters[batch_start:batch_start + batch_size]
        cluster_descriptions = []
        for idx, (cid, kws) in enumerate(batch):
            sample = kws[:15]
            cluster_descriptions.append(f"Cluster {idx}: {', '.join(sample)}")

        prompt = f"""Name each keyword cluster with a short, descriptive label (2-5 words) in {language}.
The name should capture the main topic/intent of the keywords.

{chr(10).join(cluster_descriptions)}

Respond ONLY with JSON: {{"0": "name", "1": "name"}}"""

        try:
            response = llm_client.chat(prompt, model=model, temperature=0.2, max_tokens=1000)
            response = response.strip()
            if response.startswith("```"):
                response = response.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            parsed = json.loads(response)
            for key, name in parsed.items():
                names[batch[int(key)][0]] = name
        except (json.JSONDecodeError, OpenRouterError, ValueError, IndexError) as e:
            print(f"  LLM naming error: {e}", file=sys.stderr)
            for cid, kws in batch:
                names.setdefault(cid, f"Cluster {cid}")

    return names


# ── Report Generation ────────────────────────────────────────────

def build_hierarchy_tree(all_level_results):
    """Build a hierarchy tree from multi-level clustering results.
    Maps keywords through levels: L1 -> L2 -> L3 -> keywords."""
    level_names = list(all_level_results.keys())
    if len(level_names) < 2:
        # Single level — flat tree
        ld = all_level_results[level_names[0]]
        children = []
        for cid, kws in sorted(ld["clusters"].items(), key=lambda x: -len(x[1])):
            if len(kws) < 2:
                continue
            name = ld["names"].get(cid, f"Cluster {cid}")
            children.append({"name": f"{name} ({len(kws)})", "children": [{"name": k, "size": 1} for k in kws[:20]]})
        return {"name": "All Keywords", "children": children[:30]}

    # Multi-level: build parent-child by keyword overlap
    # For each level pair (L1->L2, L2->L3), find which child cluster
    # belongs to which parent cluster (by majority keyword overlap)
    def get_kw_to_cluster(level_data):
        mapping = {}
        for cid, kws in level_data["clusters"].items():
            for kw in kws:
                mapping[kw] = cid
        return mapping

    # Build tree from broadest to most specific
    broadest = level_names[0]
    bd = all_level_results[broadest]

    root_children = []
    for cid, kws in sorted(bd["clusters"].items(), key=lambda x: -len(x[1])):
        if len(kws) < 2:
            continue
        name = bd["names"].get(cid, f"Cluster {cid}")
        node = {"name": f"{name} ({len(kws)})", "children": []}

        if len(level_names) >= 2:
            # Find L2 clusters that overlap with this L1
            l2 = all_level_results[level_names[1]]
            l2_map = get_kw_to_cluster(l2)
            l2_subclusters = defaultdict(list)
            for kw in kws:
                if kw in l2_map:
                    l2_subclusters[l2_map[kw]].append(kw)

            for l2_cid, l2_kws in sorted(l2_subclusters.items(), key=lambda x: -len(x[1])):
                l2_name = l2["names"].get(l2_cid, f"Sub {l2_cid}")
                l2_node = {"name": f"{l2_name} ({len(l2_kws)})"}

                if len(level_names) >= 3:
                    l3 = all_level_results[level_names[2]]
                    l3_map = get_kw_to_cluster(l3)
                    l3_subclusters = defaultdict(list)
                    for kw in l2_kws:
                        if kw in l3_map:
                            l3_subclusters[l3_map[kw]].append(kw)

                    l2_children = []
                    for l3_cid, l3_kws in sorted(l3_subclusters.items(), key=lambda x: -len(x[1])):
                        l3_name = l3["names"].get(l3_cid, f"Detail {l3_cid}")
                        leaf_kws = [{"name": k, "size": 1} for k in l3_kws[:10]]
                        l2_children.append({"name": f"{l3_name} ({len(l3_kws)})", "children": leaf_kws})
                    l2_node["children"] = l2_children if l2_children else [{"name": k, "size": 1} for k in l2_kws[:10]]
                else:
                    l2_node["children"] = [{"name": k, "size": 1} for k in l2_kws[:10]]

                node["children"].append(l2_node)
        else:
            node["children"] = [{"name": k, "size": 1} for k in kws[:20]]

        root_children.append(node)

    return {"name": "All Keywords", "children": root_children[:30]}


def generate_report(all_level_results, all_serps, all_snippets, fmt="md"):
    """Generate cluster analysis report with dendrogram."""
    # Domain visibility across all SERPs
    domain_urls = defaultdict(set)
    domain_positions = defaultdict(list)
    for kw, results in all_serps.items():
        for r in results:
            domain_urls[r["domain"]].add(r["url"])
            domain_positions[r["domain"]].append(r["pos"])

    top_domains = sorted(domain_positions.items(), key=lambda x: -len(x[1]))[:20]

    # Snippet distribution
    snippet_counts = defaultdict(int)
    for kw, snippets in all_snippets.items():
        for s in snippets:
            snippet_counts[s] += 1

    # Use last (most specific) level for cluster details
    last_level = list(all_level_results.keys())[-1]
    clusters = all_level_results[last_level]["clusters"]
    cluster_names = all_level_results[last_level]["names"]

    # Build hierarchy for dendrogram
    tree_data = build_hierarchy_tree(all_level_results)

    lines = []
    if fmt == "html":
        lines.append("<!DOCTYPE html><html><head><meta charset='utf-8'>")
        lines.append("<title>SERP Cluster Report</title>")
        lines.append("<style>")
        lines.append("body{font-family:sans-serif;max-width:1400px;margin:0 auto;padding:20px;color:#1f2937}")
        lines.append("table{border-collapse:collapse;width:100%}th,td{border:1px solid #e5e7eb;padding:10px;text-align:left}")
        lines.append("th{background:#f3f4f6;font-weight:600}")
        lines.append("h1{color:#111827}h2{color:#3b82f6;border-bottom:2px solid #3b82f6;padding-bottom:8px;margin-top:40px}")
        lines.append(".cluster{background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;padding:15px;margin:10px 0}")
        lines.append(".tag{display:inline-block;background:#e0e7ff;color:#3730a3;padding:3px 10px;border-radius:4px;margin:2px;font-size:0.85em}")
        lines.append(".domain-tag{display:inline-block;background:#fef3c7;color:#92400e;padding:2px 8px;border-radius:4px;margin:2px;font-size:0.85em}")
        lines.append("#dendrogram{width:100%;overflow-x:auto;border:1px solid #e5e7eb;border-radius:8px;background:#fafafa;margin:20px 0}")
        lines.append(".node circle{fill:#3b82f6;stroke:#1d4ed8;stroke-width:1.5px}")
        lines.append(".node text{font:11px sans-serif;fill:#374151}")
        lines.append(".link{fill:none;stroke:#93c5fd;stroke-width:1.5px}")
        lines.append("</style>")
        lines.append("<script src='https://d3js.org/d3.v7.min.js'></script>")
        lines.append("</head><body>")
        lines.append("<h1>SERP Cluster Report</h1>")

        # ── Dendrogram ──
        lines.append("<h2>Cluster Hierarchy (Dendrogram)</h2>")
        lines.append("<div id='dendrogram'></div>")
        lines.append("<script>")
        lines.append(f"const treeData = {json.dumps(tree_data, ensure_ascii=False)};")
        lines.append("""
(function() {
  const container = document.getElementById('dendrogram');
  const baseWidth = 1350;
  const margin = {top: 30, right: 300, bottom: 30, left: 30};
  const width = baseWidth - margin.left - margin.right;

  const svg = d3.select('#dendrogram').append('svg')
    .attr('width', baseWidth)
    .append('g')
    .attr('transform', `translate(${margin.left},${margin.top})`);

  const root = d3.hierarchy(treeData);
  root.x0 = 0;
  root.y0 = 0;

  // Start collapsed: only show first 2 levels
  function collapseAfterDepth(d, maxDepth) {
    if (d.children && d.depth >= maxDepth) {
      d._children = d.children;
      d.children = null;
    }
    if (d.children) d.children.forEach(c => collapseAfterDepth(c, maxDepth));
    if (d._children) d._children.forEach(c => collapseAfterDepth(c, maxDepth));
  }
  collapseAfterDepth(root, 1);

  let i = 0;
  const duration = 400;
  const nodeSize = 24;

  const colors = ['#3b82f6', '#8b5cf6', '#06b6d4', '#10b981'];

  function update(source) {
    // Count visible leaves for height
    function countVisible(node) {
      if (!node.children) return 1;
      return node.children.reduce((s, c) => s + countVisible(c), 0);
    }
    const visibleLeaves = countVisible(root);
    const height = Math.max(400, visibleLeaves * nodeSize);

    svg.transition().duration(duration)
      .select(function() { return this.parentNode; })
      .attr('height', height + margin.top + margin.bottom);

    const treeLayout = d3.tree().size([height, width]);
    treeLayout(root);

    const nodes = root.descendants();
    const links = root.links();

    // ── Links ──
    const link = svg.selectAll('path.link').data(links, d => d.target.id || (d.target.id = ++i));

    const linkEnter = link.enter().insert('path', 'g')
      .attr('class', 'link')
      .attr('d', () => {
        const o = {x: source.x0, y: source.y0};
        return diagonal(o, o);
      });

    const linkUpdate = linkEnter.merge(link);
    linkUpdate.transition().duration(duration).attr('d', d => diagonal(d.source, d.target));

    link.exit().transition().duration(duration)
      .attr('d', () => {
        const o = {x: source.x, y: source.y};
        return diagonal(o, o);
      }).remove();

    // ── Nodes ──
    const node = svg.selectAll('g.node').data(nodes, d => d.id || (d.id = ++i));

    const nodeEnter = node.enter().append('g')
      .attr('class', 'node')
      .attr('transform', `translate(${source.y0},${source.x0})`)
      .style('cursor', d => (d.children || d._children) ? 'pointer' : 'default')
      .on('click', (event, d) => {
        if (d.children) { d._children = d.children; d.children = null; }
        else if (d._children) { d.children = d._children; d._children = null; }
        update(d);
      });

    nodeEnter.append('circle')
      .attr('r', 1e-6)
      .style('stroke-width', '2px');

    nodeEnter.append('text')
      .attr('dy', '0.35em')
      .attr('x', d => (d.children || d._children) ? -12 : 12)
      .attr('text-anchor', d => (d.children || d._children) ? 'end' : 'start')
      .text(d => d.data.name.substring(0, 65));

    const nodeUpdate = nodeEnter.merge(node);
    nodeUpdate.transition().duration(duration)
      .attr('transform', d => `translate(${d.y},${d.x})`);

    nodeUpdate.select('circle')
      .attr('r', d => (d.children || d._children) ? 7 : 4)
      .style('fill', d => d._children ? '#f59e0b' : (d.children ? colors[Math.min(d.depth, 3)] : '#d1d5db'))
      .style('stroke', d => d._children ? '#d97706' : colors[Math.min(d.depth, 3)]);

    nodeUpdate.select('text')
      .style('font-size', d => d.depth === 0 ? '15px' : (d.children || d._children) ? '12px' : '10px')
      .style('font-weight', d => d.depth < 2 ? '700' : (d._children ? '600' : 'normal'))
      .style('fill', d => d._children ? '#d97706' : '#374151');

    const nodeExit = node.exit().transition().duration(duration)
      .attr('transform', `translate(${source.y},${source.x})`).remove();
    nodeExit.select('circle').attr('r', 1e-6);
    nodeExit.select('text').style('fill-opacity', 1e-6);

    nodes.forEach(d => { d.x0 = d.x; d.y0 = d.y; });
  }

  function diagonal(s, d) {
    return `M ${s.y} ${s.x} C ${(s.y + d.y) / 2} ${s.x}, ${(s.y + d.y) / 2} ${d.x}, ${d.y} ${d.x}`;
  }

  update(root);

  // Legend
  const legend = d3.select('#dendrogram').insert('div', 'svg')
    .style('padding', '10px 15px').style('font-size', '13px').style('color', '#6b7280');
  legend.html('Click <span style="color:#f59e0b;font-weight:700">orange</span> nodes to expand. Click <span style="color:#3b82f6;font-weight:700">blue</span> nodes to collapse.');
})();
""")
        lines.append("</script>")

        # ── Domain Visibility ──
        lines.append("<h2>Top Domains by Visibility</h2>")
        lines.append("<table><tr><th>#</th><th>Domain</th><th>Appearances</th><th>Unique URLs</th><th>Avg Position</th></tr>")
        for i, (domain, positions) in enumerate(top_domains):
            avg_pos = sum(positions) / len(positions)
            urls = len(domain_urls[domain])
            lines.append(f"<tr><td>{i+1}</td><td><strong>{domain}</strong></td><td>{len(positions)}</td><td>{urls}</td><td>{avg_pos:.1f}</td></tr>")
        lines.append("</table>")

        # ── SERP Features ──
        lines.append("<h2>SERP Features Distribution</h2>")
        lines.append("<table><tr><th>Feature</th><th>Keywords with feature</th><th>%</th></tr>")
        total_kws = len(all_serps)
        for snippet, count in sorted(snippet_counts.items(), key=lambda x: -x[1]):
            pct = count / total_kws * 100 if total_kws else 0
            lines.append(f"<tr><td>{snippet}</td><td>{count}</td><td>{pct:.0f}%</td></tr>")
        lines.append("</table>")

        # ── Clusters ──
        lines.append("<h2>Clusters (most specific level)</h2>")
        sorted_clusters = sorted(clusters.items(), key=lambda x: -len(x[1]))
        for cid, kws in sorted_clusters:
            if len(kws) < 2:
                continue
            name = cluster_names.get(cid, f"Cluster {cid}")
            lines.append(f"<div class='cluster'><h3>{name} ({len(kws)} keywords)</h3>")
            lines.append("<p>" + " ".join(f"<span class='tag'>{kw}</span>" for kw in kws[:30]) + "</p>")
            cluster_domains = defaultdict(int)
            for kw in kws:
                for r in all_serps.get(kw, []):
                    cluster_domains[r["domain"]] += 1
            top_cd = sorted(cluster_domains.items(), key=lambda x: -x[1])[:5]
            if top_cd:
                lines.append("<p><strong>Top domains:</strong> " +
                           " ".join(f"<span class='domain-tag'>{d} ({c})</span>" for d, c in top_cd) + "</p>")
            lines.append("</div>")

        lines.append("</body></html>")
    else:
        # Markdown (no dendrogram possible, text tree instead)
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


# ── Report section renderer ──────────────────────────────────────

def _d3_dendrogram_js(tree_data, container_id):
    """Return the D3 dendrogram JavaScript for embedding in a report section."""
    return f"""
<div id="{container_id}" style="width:100%;overflow-x:auto;border:1px solid var(--brand-border);border-radius:8px;background:var(--brand-bg-card);margin:20px 0">
</div>
<style>
#{container_id} .node circle{{fill:var(--brand-primary);stroke:#1d4ed8;stroke-width:1.5px}}
#{container_id} .node text{{font:11px var(--brand-font);fill:var(--brand-text)}}
#{container_id} .link{{fill:none;stroke:#93c5fd;stroke-width:1.5px}}
</style>
<script>
(function(){{
  const treeData = {json.dumps(tree_data, ensure_ascii=False)};
  const baseWidth = 1200;
  const margin = {{top:30, right:300, bottom:30, left:30}};
  const width = baseWidth - margin.left - margin.right;
  const svg = d3.select('#{container_id}').append('svg')
    .attr('width', baseWidth).append('g')
    .attr('transform', `translate(${{margin.left}},${{margin.top}})`);
  const root = d3.hierarchy(treeData);
  root.x0 = 0; root.y0 = 0;
  function collapseAfterDepth(d, maxDepth){{
    if(d.children && d.depth >= maxDepth){{ d._children = d.children; d.children = null; }}
    if(d.children) d.children.forEach(c => collapseAfterDepth(c, maxDepth));
    if(d._children) d._children.forEach(c => collapseAfterDepth(c, maxDepth));
  }}
  collapseAfterDepth(root, 1);
  let i = 0; const duration = 400; const nodeSize = 24;
  const colors = ['#3b82f6','#8b5cf6','#06b6d4','#10b981'];
  function update(source){{
    function countVisible(n){{ if(!n.children) return 1; return n.children.reduce((s,c)=>s+countVisible(c),0); }}
    const visibleLeaves = countVisible(root);
    const height = Math.max(400, visibleLeaves * nodeSize);
    svg.transition().duration(duration).select(function(){{ return this.parentNode; }})
      .attr('height', height + margin.top + margin.bottom);
    const treeLayout = d3.tree().size([height, width]);
    treeLayout(root);
    const nodes = root.descendants(); const links = root.links();
    const link = svg.selectAll('path.link').data(links, d => d.target.id || (d.target.id = ++i));
    const linkEnter = link.enter().insert('path','g').attr('class','link')
      .attr('d',()=>{{ const o={{x:source.x0,y:source.y0}}; return diagonal(o,o); }});
    linkEnter.merge(link).transition().duration(duration).attr('d',d=>diagonal(d.source,d.target));
    link.exit().transition().duration(duration)
      .attr('d',()=>{{ const o={{x:source.x,y:source.y}}; return diagonal(o,o); }}).remove();
    const node = svg.selectAll('g.node').data(nodes, d => d.id || (d.id = ++i));
    const nodeEnter = node.enter().append('g').attr('class','node')
      .attr('transform',`translate(${{source.y0}},${{source.x0}})`)
      .style('cursor',d=>(d.children||d._children)?'pointer':'default')
      .on('click',(event,d)=>{{
        if(d.children){{ d._children=d.children; d.children=null; }}
        else if(d._children){{ d.children=d._children; d._children=null; }}
        update(d);
      }});
    nodeEnter.append('circle').attr('r',1e-6).style('stroke-width','2px');
    nodeEnter.append('text').attr('dy','0.35em')
      .attr('x',d=>(d.children||d._children)?-12:12)
      .attr('text-anchor',d=>(d.children||d._children)?'end':'start')
      .text(d=>d.data.name.substring(0,65));
    const nodeUpdate = nodeEnter.merge(node);
    nodeUpdate.transition().duration(duration).attr('transform',d=>`translate(${{d.y}},${{d.x}})`);
    nodeUpdate.select('circle').attr('r',d=>(d.children||d._children)?7:4)
      .style('fill',d=>d._children?'#f59e0b':(d.children?colors[Math.min(d.depth,3)]:'#d1d5db'))
      .style('stroke',d=>d._children?'#d97706':colors[Math.min(d.depth,3)]);
    nodeUpdate.select('text')
      .style('font-size',d=>d.depth===0?'15px':(d.children||d._children)?'12px':'10px')
      .style('font-weight',d=>d.depth<2?'700':(d._children?'600':'normal'))
      .style('fill',d=>d._children?'#d97706':'var(--brand-text)');
    const nodeExit = node.exit().transition().duration(duration)
      .attr('transform',`translate(${{source.y}},${{source.x}})`).remove();
    nodeExit.select('circle').attr('r',1e-6);
    nodeExit.select('text').style('fill-opacity',1e-6);
    nodes.forEach(d=>{{ d.x0=d.x; d.y0=d.y; }});
  }}
  function diagonal(s,d){{
    return `M ${{s.y}} ${{s.x}} C ${{(s.y+d.y)/2}} ${{s.x}}, ${{(s.y+d.y)/2}} ${{d.x}}, ${{d.y}} ${{d.x}}`;
  }}
  update(root);
  d3.select('#{container_id}').insert('div','svg')
    .style('padding','10px 15px').style('font-size','13px').style('color','var(--brand-text-muted)')
    .html('Click <span style="color:#f59e0b;font-weight:700">orange</span> nodes to expand. Click <span style="color:#3b82f6;font-weight:700">blue</span> nodes to collapse.');
}})();
</script>"""


def render_report_section(all_level_results, all_serps, all_snippets):
    """Render SERP clusters data as a branded HTML report section.

    Args:
        all_level_results: Dict of level_name -> {clusters, names, threshold, resolution}
        all_serps: Dict of keyword -> [organic results]
        all_snippets: Dict of keyword -> [snippet types]

    Returns:
        Tuple of (section_html, extra_head) where extra_head contains the D3.js script tag.
    """
    from html import escape
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
    content += _d3_dendrogram_js(tree_data, container_id)

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


# ── Main ─────────────────────────────────────────────────────────

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

    # Read CSV
    keywords_data = []
    with open(args.input, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            keywords_data.append(row)

    if not keywords_data:
        print("Error: empty CSV", file=sys.stderr)
        sys.exit(1)

    if "serp_overlap" in keywords_data[0]:
        keywords_data.sort(key=lambda r: -int(r.get("serp_overlap", 0)))

    if args.top_n > 0:
        keywords_data = keywords_data[:args.top_n]

    keywords = [row["keyword"] for row in keywords_data]

    print(f"=== SERP Clustering (Weighted Jaccard + Louvain) ===", file=sys.stderr)
    print(f"Keywords: {len(keywords)} | Threshold: {args.threshold} | Levels: {args.levels}", file=sys.stderr)
    print(f"Workers: {args.workers} | Domain bonus: {args.domain_bonus}", file=sys.stderr)

    serp_client = NodeshubClient()
    llm_client = OpenRouterClient()

    balance = serp_client.get_balance()
    tokens_left = float(balance.get("left", 0))
    print(f"Balance: {tokens_left} tokens", file=sys.stderr)
    effective_budget = min(args.budget, tokens_left) if args.budget else tokens_left

    # ── Phase 1: Fetch SERPs ──
    output_stem = Path(args.output).stem if args.output else f"{Path(args.input).stem}_clustered"
    output_dir = Path(args.output).parent if args.output else Path(args.input).parent
    cache_path = output_dir / f"{output_stem}_serp_cache.json"

    batch_kws = keywords[:int(effective_budget)]

    all_serps = {}  # keyword -> [organic results]
    all_snippets = {}  # keyword -> [snippet types]
    tokens_used = 0
    errors = 0
    count = [0]

    if not args.no_cache and cache_path.exists():
        print(f"\n[Phase 1] Loading SERPs from cache: {cache_path}", file=sys.stderr)
        with open(cache_path, "r", encoding="utf-8") as _cf:
            _cached = json.load(_cf)
        all_serps = _cached.get("serps", {})
        all_snippets = _cached.get("snippets", {})
        tokens_used = len(all_serps)
        print(f"  Loaded {len(all_serps)} keywords from cache", file=sys.stderr)
    else:
        print(f"\n[Phase 1] Fetching SERPs ({args.workers} concurrent, {len(batch_kws)} keywords)...", file=sys.stderr)

        phase1_start = time.time()

        def on_result(kw, serp):
            nonlocal tokens_used
            tokens_used += 1
            count[0] += 1
            organic = extract_organic(serp)
            if organic:
                all_serps[kw] = organic
            all_snippets[kw] = extract_snippets(serp)
            if count[0] % 50 == 0:
                elapsed_p1 = time.time() - phase1_start
                speed = count[0] / (elapsed_p1 / 60) if elapsed_p1 > 0 else 0
                remaining = len(batch_kws) - count[0]
                eta_min = remaining / speed if speed > 0 else 0
                print(f"  {count[0]}/{len(batch_kws)} fetched ({speed:.1f} kw/min, ETA: {eta_min:.1f} min)", file=sys.stderr)

        def on_error(kw, e):
            nonlocal errors
            errors += 1

        serp_client.search_batch(batch_kws, gl=args.gl, hl=args.hl,
                                  max_workers=args.workers, on_result=on_result, on_error=on_error)
        print(f"  Done: {len(all_serps)} with data ({errors} errors, {tokens_used} tokens)", file=sys.stderr)

        # Save to cache
        os.makedirs(str(output_dir), exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as _cf:
            json.dump({"serps": all_serps, "snippets": all_snippets}, _cf, ensure_ascii=False)
        print(f"  Cache saved: {cache_path}", file=sys.stderr)

    # ── Phase 2: Domain weighting ──
    print(f"\n[Phase 2] Computing domain weights...", file=sys.stderr)
    coverage = compute_domain_coverage(all_serps)
    domain_weights = compute_domain_weights(coverage,
                                             high_thresh=args.high_coverage,
                                             very_high_thresh=args.very_high_coverage)
    high_cov = [(d, c) for d, c in sorted(coverage.items(), key=lambda x: -x[1])[:5]]
    for d, c in high_cov:
        print(f"  {d}: coverage={c:.1%}, weight={domain_weights[d]:.2f}", file=sys.stderr)

    # ── Phase 3: Similarity + Louvain per level ──
    level_config = {
        1: [("cluster", args.threshold, 1.0)],
        2: [("L1_broad", args.threshold * 0.5, 0.5), ("L2_specific", args.threshold, 1.0)],
        3: [("L1_broad", args.threshold * 0.4, 0.3), ("L2_medium", args.threshold * 0.7, 0.8),
            ("L3_specific", args.threshold, 1.0)],
    }
    levels = level_config[args.levels]
    # Apply resolution override if provided
    if args.resolution is not None:
        levels = [(name, thresh, args.resolution) for name, thresh, _ in levels]
    lang = "Polish" if args.hl == "pl" else "English"

    # Compute pairwise similarity once (expensive)
    kw_list = list(all_serps.keys())
    n = len(kw_list)
    print(f"\n[Phase 3] Computing {n*(n-1)//2} pairwise similarities...", file=sys.stderr)

    # Build domain -> keyword indices for max_pairs_per_domain limiting
    domain_to_kw_indices = defaultdict(set)
    for idx, kw in enumerate(kw_list):
        for r in all_serps[kw]:
            domain_to_kw_indices[r["domain"]].add(idx)

    # Limit pairs per domain: max_pairs / sqrt(coverage), clamped
    max_pairs_base = args.max_pairs_per_domain
    domain_pair_limits = {}
    for domain, cov in coverage.items():
        if cov > 0.05:
            limit = int(max_pairs_base / math.sqrt(cov))
            domain_pair_limits[domain] = max(2000, min(limit, 50000))

    pair_sims = {}  # (i,j) -> sim
    t0 = time.time()
    for i in range(n):
        for j in range(i + 1, n):
            sim = weighted_jaccard(all_serps[kw_list[i]], all_serps[kw_list[j]],
                                    domain_weights, domain_bonus=args.domain_bonus,
                                    min_shared_urls=args.min_shared_urls)
            if sim > 0.01:
                pair_sims[(i, j)] = sim
    elapsed = time.time() - t0
    print(f"  {len(pair_sims)} non-trivial pairs ({elapsed:.1f}s)", file=sys.stderr)

    all_level_results = {}

    for level_name, level_threshold, resolution in levels:
        print(f"\n[Phase 3] Louvain '{level_name}' (threshold={level_threshold:.2f}, resolution={resolution})...", file=sys.stderr)

        edges = [(kw_list[i], kw_list[j], sim)
                 for (i, j), sim in pair_sims.items() if sim >= level_threshold]
        print(f"  Edges above threshold: {len(edges)}", file=sys.stderr)

        communities = louvain_communities(kw_list, edges, resolution=resolution)

        # Group into clusters
        clusters = defaultdict(list)
        for kw, cid in communities.items():
            clusters[cid].append(kw)

        # Sort by size (all clusters kept — singletons filtered only in report/dendrogram)
        sorted_clusters = sorted(clusters.items(), key=lambda x: -len(x[1]))
        multi = sum(1 for _, kws in sorted_clusters if len(kws) >= 2)
        singles = sum(1 for _, kws in sorted_clusters if len(kws) == 1)
        sizes = [len(kws) for _, kws in sorted_clusters]
        print(f"  Clusters: {len(sorted_clusters)} (multi: {multi}, singletons: {singles})", file=sys.stderr)
        if sizes:
            print(f"  Sizes: max={max(sizes)}, avg={sum(sizes)/len(sizes):.1f}", file=sys.stderr)

        # Name clusters
        print(f"  Naming via LLM...", file=sys.stderr)
        to_name = [(cid, kws) for cid, kws in sorted_clusters if len(kws) >= 2]
        cluster_names = name_clusters(to_name, llm_client, args.model, language=lang)
        # Fill singletons
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
    output_path = args.output or str(Path(args.input).parent / f"{Path(args.input).stem}_clustered.csv")
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

    # JSON
    if args.json:
        json_path = output_path.rsplit(".", 1)[0] + ".json"
        json_output = {
            "input": args.input, "gl": args.gl, "hl": args.hl,
            "tokens_used": tokens_used, "keywords_with_serp": len(all_serps),
            "levels": {},
        }
        for level_name, ld in all_level_results.items():
            json_output["levels"][level_name] = {
                "threshold": ld["threshold"], "resolution": ld["resolution"],
                "clusters": [{"id": cid, "name": ld["names"].get(cid, ""), "keywords": kws}
                             for cid, kws in sorted(ld["clusters"].items(), key=lambda x: -len(x[1]))],
            }
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(json_output, f, indent=2, ensure_ascii=False)
        print(f"Saved: {json_path}", file=sys.stderr)

    # Report
    if args.report:
        report = generate_report(all_level_results, all_serps, all_snippets, fmt=args.report)
        ext = "html" if args.report == "html" else "md"
        report_path = output_path.rsplit(".", 1)[0] + f"_report.{ext}"
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"Saved report: {report_path}", file=sys.stderr)

    # ── Final Report ──
    print(f"\n{'='*70}", file=sys.stderr)
    print(f"  SERP CLUSTERING REPORT (Weighted Jaccard + Louvain)", file=sys.stderr)
    print(f"{'='*70}", file=sys.stderr)
    print(f"  Keywords: {len(keywords)} -> {len(all_serps)} with SERP | Tokens: {tokens_used}", file=sys.stderr)

    for level_name, ld in all_level_results.items():
        clusters = ld["clusters"]
        names = ld["names"]
        sorted_c = sorted(clusters.items(), key=lambda x: -len(x[1]))
        multi = sum(1 for _, kws in sorted_c if len(kws) >= 2)
        print(f"\n  --- {level_name} (threshold: {ld['threshold']:.2f}, resolution: {ld['resolution']}) ---", file=sys.stderr)
        print(f"  Clusters: {len(clusters)} | Multi: {multi}", file=sys.stderr)
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
