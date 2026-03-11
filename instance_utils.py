# Shared graph helpers for instance_generator and instance_validator (no duplicate code).

import heapq

from instance_models import Street


def build_adjacency_with_time(streets: list[Street], n: int) -> tuple[dict, dict]:
    """
    Forward and reverse adjacency for shortest-path computation.
    Forward: from u -> [(v, time), ...]. Reverse: to u -> [(v, time), ...].
    """
    adj: dict[int, list[tuple[int, int]]] = {}
    rev: dict[int, list[tuple[int, int]]] = {}
    for s in streets:
        a, b, t = s.a, s.b, s.traversal_time
        adj.setdefault(a, []).append((b, t))
        rev.setdefault(b, []).append((a, t))
        if s.direction == 2:
            adj.setdefault(b, []).append((a, t))
            rev.setdefault(a, []).append((b, t))
    return adj, rev


def dijkstra(n: int, source: int, adj: dict[int, list[tuple[int, int]]]) -> list[float]:
    """Shortest path distances from source (in time). Unreachable = inf."""
    dist = [float("inf")] * n
    dist[source] = 0
    heap = [(0, source)]
    while heap:
        d, u = heapq.heappop(heap)
        if d > dist[u]:
            continue
        for v, t in adj.get(u, []):
            nd = d + t
            if nd < dist[v]:
                dist[v] = nd
                heapq.heappush(heap, (nd, v))
    return dist
