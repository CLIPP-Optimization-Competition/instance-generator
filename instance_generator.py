# IEN = Internal Explanation Note

import heapq
import random

from instance_models import (
    Edge,
    InstanceParams,
    Street,
    LENGTH_MIN,
    LENGTH_MAX,
    STREET_CATEGORIES,
    REQUIREMENTS,
    TIME_MIN,
    TIME_MAX,
    VEHICLE_TYPES,
)
from instance_utils import build_adjacency_with_time, dijkstra
from instance_validator import instance_params_param_validator, street_param_validator

# T slack: so instances aren't too tight (more optional/connector, easier to solve)
SLACK_MIN_SEC = 300       # at least 5 minutes extra
SLACK_FRACTION = 0.5     # or 50% of required_t

# Re-export for callers that import from instance_generator
__all__ = [
    "InstanceParams",
    "Street",
    "Edge",
    "choose_edges",
    "build_streets_from_edges",
    "generate_instance",
    "generate_vehicle_types",
    "instance_to_string",
    "write_instance",
    "main",
]


# GRAPH CONSTRUCTION ----------------------------------------------------
# IEN-1: We need the graph of streets (edges). We first create a "spanning tree"
#        so every junction is connected to the depot. Then we add the extra streets needed
#        until we have exactly M streets (edges) in the instance.
def create_edge(junction_one: int, junction_two: int) -> Edge:
    low = min(junction_one, junction_two)
    high = max(junction_one, junction_two)
    return Edge(a=low, b=high)

# IEN-2: A "spanning tree" is a subgraph of a connected, undirected graph that includes all vertices of the original graph, connected with the minimum possible number of edges and no cycles (n_junctions − 1). 
def random_spanning_tree_edges(n_junctions: int, rng: random.Random) -> list[Edge]:
    node_order = list(range(n_junctions))
    rng.shuffle(node_order)

    edges = []
    for i in range(1, n_junctions):
        node_to_add = node_order[i]
        index_of_node_already_in_graph = rng.randint(0, i - 1)
        node_already_in_graph = node_order[index_of_node_already_in_graph]

        edge = create_edge(node_to_add, node_already_in_graph)
        edges.append(edge)

    return edges

# IEN-3: Uses that "spanning tree" and then adds more edges until we have exactly M (We need exactly M streets (edges) in the instance)
def choose_edges(n_junctions: int, n_streets: int, rng: random.Random) -> list[Edge]:
    tree_edges = random_spanning_tree_edges(n_junctions, rng)
    tree_set = set(tree_edges)

    all_possible_edges = []
    for a in range(n_junctions):
        for b in range(a + 1, n_junctions):
            all_possible_edges.append(Edge(a=a, b=b))

    edges_not_in_tree = [e for e in all_possible_edges if e not in tree_set]
    rng.shuffle(edges_not_in_tree)

    n_extra_needed = n_streets - len(tree_edges)
    extra_edges = edges_not_in_tree[:n_extra_needed]

    return tree_edges + extra_edges


# ASSIGNING STREET DATA -----------------------------------------------------
# IEN-4: Each edge becomes a Street with direction, time, length, category (M/O/C),
#        and requirement. We assign categories so at least one street is mandatory.
# IEN-5: Spanning tree edges are two-way so every junction is reachable from the depot.
def build_streets_from_edges(
    edges: list[Edge], n_junctions: int, rng: random.Random
) -> list[Street]:
    n = len(edges)
    tree_set = set(edges[: n_junctions - 1])
    one_mandatory = [STREET_CATEGORIES[0]]
    rest_random = [rng.choice(STREET_CATEGORIES) for _ in range(n - 1)]
    categories = one_mandatory + rest_random
    rng.shuffle(categories)

    streets = []
    for edge, category in zip(edges, categories):
        direction = 2 if edge in tree_set else rng.choice((1, 2))
        traversal_time = rng.randint(TIME_MIN, TIME_MAX)

        junction_a = edge.a
        junction_b = edge.b
        if direction == 1 and rng.choice((True, False)):
            junction_a, junction_b = edge.b, edge.a

        if category == "C":
            length = 0
            requirement = 0
        else:
            length = rng.randint(LENGTH_MIN, LENGTH_MAX)
            requirement = rng.choice(REQUIREMENTS)

        street = Street(
            a=junction_a,
            b=junction_b,
            direction=direction,
            traversal_time=traversal_time,
            length=length,
            category=category,
            requirement=requirement,
        )
        streets.append(street)

    return streets


# VEHICLE TYPES (spec: C types from {S, M, L}) --------------------------
def generate_vehicle_types(c: int, rng: random.Random) -> list[str]:
    return [rng.choice(VEHICLE_TYPES) for _ in range(c)]


# FEASIBILITY: T must allow depot -> mandatory -> depot for each mandatory -------
# IEN-7: Dijkstra from depot (see instance_utils.build_adjacency_with_time, dijkstra).
# IEN-8: T is always at least as big as the time needed to serve every mandatory street and return to the depot.
def sum_mandatory_time(streets: list[Street]) -> int:
    """Total traversal time of all mandatory streets (minimum work that must fit in C*T)."""
    return sum(s.traversal_time for s in streets if s.category == "M")


def min_round_trip_over_mandatories(
    n_junctions: int, depot: int, streets: list[Street]
) -> float:
    """Max over mandatory streets of min depot->street->depot time (inf if unreachable)."""
    adj, rev = build_adjacency_with_time(streets, n_junctions)
    dist_from = dijkstra(n_junctions, depot, adj)
    dist_to = dijkstra(n_junctions, depot, rev)
    max_rt = 0.0
    for s in streets:
        if s.category != "M":
            continue
        cost = s.traversal_time
        if s.direction == 1:
            rt = dist_from[s.a] + cost + dist_to[s.b]
        else:
            rt = min(
                dist_from[s.a] + cost + dist_to[s.b],
                dist_from[s.b] + cost + dist_to[s.a],
            )
        if rt == float("inf"):
            return float("inf")
        max_rt = max(max_rt, rt)
    return max_rt


# WRITE INSTANCE (spec: 1 + M + 1 lines) ----------------------------------
def instance_to_string(
    params: InstanceParams,
    streets: list[Street],
    vehicles: list[str],
) -> str:
    """Return instance file content as a string (same format as on disk)."""
    lines = [
        f"{params.n_junctions} {params.n_streets} {params.time_limit} "
        f"{params.n_vehicles} {params.depot} {params.w_penalty}",
        *(s.to_line() for s in streets),
        " ".join(vehicles),
    ]
    return "\n".join(lines) + "\n"


def write_instance(
    path: str,
    params: InstanceParams,
    streets: list[Street],
    vehicles: list[str],
) -> None:
    with open(path, "w", newline="\n") as f:
        f.write(instance_to_string(params, streets, vehicles))


# MAIN --------------------------------------------------------------------
def generate_instance(params: InstanceParams) -> tuple[list[Street], list[str]]:
    """One feasible instance: connected graph, at least one M, T >= round-trips."""
    instance_params_param_validator(params)
    rng = random.Random(params.seed)
    edges = choose_edges(params.n_junctions, params.n_streets, rng)
    streets = build_streets_from_edges(edges, params.n_junctions, rng)
    for s in streets:
        street_param_validator(s, params.n_junctions)
    vehicles = generate_vehicle_types(params.n_vehicles, rng)
    return streets, vehicles


def main() -> None:
    import argparse
    import os

    parser = argparse.ArgumentParser(description="Generate CLIPP instances (v2)")
    parser.add_argument("-n", "--junctions", type=int, default=20)
    parser.add_argument("-m", "--streets", type=int, default=45)
    parser.add_argument("-t", "--time-limit", type=int, default=3600)
    parser.add_argument(
        "-c", "--vehicles", type=int, default=3,
        help="Number of vehicles (2 to 100)",
    )
    parser.add_argument("-s", "--depot", type=int, default=0)
    parser.add_argument("-w", "--w-penalty", type=float, default=1.0,
                        help="Water waste penalty factor W (>= 0)")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("-o", "--output", type=str, default="instance.txt")

    args = parser.parse_args()

    params = InstanceParams(
        n_junctions=args.junctions,
        n_streets=args.streets,
        time_limit=args.time_limit,
        n_vehicles=args.vehicles,
        depot=args.depot,
        w_penalty=args.w_penalty,
        seed=args.seed,
    )
    streets, vehicles = generate_instance(params)
    required_t = min_round_trip_over_mandatories(
        params.n_junctions, params.depot, streets
    )
    total_mandatory = sum_mandatory_time(streets)
    # T must be at least: (1) max single mandatory round-trip, (2) total_mandatory/C so sum <= C*T
    t_from_round_trip = 0
    if required_t != float("inf"):
        slack = max(SLACK_MIN_SEC, int(required_t * SLACK_FRACTION))
        t_from_round_trip = int(required_t) + slack
    t_from_budget = 0
    if params.n_vehicles > 0 and total_mandatory > 0:
        # need total_mandatory <= C*T  =>  T >= total_mandatory/C; add slack for travel between streets
        min_t_per_vehicle = (total_mandatory + params.n_vehicles - 1) // params.n_vehicles
        t_from_budget = min_t_per_vehicle + max(SLACK_MIN_SEC, min_t_per_vehicle // 2)
    params.time_limit = max(
        params.time_limit,
        t_from_round_trip,
        t_from_budget,
    )
    out_dir = os.path.dirname(args.output)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    write_instance(args.output, params, streets, vehicles)
    print(
        f"Wrote {args.output}: N={params.n_junctions} M={params.n_streets} "
        f"T={params.time_limit} C={params.n_vehicles} depot={params.depot}"
    )


if __name__ == "__main__":
    main()
