"""Conditional branch partitions and risk ledgers conserve initiating frequency."""

from __future__ import annotations

from dataclasses import dataclass
import math

from .probability import nonnegative, probability


@dataclass(frozen=True)
class Branch:
    id: str
    probability_given_path: float
    children: tuple[Branch, ...] = ()
    consequence_id: str | None = None
    evidence: str = ""

    def __post_init__(self):
        probability(self.probability_given_path)
        if not self.id.strip() or not self.evidence.strip():
            raise ValueError("branch identity and evidence required")
        if self.children:
            _partition(self.children)
            if self.consequence_id is not None:
                raise ValueError("only terminal branches can own consequences")
        elif not self.consequence_id:
            raise ValueError("terminal branch requires a consequence including no-harm outcomes")


def _partition(branches):
    if not branches or len({branch.id for branch in branches}) != len(branches):
        raise ValueError("partition requires nonempty unique branch IDs")
    if not math.isclose(
        math.fsum(branch.probability_given_path for branch in branches), 1, abs_tol=1e-12, rel_tol=0
    ):
        raise ValueError("sibling conditional probabilities must sum to one")


def event_tree(initiating_frequency_per_year: float, branches: tuple[Branch, ...]):
    frequency = nonnegative(initiating_frequency_per_year)
    _partition(branches)
    rows = []

    def walk(nodes, weight, path):
        for node in nodes:
            p = weight * node.probability_given_path
            current = path + (node.id,)
            if node.children:
                walk(node.children, p, current)
            else:
                rows.append(
                    {
                        "path": current,
                        "probability_given_initiation": p,
                        "annual_frequency_per_year": frequency * p,
                        "consequence_id": node.consequence_id,
                        "evidence": node.evidence,
                    }
                )

    walk(branches, 1.0, ())
    return tuple(rows)


def protection_partition(
    auto_success: float, human_failure_given_auto_failure: float, *, auto_evidence: str, human_evidence: str
):
    pa, qh = probability(auto_success), probability(human_failure_given_auto_failure)
    return (
        Branch("automatic_success", pa, consequence_id="automatic_isolation", evidence=auto_evidence),
        Branch(
            "automatic_failure",
            1 - pa,
            evidence=auto_evidence,
            children=(
                Branch("manual_success", 1 - qh, consequence_id="manual_isolation", evidence=human_evidence),
                Branch("manual_failure", qh, consequence_id="no_isolation", evidence=human_evidence),
            ),
        ),
    )


def individual_risk_rate(ledger, conditional_harm: dict[str, float]):
    """Annual risk rate at one declared receptor; occupancy must be included once."""
    total = 0.0
    for row in ledger:
        key = row["consequence_id"]
        if key not in conditional_harm:
            raise ValueError(f"missing consequence probability: {key}")
        total += nonnegative(row["annual_frequency_per_year"]) * probability(conditional_harm[key])
    return total


def fn_curve(ledger, fatality_distribution: dict[str, dict[int, float]], thresholds):
    """Annual frequency of N or more fatalities from conditional discrete outcomes."""
    for outcomes in fatality_distribution.values():
        if not outcomes or any(type(n) is not int or n < 0 for n in outcomes):
            raise ValueError("nonnegative integer fatality counts required")
        if not math.isclose(sum(probability(p) for p in outcomes.values()), 1, abs_tol=1e-12, rel_tol=0):
            raise ValueError("conditional fatality distribution must sum to one")
    result = {}
    for n in thresholds:
        if type(n) is not int or n < 1:
            raise ValueError("F-N thresholds must be positive integers")
        value = 0.0
        for row in ledger:
            if row["consequence_id"] not in fatality_distribution:
                raise ValueError("missing conditional fatality distribution")
            outcomes = fatality_distribution[row["consequence_id"]]
            value += nonnegative(row["annual_frequency_per_year"]) * sum(
                p for count, p in outcomes.items() if count >= n
            )
        result[n] = value
    return result
