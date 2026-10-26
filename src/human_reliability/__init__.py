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
from .actions import (
    Command,
    EquipmentCapability,
    ExecutableAction,
    ProcessState,
    StatePredicate,
    StateValue,
    execute_action,
)
from .causal import CausalGraph, CausalLeaf, CausalGate, evaluate_causal_graph
from .risk import RiskCase, RiskEngine
from .dynamics import CoupledCase, RuntimeJob, StateProcess, run_coupled_case, run_coupled_episode
from .method_workflows import MethodWorkflowCase, run_method_workflow
from .field_data import FieldSource, field_sources
from .collection import CollectionBundle, CollectionProtocol, load_collection, write_collection_kit
from .opportunity_validation import ValidationPlan, validate_collection

__version__ = "0.5.0"
__all__ = [
    "CollectionBundle",
    "CollectionProtocol",
    "load_collection",
    "write_collection_kit",
    "ValidationPlan",
    "validate_collection",
    "FieldSource",
    "field_sources",
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
    "Command",
    "EquipmentCapability",
    "ExecutableAction",
    "ProcessState",
    "StatePredicate",
    "StateValue",
    "execute_action",
    "CausalGraph",
    "CausalLeaf",
    "CausalGate",
    "evaluate_causal_graph",
    "RiskCase",
    "RiskEngine",
    "CoupledCase",
    "RuntimeJob",
    "StateProcess",
    "run_coupled_case",
    "run_coupled_episode",
    "MethodWorkflowCase",
    "run_method_workflow",
]
