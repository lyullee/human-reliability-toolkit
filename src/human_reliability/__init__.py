"""Composable human reliability models with explicit evidence and applicability."""

from .contracts import (
    Context,
    ContextValue,
    Estimate,
    Evidence,
    HumanFailureEvent,
    MethodInput,
    SignalSeries,
    Task,
    TaskStep,
    canonical_digest,
)
from .probability import BetaPrior, demand_frequency, interval_probability
from .methods import MethodRegistry, cognitive_chain, declared_estimator
from .qualitative import analyze_task
from .evidence_catalog import (
    ApplicabilityReview,
    HumanErrorRecord,
    HumanEvidenceCatalog,
    HumanEvidenceSource,
    annual_frequency_from_evidence,
    builtin_evidence_catalog,
    load_evidence_catalog,
    sacada_context_labels,
)

__version__ = "0.2.0"
__all__ = [
    "Context",
    "ContextValue",
    "Estimate",
    "Evidence",
    "HumanFailureEvent",
    "MethodInput",
    "SignalSeries",
    "Task",
    "TaskStep",
    "canonical_digest",
    "BetaPrior",
    "demand_frequency",
    "interval_probability",
    "MethodRegistry",
    "cognitive_chain",
    "declared_estimator",
    "analyze_task",
    "ApplicabilityReview",
    "HumanErrorRecord",
    "HumanEvidenceCatalog",
    "HumanEvidenceSource",
    "annual_frequency_from_evidence",
    "builtin_evidence_catalog",
    "load_evidence_catalog",
    "sacada_context_labels",
]
