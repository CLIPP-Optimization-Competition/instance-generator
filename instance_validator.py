from typing import Callable

from instance_models import (
    InstanceParams,
    Street,
    N_MIN,
    N_MAX,
    M_MIN,
    M_MAX,
    T_MIN,
    T_MAX,
    C_MIN,
    C_MAX,
    TIME_MIN,
    TIME_MAX,
    LENGTH_MIN,
    LENGTH_MAX,
    STREET_CATEGORIES,
    REQUIREMENTS,
    VEHICLE_TYPES,
)
from instance_utils import build_adjacency_with_time, dijkstra

# PARAMETER VALIDATION --------------------------------------------------------------------------

def instance_params_param_validator(params: InstanceParams) -> None:
    """Raises ValueError if any field is out of bounds or inconsistent."""
    if not (N_MIN <= params.n_junctions <= N_MAX):
        raise ValueError(f"n_junctions must be in [{N_MIN}, {N_MAX}], got {params.n_junctions}")
    if not (M_MIN <= params.n_streets <= M_MAX):
        raise ValueError(f"n_streets must be in [{M_MIN}, {M_MAX}], got {params.n_streets}")
    if not (T_MIN <= params.time_limit <= T_MAX):
        raise ValueError(f"time_limit must be in [{T_MIN}, {T_MAX}], got {params.time_limit}")
    if not (C_MIN <= params.n_vehicles <= C_MAX):
        raise ValueError(f"n_vehicles must be in [{C_MIN}, {C_MAX}], got {params.n_vehicles}")
    if not (0 <= params.depot < params.n_junctions):
        raise ValueError(f"depot must be in [0, n_junctions-1], got {params.depot}")
    max_edges = params.n_junctions * (params.n_junctions - 1) // 2
    if params.n_streets > max_edges:
        raise ValueError(f"n_streets cannot exceed {max_edges} for {params.n_junctions} junctions")
    if params.n_streets < params.n_junctions - 1:
        raise ValueError("n_streets must be at least n_junctions-1 for a connected graph")


def street_param_validator(street: Street, n_junctions: int) -> None:
    """Raises ValueError if any field is out of bounds or inconsistent."""
    if not (0 <= street.a < n_junctions and 0 <= street.b < n_junctions):
        raise ValueError(f"junctions a,b must be in [0, {n_junctions}-1], got {street.a}, {street.b}")
    if street.a == street.b:
        raise ValueError("a and b must be different")
    if street.direction not in (1, 2):
        raise ValueError(f"direction must be 1 or 2, got {street.direction}")
    if not (TIME_MIN <= street.traversal_time <= TIME_MAX):
        raise ValueError(f"traversal_time must be in [{TIME_MIN}, {TIME_MAX}], got {street.traversal_time}")
    if not (LENGTH_MIN <= street.length <= LENGTH_MAX):
        raise ValueError(f"length must be in [{LENGTH_MIN}, {LENGTH_MAX}], got {street.length}")
    if street.category not in STREET_CATEGORIES:
        raise ValueError(f"category must be M, O, or C, got {street.category}")
    if street.category == "C":
        if street.length != 0 or street.requirement != 0:
            raise ValueError("connector street must have length=0 and requirement=0")
    else:
        if street.requirement not in REQUIREMENTS:
            raise ValueError(f"requirement must be 10, 20, or 30, got {street.requirement}")


# GENERATED INSTANCE VALIDATION --------------------------------------------------------------
# Validates a full instance (params + streets + vehicles) per CLIPP problem definition.
# Order of checks follows the problem: header/params → streets → vehicles → graph → feasibility.


def _vehicle_capacity(vtype: str) -> int:
    """Water capacity in L/km: S=10, M=20, L=30 (problem definition)."""
    if vtype == "S":
        return 10
    if vtype == "M":
        return 20
    if vtype == "L":
        return 30
    raise ValueError(f"vehicle type must be S, M, or L, got {vtype!r}")


def _all_pairs_distances(n: int, adj: dict[int, list[tuple[int, int]]]) -> list[list[float]]:
    """Return n×n matrix: dist[u][v] = shortest time from u to v. Unreachable = inf."""
    dist = []
    for i in range(n):
        dist.append(dijkstra(n, i, adj))
    return dist


def _check_full_feasibility_greedy(
    n: int,
    depot: int,
    T: int,
    C: int,
    mandatory: list[tuple[int, Street]],
    dist: list[list[float]],
    dist_to_depot: list[float],
) -> bool:
    """
    Try to assign all mandatory streets to C routes so each route stays within time T.
    Greedy: for each vehicle, repeatedly add the mandatory street that minimizes
    extra time from current position (and allows return to depot within T).
    Returns True if a feasible packing is found, False otherwise (heuristic may fail
    even when a solution exists).
    """
    if not mandatory:
        return True
    unassigned = set(range(len(mandatory)))
    for _ in range(C):
        if not unassigned:
            break
        pos = depot
        time_used = 0.0
        while unassigned:
            best_j: int | None = None
            best_cost = float("inf")
            best_new_pos = -1
            for j in unassigned:
                idx, s = mandatory[j]
                t = s.traversal_time
                if s.direction == 1:
                    # only a -> b
                    cost = dist[pos][s.a] + t
                    new_pos = s.b
                else:
                    c1 = dist[pos][s.a] + t
                    c2 = dist[pos][s.b] + t
                    if c1 <= c2:
                        cost, new_pos = c1, s.b
                    else:
                        cost, new_pos = c2, s.a
                return_time = dist_to_depot[new_pos]
                if time_used + cost + return_time <= T and cost < best_cost:
                    best_cost = cost
                    best_j = j
                    best_new_pos = new_pos
            if best_j is None:
                break
            unassigned.remove(best_j)
            pos = best_new_pos
            time_used += best_cost
    return len(unassigned) == 0


def check_full_feasibility_greedy(
    n: int,
    depot: int,
    T: int,
    C: int,
    streets: list[Street],
) -> bool:
    """
    Return True if the greedy packer can assign all mandatory streets to C routes
    each within time T. Use this to require "FULL FEASIBILITY: yes" when generating.
    """
    mandatory_list = [(i, s) for i, s in enumerate(streets) if s.category == "M"]
    adj, rev = build_adjacency_with_time(streets, n)
    dist_to_depot = dijkstra(n, depot, rev)
    dist_matrix = _all_pairs_distances(n, adj)
    return _check_full_feasibility_greedy(
        n, depot, T, C, mandatory_list, dist_matrix, dist_to_depot
    )


def _reachable_from(adj: dict[int, list[tuple[int, int]]], start: int, n: int) -> set[int]:
    """Set of junctions reachable from start following directed edges."""
    seen = {start}
    stack = [start]
    while stack:
        u = stack.pop()
        for v, _ in adj.get(u, []):
            if v not in seen:
                seen.add(v)
                stack.append(v)
    return seen


def validate_generated_instance(
    params: InstanceParams,
    streets: list[Street],
    vehicle_types: list[str],
    *,
    report: Callable[[str], None] | None = None,
) -> None:
    """
    Validate a full CLIPP instance (params + streets + vehicle types).
    Raises ValueError with a clear message on first failure.
    Order of checks follows the problem definition.
    If report is given, call report(msg) after each check passes (msg is a short description).
    """

    def noop(_: str) -> None:
        pass

    report = report or noop
    n = params.n_junctions
    m = params.n_streets
    T = params.time_limit
    C = params.n_vehicles
    depot = params.depot

    # -------------------------------------------------------------------------
    # 1. PARAMETER BOUNDS (problem: first line N M T C S W)
    # -------------------------------------------------------------------------
    instance_params_param_validator(params)
    w = getattr(params, "w_penalty", 1.0)
    if w < 0:
        raise ValueError(f"PARAMETER BOUNDS: W (water waste penalty) must be >= 0, got {w}")
    report(f"PARAMETER BOUNDS: junctions ({n}), streets ({m}), time limit ({T}s), vehicles ({C}), depot ({depot}), penalty (W={w})")

    # -------------------------------------------------------------------------
    # 2. STREET COUNT AND EACH STREET VALID
    # -------------------------------------------------------------------------
    if len(streets) != m:
        raise ValueError(
            f"STREETS: instance has {len(streets)} streets but params.n_streets is {m}"
        )
    seen_edges: set[tuple[int, int]] = set()
    for i, street in enumerate(streets):
        street_param_validator(street, n)
        edge = (min(street.a, street.b), max(street.a, street.b))
        if edge in seen_edges:
            raise ValueError(
                f"STREETS: street {i}: duplicate edge between junctions {street.a} and {street.b} "
                "(each pair of junctions at most one street)"
            )
        seen_edges.add(edge)
    report(f"STREETS: correct count ({m}), each street's junctions/direction/time/length/category/requirement in allowed range, no duplicate: between any two junctions at most one street")

    # -------------------------------------------------------------------------
    # 3. VEHICLE LINE: C types, each S, M, or L (problem: last line)
    # -------------------------------------------------------------------------
    if len(vehicle_types) != C:
        raise ValueError(
            f"VEHICLES: instance has {len(vehicle_types)} vehicle types but params.n_vehicles is {C}"
        )
    if not (C_MIN <= C <= C_MAX):
        raise ValueError(f"VEHICLES: C (number of vehicles) must be in [{C_MIN}, {C_MAX}], got {C}")
    for i, v in enumerate(vehicle_types):
        if v not in VEHICLE_TYPES:
            raise ValueError(
                f"VEHICLES: vehicle {i}: type must be one of {VEHICLE_TYPES}, got {v!r}"
            )
    report(f"VEHICLES: correct count ({C}), each type is S, M or L")

    # -------------------------------------------------------------------------
    # 4. REACHABILITY: every junction reachable from depot (directed graph)
    #    (problem: vehicles may only move along streets respecting one-way)
    # -------------------------------------------------------------------------
    adj, _ = build_adjacency_with_time(streets, n)
    reach = _reachable_from(adj, depot, n)
    if len(reach) < n:
        unreach = set(range(n)) - reach
        unreach_sorted = sorted(unreach)[:10]
        suffix = "..." if len(unreach) > 10 else ""
        raise ValueError(
            f"GRAPH: from depot {depot}, {n - len(reach)} junction(s) unreachable: "
            f"{unreach_sorted}{suffix} (one-way directions prevent reachability)"
        )
    report("GRAPH: verified that every junction is reachable from depot by following street directions")

    # -------------------------------------------------------------------------
    # 5. MANDATORY STREETS: at least one vehicle can clean each (capacity)
    #    (problem: a vehicle can only clean a street if capacity >= requirement)
    # -------------------------------------------------------------------------
    max_capacity = max(_vehicle_capacity(v) for v in vehicle_types)
    for i, s in enumerate(streets):
        if s.category != "M":
            continue
        if max_capacity < s.requirement:
            raise ValueError(
                f"CAPACITY: mandatory street {i} (junctions {s.a}-{s.b}) requires {s.requirement} L/km "
                f"but best vehicle has {max_capacity} L/km; no vehicle can clean it"
            )
    report(f"CAPACITY: verified that best vehicle ({max_capacity} L/km) can clean each mandatory street (capacity ≥ requirement)")

    # -------------------------------------------------------------------------
    # 6. NECESSARY FEASIBILITY: each mandatory street has depot→street→depot within T
    #    Plus necessary condition: total mandatory traversal time must fit in C*T.
    #    Then optional greedy check to see if all mandatory can be packed into C routes.
    # -------------------------------------------------------------------------
    mandatory_list = [(i, s) for i, s in enumerate(streets) if s.category == "M"]
    sum_mandatory_time = sum(s.traversal_time for _, s in mandatory_list)
    if sum_mandatory_time > C * T:
        raise ValueError(
            f"TIME LIMIT: total mandatory street time {sum_mandatory_time}s > C*T ({C}*{T}={C * T}s); "
            "instance is infeasible (not enough time budget)"
        )
    adj, rev = build_adjacency_with_time(streets, n)
    dist_from_depot = dijkstra(n, depot, adj)
    dist_to_depot = dijkstra(n, depot, rev)
    max_round_trip = 0
    for i, s in enumerate(streets):
        if s.category != "M":
            continue
        cost = s.traversal_time
        if s.direction == 1:
            round_trip = dist_from_depot[s.a] + cost + dist_to_depot[s.b]
        else:
            round_trip = min(
                dist_from_depot[s.a] + cost + dist_to_depot[s.b],
                dist_from_depot[s.b] + cost + dist_to_depot[s.a],
            )
        if round_trip == float("inf"):
            raise ValueError(
                f"TIME LIMIT: mandatory street {i} (junctions {s.a}-{s.b}) is unreachable "
                f"from depot {depot} or back to depot in the directed graph"
            )
        if round_trip > T:
            raise ValueError(
                f"TIME LIMIT: mandatory street {i} requires at least {int(round_trip)}s for "
                f"depot→street→depot, exceeding time limit T={T}s"
            )
        max_round_trip = max(max_round_trip, round_trip)
    report(
        f"TIME LIMIT: each mandatory street has depot→street→depot ≤ T on its own "
        f"(max {int(max_round_trip)}s ≤ T={T}s); total mandatory time {sum_mandatory_time}s ≤ C*T={C * T}s"
    )
    # Optional: try to verify full feasibility (all mandatory in C routes of length ≤ T)
    dist_matrix = _all_pairs_distances(n, adj)
    full_ok = _check_full_feasibility_greedy(
        n, depot, T, C, mandatory_list, dist_matrix, dist_to_depot
    )
    if full_ok:
        report("FULL FEASIBILITY: yes (greedy packing of all mandatory streets into C routes within T)")
    else:
        report("FULL FEASIBILITY: not verified (greedy could not pack all mandatory into C routes; instance may still be feasible)")


def _print_instance_summary(params: InstanceParams, streets: list[Street]) -> None:
    """Print a short summary of the instance (counts and totals)."""
    n_m = sum(1 for s in streets if s.category == "M")
    n_o = sum(1 for s in streets if s.category == "O")
    n_c = sum(1 for s in streets if s.category == "C")
    total_mandatory_m = sum(s.length for s in streets if s.category == "M")
    total_optional_m = sum(s.length for s in streets if s.category == "O")
    sum_mandatory_time = sum(s.traversal_time for s in streets if s.category == "M")
    w = getattr(params, "w_penalty", 1.0)
    print("--- Instance summary ---")
    print(f"  Junctions: {params.n_junctions}, Streets: {params.n_streets}, Time limit: {params.time_limit}s, Vehicles: {params.n_vehicles}")
    print(f"  Water waste penalty W: {w}")
    print(f"  Depot: {params.depot}")
    print(f"  Streets: {n_m} mandatory, {n_o} optional, {n_c} connector")
    print(f"  Total mandatory length: {total_mandatory_m} m")
    print(f"  Total optional length: {total_optional_m} m")
    print(f"  Sum of mandatory street times: {sum_mandatory_time} s")


def parse_instance_file(path: str) -> tuple[InstanceParams, list[Street], list[str]]:
    """
    Parse a v2 instance file (first line N M T C S W, M street lines, last line C vehicle types).
    Returns (params, streets, vehicle_types). Raises on parse error.
    """
    with open(path, encoding="utf-8") as f:
        lines = [ln.strip() for ln in f if ln.strip()]
    if len(lines) < 2:
        raise ValueError(f"File has too few lines: {len(lines)}")
    parts = lines[0].split()
    if len(parts) != 6:
        raise ValueError(f"First line must have 6 values (N M T C S W), got {len(parts)}")
    n = int(parts[0])
    m = int(parts[1])
    T = int(parts[2])
    C = int(parts[3])
    depot = int(parts[4])
    w = float(parts[5])
    params = InstanceParams(
        n_junctions=n,
        n_streets=m,
        time_limit=T,
        n_vehicles=C,
        depot=depot,
        w_penalty=w,
        seed=None,
    )
    if len(lines) != 1 + m + 1:
        raise ValueError(f"Expected 1 + {m} + 1 = {1 + m + 1} lines, got {len(lines)}")
    streets = []
    for j in range(1, 1 + m):
        p = lines[j].split()
        if len(p) != 7:
            raise ValueError(f"Street line {j}: expected 7 values, got {len(p)}")
        streets.append(Street(
            a=int(p[0]),
            b=int(p[1]),
            direction=int(p[2]),
            traversal_time=int(p[3]),
            length=int(p[4]),
            category=p[5],
            requirement=int(p[6]),
        ))
    vehicle_types = lines[1 + m].split()
    if len(vehicle_types) != C:
        raise ValueError(f"Vehicle line: expected {C} types, got {len(vehicle_types)}")
    return params, streets, vehicle_types


def validate_instance_file(path: str, *, verbose: bool = False) -> None:
    """
    Load instance from file and run full validation. Raises ValueError if invalid.
    If verbose is True, print a numbered '[OK]' line for each check that passes.
    """
    params, streets, vehicle_types = parse_instance_file(path)
    if verbose:
        counter = [0]  # use list so inner function can mutate

        def report(msg: str) -> None:
            counter[0] += 1
            print(f"{counter[0]}. [OK] {msg}")

        validate_generated_instance(params, streets, vehicle_types, report=report)
        _print_instance_summary(params, streets)
    else:
        validate_generated_instance(params, streets, vehicle_types)


if __name__ == "__main__":
    import sys

    path = sys.argv[1] if len(sys.argv) > 1 else None
    if not path:
        print("Usage: python v2/instance_validator.py <instance.txt>", file=sys.stderr)
        sys.exit(2)
    try:
        validate_instance_file(path, verbose=True)
        print(f"Valid: {path}")
    except ValueError as e:
        msg = str(e)
        category = msg.split(":", 1)[0]
        category_to_index = {
            "PARAMETER BOUNDS": 1,
            "STREETS": 2,
            "VEHICLES": 3,
            "GRAPH": 4,
            "CAPACITY": 5,
            "TIME LIMIT": 6,
            "FULL FEASIBILITY": 7,
        }
        idx = category_to_index.get(category)
        if idx is not None:
            print(f"{idx}. [INVALID] {msg}", file=sys.stderr)
        else:
            print(f"[INVALID] {path}: {msg}", file=sys.stderr)
        sys.exit(1)
