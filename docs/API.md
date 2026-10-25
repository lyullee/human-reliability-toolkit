# Python API and extension guide

Python imports use `human_reliability`. The distribution name is
`human-reliability-toolkit`. Objects are ordinary Python/Pydantic objects and arrays;
no web service or UI is required.

## Human-performance evidence API (0.2.0)

Read [Human-error evidence](HUMAN_ERROR_DATA.md) for full examples. Public exports
include `builtin_evidence_catalog`, `load_evidence_catalog`, `HumanErrorRecord`,
`HumanEvidenceSource`, `HumanEvidenceCatalog`, `ApplicabilityReview`,
`sacada_context_labels` and `annual_frequency_from_evidence`.

`catalog.search` performs exact typed filtering; `catalog.get` selects a stable ID.
`catalog.bind` returns an estimate and evidence records after explicit review.
Observed records need an explicit `BetaPrior`; intervals need an explicit point.
Components and multipliers are rejected as stand-alone HEPs.

`AssessmentEngine(evidence_catalog=custom_catalog)` accepts a caller-owned catalog.
Otherwise the engine loads the built-in catalog lazily. The JSON method name
`evidence_catalog` accepts `record_id`, `review`, optional `prior` and optional
`selected_value`. Its specification must cite the exact source/prior evidence IDs.
`catalog.estimator` also provides the existing registry's callable extension point.

`reference_methods.spar_h_profile_probability` uses eight explicit stage-specific
categories. `heart_profile_probability` uses task/EPC IDs and caller-assessed
proportions. `idheas_cfm_probability` supplies single-function arithmetic. These
return numerical output and trace without inferring field applicability.

## Assessment workflow

```python
from pathlib import Path
from human_reliability.assessment import AssessmentCase, AssessmentEngine

case = AssessmentCase.model_validate_json(Path("input.json").read_text(encoding="utf-8"))
result = AssessmentEngine().assess(case)
```

`AssessmentCase` contains `task`, `context`, `events`, `models`, optional
`deviation_rules`, and `exclusions`. Model parameters are explicit JSON values.
Unknown fields, unsupported schema versions, dangling step references, missing
evidence and inconsistent event/model sets are rejected. `Estimate.includes`
identifies recovery, timing and dependency effects already included.

## Register a custom estimator

```python
from human_reliability import Estimate
from human_reliability.assessment import AssessmentEngine

def application_method(request):
    value = request.parameters["reviewed_probability"]
    return Estimate(
        event_id=request.event.id,
        method="application_method_v1",
        probability=value,
        conditioning=request.event.conditioning,
        evidence_ids=(request.parameters["evidence_id"],),
        status="method_estimate",
    )

engine = AssessmentEngine()
engine.register("application_method", application_method)
# In the case JSON use this method name and its explicit parameter dictionary.
```

Plugins receive `MethodInput.event`, `.context`, `.evidence` and `.parameters`.
Return an `Estimate` for the exact event and conditioning. The registry verifies
evidence identities and required failure scope. It cannot verify that an external
scientific model's assumptions are correct. Keep a model version in its method
identity and preserve input/output digests.

## Probability and dependencies

```python
from human_reliability import BetaPrior
from human_reliability.dependency import apply_recovery

prior = BetaPrior(alpha=1.0, beta=1.0, evidence_id="prior-basis")
estimate = prior.posterior(
    3, 500, event_id="defined-task-failure", observation_id="observations-v1",
    conditioning="same task and declared operating context",
)
unrecovered = apply_recovery(estimate, 0.2, evidence_id="recovery-study")
```

These are illustrative counts and recovery assumptions. For repeated operators,
consider cluster uncertainty and a more suitable hierarchical model. The posterior
method recomputes from the original prior; it is not a mutable event-stream ingest.

## Modules and principal entry points

| Module | Principal public entries | Purpose |
|---|---|---|
| `contracts` | `Evidence`, `ContextValue`, `Context`, `TaskStep`, `Task`, `HumanFailureEvent`, `Estimate`, `MethodInput`, `SignalSeries`, `canonical_digest` | Portable records and identities |
| `qualitative` | `DeviationRule`, `Finding`, `analyze_task`, `ReviewItem`, `Review` | Configurable deviations and structured reviews |
| `assessment` | `ModelSpec`, `AssessmentCase`, `AssessmentEngine` | Case orchestration and plugin binding |
| `probability` | `BetaPrior`, `sample_estimate`, `demand_frequency`, `interval_probability`, independent union/intersection | Counts, uncertainty and units |
| `methods` | `MethodRegistry`, `declared_estimator`, `cognitive_chain`, `scenario_mixture`, `spar_h_probability`, `heart_probability` | Explicit alternative estimators |
| `dependency` | `conditional_dependency`, `joint_two_failures`, `apply_recovery`, `series_response_failure` | Conditional dependencies and recovery |
| `timing` | `LognormalTime`, `WeibullTime`, `KaplanMeierTime`, `fit_weibull_censored`, `CensoredRegression`, `apply_deadline`, `response_bins`, `first_threshold_crossing` | Completion and censoring |
| `simulation` | `ActionOutcome`, `simulate_task`, `simulate_response` | Task/resource episodes and timelines |
| `bayes` | `DiscreteNode`, `BayesianNetwork` | Small exact conditional inference |
| `fault_tree` | `Event`, `Gate`, `fault_probability`, `fault_probability_joint`, `minimal_cut_sets`, `birnbaum_importance` | Static Boolean reliability |
| `event_tree` | `Branch`, `event_tree`, `protection_partition`, `individual_risk_rate`, `fn_curve` | Conditional path and risk ledger |
| `barriers` | `Barrier`, `lopa_screen` | Independent-layer screening |
| `registers` | `hazop_rows`, `FailureMode`, `RiskMatrix` | HAZOP/FMECA and ordinal handoff |
| `workflow` | `Transition`, `WorkflowNet` | Bounded reachability and deadlocks |
| `attention` | `allocate_attention` | Constrained attention/resource allocation |
| `safety_case` | `Claim`, `SafetyCase` | Evidence changes and impacted claims |
| `monitoring` | `AlarmPolicy`, `alarm_burden` | Causal alarm context |
| `thermo` | `CoolPropState`, `inventory_mass_residual`, `energy_residual` | SI properties and accounting |
| `uncertainty` | `Distribution`, `sample_inputs`, `propagate`, `sobol_sensitivity` | Joint sampling and sensitivity |
| `datasets` | HITL, COG, six UCI readers and `tep_rdata` | Source-aware data loading |
| `studies` | `group_holdout`, `cluster_bootstrap_rate`, `probability_metrics`, `grouped_logistic` | Empirical research checks |
| `adapters` | PRISM, DynaSense, station, monitoring, SAGA, LH2 observations, PSA and QSafety adapters | External object boundaries |

## FTA and ETA example

```python
from human_reliability.fault_tree import Event, Gate, fault_probability

a, b, c = Event("a"), Event("shared-human-event"), Event("c")
tree = Gate("OR", (Gate("AND", (a, b)), Gate("AND", (b, c))))
value = fault_probability(tree, {"a": 0.1, "shared-human-event": 0.2, "c": 0.3})
# value is 0.2 * (0.1 + 0.3 - 0.1 * 0.3), not a sum of independent cut sets.
```

Use a complete joint distribution when events are dependent. Static NOT and voting
are supported; dynamic order must be modeled using timelines or workflow states.

## Custom time models

Implement `cdf(time_s) -> float` and `sample(size, rng) -> ndarray`. The CDF must
describe completion under the same conditioning as the probability estimate. The
sample generator must produce finite nonnegative times. Nonparametric tails may be
unidentified. `simulate_task` calls `.sample`; `apply_deadline` and `response_bins`
call `.cdf`. Applications can therefore keep an existing survival or simulator model.

## Serialization and CLI

`model_dump_json` and `model_validate_json` preserve versioned contracts. Use
`canonical_digest` for source identities. Numeric arrays returned by sampling and
external adapters may require `.tolist()` for application JSON serialization.
Do not pickle untrusted models.

```console
human-reliability doctor
human-reliability schema
human-reliability template input.json
human-reliability run input.json --out output.json
```

The schema command prints the complete input schema. Template creation refuses to
overwrite an existing file. A run writes its requested output destination and
records the input digest. Invalid inputs raise explanatory exceptions; unavailable
results are not changed to zero.
