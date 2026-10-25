"""LOPA-style screening requires declared independence and feasible human response."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .probability import nonnegative, probability


@dataclass(frozen=True)
class Barrier:
    id: str
    kind: Literal["human", "automatic", "passive"]
    failure_on_demand: float
    evidence: str
    independence_evidence: str
    dependency_groups: tuple[str, ...] = ()
    response_feasible: bool | None = None

    def __post_init__(self):
        probability(self.failure_on_demand)
        if (
            not self.id.strip()
            or not self.evidence.strip()
            or self.kind not in {"human", "automatic", "passive"}
        ):
            raise ValueError("barrier identity, kind and reliability evidence required")


def lopa_screen(
    initiating_frequency_per_year: float,
    barriers: tuple[Barrier, ...],
    *,
    initiating_dependency_groups: tuple[str, ...] = (),
):
    """Do not credit overlapping protection layers as independent multipliers."""
    frequency = nonnegative(initiating_frequency_per_year)
    if not barriers or len({barrier.id for barrier in barriers}) != len(barriers):
        raise ValueError("nonempty unique barriers required")
    seen = set(initiating_dependency_groups)
    reasons = []
    for barrier in barriers:
        if not barrier.independence_evidence.strip():
            reasons.append(f"{barrier.id}: independence evidence missing")
        if seen & set(barrier.dependency_groups):
            reasons.append(f"{barrier.id}: shared dependency requires joint modeling")
        seen.update(barrier.dependency_groups)
        if barrier.kind == "human" and barrier.response_feasible is not True:
            reasons.append(f"{barrier.id}: feasible response not established")
    result = frequency
    for barrier in barriers:
        result *= barrier.failure_on_demand
    return {
        "status": "withheld" if reasons else "declared_independent_screen",
        "residual_frequency_per_year": None if reasons else result,
        "reasons": reasons,
        "initiating_frequency_per_year": frequency,
        "certified_ipl_claim": False,
    }
