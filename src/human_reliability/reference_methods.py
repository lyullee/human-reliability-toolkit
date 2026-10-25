"""Reviewed numeric profiles feed existing arithmetic without inventing observations."""

from __future__ import annotations

import math

from .evidence_catalog import builtin_evidence_catalog
from .methods import SPAR_H_FACTORS, heart_probability, spar_h_probability
from .probability import probability, union_independent


def spar_h_profile_probability(stage: str, levels: dict[str, str], *, allow_unknown=False, catalog=None):
    """Apply the cited at-power profile; all eight categorical choices are explicit."""
    catalog = catalog or builtin_evidence_catalog()
    if stage not in {"diagnosis", "action"} or set(levels) != SPAR_H_FACTORS:
        raise ValueError("diagnosis/action and exactly eight named PSF selections required")
    if type(allow_unknown) is not bool:
        raise ValueError("allow_unknown must be boolean")
    values, identities, terminals = {}, [], []
    for psf, level in levels.items():
        if not isinstance(level, str):
            raise ValueError("PSF category must be a string")
        row = catalog.get(f"spar_h.{stage}.{psf}.{level}")
        if (
            row.kind not in {"method_multiplier", "method_rule"}
            or row.conditions.get("profile") != "at_power"
        ):
            raise ValueError("selected record is not a supported at-power PSF reference")
        if row.basis == "placeholder" and not allow_unknown:
            raise ValueError("unknown PSF information requires explicit allow_unknown=True")
        identities.append(row.id)
        if row.kind == "method_rule":
            terminals.append(row.id)
            values[psf] = 1.0
        else:
            values[psf] = row.value
    nominal = catalog.get("spar_h.nominal." + stage)
    value, trace = spar_h_probability(stage, values, nominal=nominal.value)
    return (1.0 if terminals else value), trace | {
        "profile": "NUREG/CR-6883 Appendix A at-power",
        "record_ids": [nominal.id, *identities],
        "selected_levels": dict(levels),
        "terminal_conditions": terminals,
        "without_terminal_rules": value,
        "observed_probability": False,
    }


def heart_profile_probability(task_code: str, effects, *, catalog=None):
    """effects contains explicit (EPC record ID, assessed proportion) pairs."""
    catalog = catalog or builtin_evidence_catalog()
    nominal = catalog.get("heart.gtt." + task_code)
    if nominal.kind != "method_probability" or nominal.conditions.get("generic_task_code") != task_code:
        raise ValueError("a reviewed generic HEART task reference is required")
    selected = tuple(effects)
    if len({identity for identity, _ in selected}) != len(selected):
        raise ValueError("an EPC record cannot be applied twice")
    arguments = []
    for identity, proportion in selected:
        row = catalog.get(identity)
        if row.method != "heart" or row.kind != "method_multiplier" or "epc_code" not in row.conditions:
            raise ValueError("selected effect is not a HEART EPC")
        arguments.append((row.value, probability(proportion)))
    if len({catalog.get(identity).conditions["epc_code"] for identity, _ in selected}) != len(selected):
        raise ValueError("alternative levels of one EPC must not be combined")
    value, trace = heart_probability(nominal.value, tuple(arguments))
    return value, trace | {
        "record_ids": [nominal.id, *(identity for identity, _ in selected)],
        "assessed_proportions": dict(selected),
        "observed_probability": False,
        "profile_source": "CC-BY source 10.1371/journal.pone.0253827, Tables 1-2",
    }


def idheas_cfm_probability(
    function: str,
    base_probabilities: dict[str, float],
    modifier_weights: dict[str, float],
    *,
    recovery_divisor=1.0,
):
    """NUREG-2256 equations 3.4/3.5 arithmetic for one cognitive function.

    Attribute selection, attribution to PIFs, uncertainty, task aggregation and time
    remain application responsibilities. This kernel does not multiply modifier weights.
    """
    if function not in {"detection", "understanding", "decision", "action", "coordination"}:
        raise ValueError("unknown cognitive function")
    if set(base_probabilities) != {"scenario_familiarity", "information", "task_complexity"}:
        raise ValueError("all three named base influences must be explicitly specified")
    if (
        isinstance(recovery_divisor, (bool, str))
        or not math.isfinite(recovery_divisor)
        or recovery_divisor < 1
    ):
        raise ValueError("recovery divisor must be finite and at least one")
    if any(isinstance(w, (bool, str)) or not math.isfinite(w) or w < 1 for w in modifier_weights.values()):
        raise ValueError("modification weights must be finite and at least one")
    base = union_independent(base_probabilities.values())
    floor_used = base == 0
    if floor_used:
        base = 0.0001 if function in {"detection", "action"} else 0.001
    modification = 1 + math.fsum(weight - 1 for weight in modifier_weights.values())
    raw = base * modification / recovery_divisor
    if not math.isfinite(raw):
        raise ValueError("cognitive function calculation overflow")
    return min(1.0, raw), {
        "function": function,
        "base_probability": base,
        "all_base_factors_inactive_floor_used": floor_used,
        "base_inputs": base_probabilities,
        "modifier_weights": modifier_weights,
        "additive_excess_weight": modification,
        "recovery_divisor": recovery_divisor,
        "uncapped_probability": raw,
        "bounded_to_one": raw > 1,
        "scope": "single cognitive function arithmetic; no timing or HFE aggregation",
        "source": "NUREG-2256 equations 3.4/3.5 and Appendix B introductory floor",
        "official_full_method_implementation": False,
    }
