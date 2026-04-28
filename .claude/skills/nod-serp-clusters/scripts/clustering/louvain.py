"""Louvain community detection — modularity optimization on weighted graph."""

import random
from collections import defaultdict


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
