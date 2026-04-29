"""D3.js dendrogram JS template for branded report sections.

Used by section.py (renders into shared report system with var(--brand-*) CSS).
The standalone HTML report in report_html.py uses its own inline JS with
hardcoded colors.
"""

import json


def dendrogram_js(tree_data, container_id):
    """Return the D3 dendrogram JavaScript for embedding in a report section.

    Uses var(--brand-*) CSS variables — meant for shared branded reports.
    """
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
