#!/usr/bin/env python3
"""
Standalone script: generate a feasible instance with T fixed at 8h (28800 s).
Uses bounded retries (different seeds) until one instance fits. No changes to
instance_generator.py or app.
"""
import argparse
import os
import sys

# Run from project root so imports work
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from instance_generator import (
    generate_instance,
    min_round_trip_over_mandatories,
    write_instance,
    sum_mandatory_time,
)
from instance_models import InstanceParams
from instance_validator import check_full_feasibility_greedy

T_8H = 28800
MAX_ATTEMPTS = 200


def is_feasible_for_t(n_junctions: int, depot: int, streets, time_limit: int, n_vehicles: int) -> bool:
    """True if instance fits in time_limit: round-trip and budget constraints."""
    required_t = min_round_trip_over_mandatories(n_junctions, depot, streets)
    if required_t == float("inf") or required_t > time_limit:
        return False
    total_mandatory = sum_mandatory_time(streets)
    if total_mandatory > n_vehicles * time_limit:
        return False
    return True


def has_full_feasibility(n_junctions: int, depot: int, streets, time_limit: int, n_vehicles: int) -> bool:
    """True if greedy packer can assign all mandatory streets to C routes within T."""
    return check_full_feasibility_greedy(n_junctions, depot, time_limit, n_vehicles, streets)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a feasible CLIPP instance with T fixed at 8h (28800 s). Bounded retries."
    )
    parser.add_argument("-n", "--junctions", type=int, default=20, help="N (default: 20, better for full feasibility)")
    parser.add_argument("-m", "--streets", type=int, default=45, help="M (default: 45)")
    parser.add_argument("-c", "--vehicles", type=int, default=5, help="C (default: 5)")
    parser.add_argument("-s", "--depot", type=int, default=0)
    parser.add_argument("-a", "--alpha", type=float, default=0.5)
    parser.add_argument("-o", "--output", type=str, default="instances/8h_strict/instance_8h.txt")
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=MAX_ATTEMPTS,
        help=f"Max seeds to try (default: {MAX_ATTEMPTS})",
    )
    args = parser.parse_args()

    n_junctions = args.junctions
    n_streets = args.streets
    n_vehicles = args.vehicles
    depot = args.depot
    alpha = args.alpha
    output = args.output
    max_attempts = args.max_attempts

    print(f"Fixed T = {T_8H} s (8h). Trying up to {max_attempts} attempts (N={n_junctions}, M={n_streets}, C={n_vehicles})...")

    for attempt in range(max_attempts):
        seed = attempt
        params = InstanceParams(
            n_junctions=n_junctions,
            n_streets=n_streets,
            time_limit=T_8H,
            n_vehicles=n_vehicles,
            depot=depot,
            alpha=alpha,
            seed=seed,
        )
        try:
            streets, vehicles = generate_instance(params)
        except Exception as e:
            print(f"  Attempt {attempt + 1} (seed={seed}): generation failed: {e}", file=sys.stderr)
            continue

        if not is_feasible_for_t(n_junctions, depot, streets, T_8H, n_vehicles):
            if (attempt + 1) % 10 == 0:
                print(f"  ... {attempt + 1} attempts so far")
            continue
        if not has_full_feasibility(n_junctions, depot, streets, T_8H, n_vehicles):
            if (attempt + 1) % 10 == 0:
                print(f"  ... {attempt + 1} attempts so far")
            continue
        out_dir = os.path.dirname(output)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        params.time_limit = T_8H
        write_instance(output, params, streets, vehicles)
        print(f"Feasible instance with FULL FEASIBILITY: yes, found on attempt {attempt + 1} (seed={seed}).")
        print(f"Wrote {output}: N={n_junctions} M={n_streets} T={T_8H} C={n_vehicles} depot={depot}")
        return

    print(
        f"Could not find an instance with FULL FEASIBILITY: yes in {max_attempts} attempts for N={n_junctions}, M={n_streets}, C={n_vehicles}.",
        file=sys.stderr,
    )
    print("Try smaller N/M, or more vehicles (C), or increase --max-attempts.", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
