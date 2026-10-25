"""Attention allocation uses caller-calibrated costs and an explicit resource budget."""

from __future__ import annotations

from collections.abc import Callable
import math

import numpy as np
from scipy.optimize import minimize


def allocate_attention(
    costs: dict[str, Callable[[float], float]],
    bounds: dict[str, tuple[float, float]],
    *,
    budget: float,
    evidence_id: str,
):
    """Optimize simultaneous polling effort; the cost functions are not generic HEPs."""
    if (
        not costs
        or set(costs) != set(bounds)
        or not evidence_id.strip()
        or not math.isfinite(budget)
        or budget <= 0
    ):
        raise ValueError("matched costs/bounds, evidence and positive budget required")
    if any(not math.isfinite(a) or not math.isfinite(b) or a < 0 or a > b for a, b in bounds.values()):
        raise ValueError("finite nonnegative increasing allocation bounds required")
    if sum(a for a, _ in bounds.values()) > budget:
        raise ValueError("minimum effort exceeds available budget")
    names = tuple(costs)
    lower = np.asarray([bounds[name][0] for name in names])

    def objective(values):
        result = sum(float(costs[name](value)) for name, value in zip(names, values))
        if not math.isfinite(result):
            raise ValueError("cost model returned nonfinite value")
        return result

    result = minimize(
        objective,
        lower,
        method="SLSQP",
        bounds=[bounds[name] for name in names],
        constraints=[{"type": "ineq", "fun": lambda x: budget - sum(x)}],
        options={"ftol": 1e-10, "maxiter": 1000},
    )
    if not result.success or sum(result.x) > budget + 1e-8:
        raise ValueError(f"attention optimization failed: {result.message}")
    return {
        "allocation": dict(zip(names, result.x.tolist())),
        "cost": float(result.fun),
        "budget": budget,
        "evidence_id": evidence_id,
        "global_optimum_claim": False,
    }
