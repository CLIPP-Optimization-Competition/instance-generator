# Shared types and bounds for v2 (no circular dependency with generator/validator).

from dataclasses import dataclass
from typing import NamedTuple, Optional

### PROBLEM BOUNDS (from problem statement) ----------------------------
N_MIN, N_MAX = 1, 10**4
M_MIN, M_MAX = 1, 10**5
T_MIN, T_MAX = 1, 10**6
C_MIN, C_MAX = 2, 10**2
TIME_MIN, TIME_MAX = 1, 10**4
LENGTH_MIN, LENGTH_MAX = 0, 10**4

STREET_CATEGORIES = ("M", "O", "C")
REQUIREMENTS = (10, 20, 30)
VEHICLE_TYPES = ("S", "M", "L")


@dataclass
class InstanceParams:
    n_junctions: int
    n_streets: int
    time_limit: int
    n_vehicles: int
    depot: int
    alpha: float = 0.5
    seed: Optional[int] = None


@dataclass
class Street:
    a: int
    b: int
    direction: int       # 1 = one-way A→B, 2 = two-way
    traversal_time: int
    length: int
    category: str        # M, O, or C
    requirement: int     # 10, 20, or 30 (0 for connector)

    def to_line(self) -> str:
        return f"{self.a} {self.b} {self.direction} {self.traversal_time} {self.length} {self.category} {self.requirement}"


class Edge(NamedTuple):
    a: int
    b: int
