"""Standalone HTML report with inline D3.js dendrogram.

Used when the user passes --report html to cluster.py. Self-contained
output (own CSS, own inline D3 JS). For a branded report section that
plugs into the shared report system, see section.py.
"""

import json
from collections import defaultdict

from .hierarchy import build_hierarchy_tree


def generate_html_report(all_level_results, all_serps, all_snippets):
    """Generate a standalone HTML clustering report."""
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

    tree_data = build_hierarchy_tree(all_level_results)

    lines = []
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
    return "\n".join(lines)
