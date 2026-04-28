"""Build a multi-level cluster hierarchy tree for dendrogram rendering."""

from collections import defaultdict


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
