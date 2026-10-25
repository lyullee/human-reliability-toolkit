"""Structured HAZOP/FMECA handoffs and caller-defined qualitative risk matrices."""

from __future__ import annotations

from dataclasses import dataclass

from .qualitative import Finding


def hazop_rows(findings: tuple[Finding, ...]):
    return tuple(
        {
            "human_event_candidate_id": finding.id,
            "task_id": finding.task_id,
            "step_id": finding.step_id,
            "deviation": finding.rule_id,
            "cause_concern": finding.concern,
            "consequence": finding.consequence,
            "existing_controls": list(finding.controls),
            "status": finding.status,
            "rationale": finding.rationale,
            "evidence_ids": list(finding.evidence_ids),
        }
        for finding in findings
    )


@dataclass(frozen=True)
class FailureMode:
    id: str
    step_id: str
    mode: str
    local_effect: str
    system_effect: str
    detection: str
    recovery: str
    evidence_ids: tuple[str, ...]
    probability_event_id: str | None = None


class RiskMatrix:
    """Ordinal labels are supplied by the application, never converted into HEPs."""

    def __init__(self, severities: tuple[str, ...], likelihoods: tuple[str, ...], cells: dict):
        required = {(severity, likelihood) for severity in severities for likelihood in likelihoods}
        if (
            not severities
            or not likelihoods
            or len(set(severities)) != len(severities)
            or len(set(likelihoods)) != len(likelihoods)
            or set(cells) != required
        ):
            raise ValueError("risk matrix requires all declared severity/likelihood cells")
        if any(not str(value).strip() for value in cells.values()):
            raise ValueError("matrix labels must be nonempty")
        self.cells = dict(cells)

    def classify(self, severity, likelihood):
        if (severity, likelihood) not in self.cells:
            raise ValueError("unknown severity or likelihood class")
        return self.cells[severity, likelihood]
