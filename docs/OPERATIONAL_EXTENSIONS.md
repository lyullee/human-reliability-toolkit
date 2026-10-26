# Operational modeling and research extensions

Version 0.3.0 connects task execution, causal models, observed opportunities,
conditional risk and design comparisons. The original assessment, timing, FTA,
ETA and adapter APIs remain available. This guide describes the twelve extension
areas, their parameters and their computational limits.

The runnable examples use original authored scenarios. The example that selects
SACADA data retains the real released counts and an explicit prior, but its plant
transfer, exposure, physical context and interventions remain illustrative.
The numeric catalog retains its seven sources and 1,334 records; adding modeling
features does not create new field observations.

## Start from a typed template

Install core functionality with `python -m pip install -e .`. Add the event
scheduler with `python -m pip install -e ".[dynamics]"`. For all development and
research checks:

```console
python -m pip install -e ".[data,curation,learning,survival,thermo,sensitivity,bdd,dynamics,dev]"
human-reliability risk-template risk.json
human-reliability risk-run risk.json --out risk-result.json
human-reliability workflow-template method.json
human-reliability workflow-run method.json --out method-result.json
human-reliability coupled-template operations.json
human-reliability coupled-run operations.json --out operations-result.json
python examples/operational_research.py
```

Template commands refuse to overwrite an existing file. Edit the generated JSON
or use the Python contracts. `risk-schema`, `workflow-schema` and `coupled-schema`
print structural JSON schemas, including conditional method-parameter schemas.
Semantic unit, identity, scope and dependence checks also run during evaluation.
Python constructors use strict types, including
tuples for tuple fields. JSON interchange uses `Model.model_validate_json(text)`
and `model.model_dump_json(indent=2)`.

The templates intentionally contain assumptions. The coupled template uses
declared linear state rates; it is not a validated pressure-vessel model. The
Python example additionally demonstrates a process update that depends on the
previous valve action and therefore changes the next available observation.

## Module map

| Requirement | Module | Main interfaces |
|---|---|---|
| G01 Actions and error variants | `actions` | `ProcessState`, `StatePredicate`, `EquipmentCapability`, `ExecutableAction`, `execute_action`, `error_variants`, `reordered_plan` |
| G02 Causal and barrier model | `causal` | `CausalLeaf`, `CausalGate`, `CausalGraph`, `JointState`, `evaluate_causal_graph` |
| G03 Risk orchestration | `risk` | `RiskCase`, `RiskScenario`, `InitiatingFrequency`, `RiskBranch`, `RiskEngine`, `ConsequenceRegistry` |
| G05 Communication and authorization | `communication` | `MessageLedger`, `Handover`, `WorkPermit`, `WorkControl` |
| G06 Operational evidence | `observations` | `ObservationWindow`, `TaskOpportunity`, `ObservedAction`, `RecoveryAttempt`, `ObservationLedger` |
| G07 Intervention comparison | `interventions` | `CaseChange`, `Intervention`, `apply_intervention`, `compare_intervention`, `paired_model_comparison`, `risk_importance` |
| G04 Coupled dynamics | `dynamics` | `ProcessBackend`, `StateProcess`, `PolicyTask`, `ProcessObservation`, `RuntimeJob`, `CoupledCase`, `run_coupled_episode` |
| G08 Progress and deadlines | `verification` | `compile_task_net`, `verify_progress`, `TimedTransition`, `DiscreteTimedNet` |
| G09 Information and diagnosis | `cognition` | `Cue`, `CueStore`, `BeliefState`, `PollChannel`, `monitor_cues` |
| G10 Sparse data and elicitation | `calibration` | `BinomialGroup`, `BetaHyperPoint`, `fit_partial_pooling`, held-out/predictive scores and expert functions |
| G11 Procedure and assurance lifecycle | `assurance` | `TraceStep`, `procedure_conformance`, `import_task_csv`, `Assumption`, `ArtifactFingerprint`, `AssuranceLifecycle` |
| G12 Reference workflows | `method_workflows` | `MethodWorkflowCase`, `run_method_workflow`, `workflow_estimator` |

## G01 Execute the intended or an erroneous command

A `ProcessState` maps stable keys to `StateValue(value, unit)`. `None` is unknown,
not zero. A predicate compares one key using `eq`, `ne`, `lt`, `le`, `gt` or `ge`.
Ordered comparisons require numeric values. Units and scalar types must match;
the action layer does not silently convert bar to Pa or text to a number.

`EquipmentCapability` binds a target and verb to one state key, an operation
(`set` or `add`), a unit and optional physical limits or allowed values. Physical
limits describe what the equipment can do. Safety constraints belong in the
action's `safety_conditions` or enabled `permissives`.

```python
# executable
from human_reliability.actions import (
    Command, EquipmentCapability, ExecutableAction, Permissive,
    ProcessState, StatePredicate, StateValue, execute_action,
)
state = ProcessState(revision="example", values={
    "pressure": StateValue(value=4e5, unit="Pa"),
    "valve.position": StateValue(value=0.0),
})
condition = StatePredicate(key="pressure", operator="le", value=2e5, unit="Pa")
capability = EquipmentCapability(
    target="valve", verb="position", state_key="valve.position",
    minimum=0.0, maximum=1.0,
)
action = ExecutableAction(
    id="open", command=Command(target="valve", verb="position", value=1.0),
    safety_conditions=(condition,), evidence="Authored example",
)
attempt = execute_action(state, action, (capability,))
assert attempt.status == "unsafe_attempt"
protected = action.model_copy(update={"permissives": (
    Permissive(id="pressure", condition=condition, evidence="Declared design"),
)})
blocked = execute_action(state, protected, (capability,))
assert blocked.status == "blocked"
assert blocked.state_after.values["valve.position"].value == 0.0
```

The result retains intended/realized commands, before/after states, condition
results and interlock results. `omitted=True` records no realized command. A false
safety condition permits an explicitly modeled unsafe attempt. An enabled false
or unknown permissive blocks the command. Unknown safety information defaults to
`unknown_withheld`; `unknown_policy="attempt"` permits an explicit unknown-risk
attempt but does not bypass an enabled permissive.

`error_variants` accepts reviewed alternative targets, magnitudes, delays and
repetition counts. It checks equipment support and limits output with
`maximum_variants`. It supplies no probability for those variants. Negative delays
are rejected; an early action is represented by a reviewed changed task order or
release time. `reordered_plan` reports precedence violations without modifying the
nominal task DAG. Physical dynamics require a process backend.

## G02 Construct a causal event model

Leaves have kinds `cause`, `latent`, `action`, `detection_failure`,
`recovery_failure` or `barrier_failure`. Each supplies exactly one reviewed
probability or `estimate_id`, plus evidence and conditioning. Every leaf must use
the graph's conditioning population. Gates reference node IDs and support the
existing AND/OR/NOT/VOTE logic. Repeated references share the same event identity.
Unknown references, cycles and unreachable nodes are rejected.

Multiple primitive events require `independence_evidence`, or a declared
`joint_states` distribution. Overlapping `dependency_groups` withhold independent
calculation. A supplied joint model must agree with the declared marginals;
missing joint states have zero mass under the existing joint-state API. Do not
insert a conditional HEP as if it were a marginal probability in that distribution.

`scope_group` identifies the same underlying failure scope. Combining an estimate
that already includes recovery with another recovery-failure leaf in that scope
is rejected. Alternative causes belong in logic branches. Within-mechanism
modifiers are restricted to a cause leaf and need their own evidence and selected
normalization. Changing marginals alone cannot define a modified joint model.

A latent-condition branch can produce a hazard during a correct operation;
there need not be an operator-error leaf. `maximum_depth` and
`maximum_expanded_nodes` bound compilation. The existing FTA backend additionally
limits state enumeration; select its BDD backend where appropriate.

## G03 Evaluate a complete risk case

`RiskCase` accepts a native `AssessmentCase`, supplied `Estimate` objects, causal
graphs, contextual scenarios and consequence providers. Supplied estimates must
reference available `Evidence` records. Reused evidence identities must agree.
Graph IDs and estimate IDs cannot collide.

```python
# executable
from importlib.resources import files
from human_reliability.risk import RiskCase, RiskEngine
case = RiskCase.model_validate_json(
    files("human_reliability.data").joinpath("risk_case.json").read_text(encoding="utf-8")
)
result = RiskEngine().assess(case)
assert abs(result["annual_frequency_per_year"] - 0.2) < 1e-12
assert abs(result["individual_risk_rate_per_year"] - 0.01) < 1e-12
```

This example's numbers are authored assumptions. Its ten demands/year, 0.02
failure probability, 0.1 conditional harm and 0.5 presence yield 0.2 failures/year
and 0.01/year individual risk rate. This is an expected rate, not necessarily the
probability of at least one event in a year.

An initiator uses either an annual rate or demands/year times a referenced event
probability. Demand exposure must match `opportunity_definitions`; native event
definitions are imported from an attached assessment. A missing exposure remains
`None`, with an unresolved reason. It never becomes zero.

`exclusive_contexts` requires contextual weights summing to one; use these weights
when splitting the same exposure population. `distinct_initiators` requires unit
weights and declared partition evidence for separately counted initiating events.
Do not apply a contextual fraction twice to already stratified exposure.

Each `RiskBranch` supplies a point probability or an event reference. References
require exact conditioning agreement. Sibling branches must close to one. A
`complement` flag constructs the opposite outcome; it does not establish an
independence assumption. Every terminal path references a consequence, including
no-harm outcomes.

Fixed consequences use `ConsequenceMetrics`. Harm is either `includes_occupancy`
or `conditional_on_presence`, in which case an occupancy value is required. The
former rejects another occupancy multiplier. Fatality distributions are separate,
normalized conditional distributions that must already cover the modeled exposed
population. Expected loss requires a currency; unlike currencies cannot be added.

External providers register a local callable returning `ConsequenceMetrics` with
an explicit version/code pin and evidence. Their contract is
`provider(parameters, context)`. Context contains the scenario, path, estimates
and graph results. Registration authorizes no external service call. Providers
may run an already installed physical solver within its documented domain.

`dynasense_consequence_provider` connects the pinned DynaSense solver using
physical completion time, occupancy and an exact baseline fingerprint.
`risk_scenario_branches` exports a complete partition through the existing PRISM
`EventBranch` factory. The older human-initiator payload still needs a receiving
PRISM initiator-contract extension; this release does not relabel a human event
as an equipment literature event. See [Integration](INTEGRATION.md).

Results retain source estimates, evidence, graph results, provider provenance and
a path ledger. Known frequency can remain available when a consequence provider
is unavailable, while harm stays withheld. F-N and loss outputs remain `None`
when their specific required inputs are absent.

## G05 Model communication and work-control conditions

`Message` identifies sender, receiver, a typed command, send/expiry times and
evidence. `MessageLedger` records chronological events:

1. `send` allocates a new immutable identity.
2. `receive` distinguishes delivery to the intended recipient from another role.
3. `interpret` compares the receiver's understood command with the sent command.
4. `confirm` checks the sender's confirmation of a matching readback.
5. `authorized_command` returns a command only after confirmation, for the correct
   receiver, within the validity window, without reading a future event.

Receipt is not understanding. Reinterpretation invalidates an earlier confirmation.
Duplicate IDs/receipts are rejected; model a deliberate repeated message with a
new identity. A wrong recipient or expired message does not authorize action.

`Handover` checks receiver, procedure version, state revision, content fingerprint,
acknowledged content and validity. Compute `facts_digest` from
`canonical_digest(state.model_dump(mode="json")["values"])`. Changes require
renewed review rather than automatic acceptance of the old snapshot.

`WorkPermit` declares area, activity, validity, predicates, individual lock owners
and required restorations. `WorkControl` manages issue, lock, authorization,
suspension, renewal, individual unlock, restoration confirmation and closeout.
Unknown conditions or missing personal locks prevent authorization. Each owner
removes their own recorded lock; removing a lock suspends active authorization.
Conflicting active activities in the same area are checked against the supplied
incompatibility pairs. Renewal requires a new revision and another authorization;
changed work scope requires a separate permit. Closeout requires all personal
locks released and every specified restoration confirmed. These are modeled
records, not commands to real plant equipment or an operational permit service.

## G06 Build operational evidence without inventing denominators

`ObservationWindow` supplies source, clock, interval, evidence and optional context.
`TaskOpportunity` supplies source-event identity, event/task meaning, interval,
domain, denominator definition, initial error, final failure and follow-up status.
`ObservedAction` and `RecoveryAttempt` attach observed events to that opportunity.
Group IDs are optional pseudonymous source metadata; the importer does not infer
missing crew/episode identities.

An `ObservationLedger` rejects repeated source opportunities, unknown links,
observations outside their windows, incompatible definitions and successful
recovery after the defined deadline. Count summaries reject overlapping selected
windows. Specify `window_ids` when the ledger contains multiple observation
populations. Exact, typed context filters select compatible records.

`snapshot(event_id, estimand="initial")` counts initial errors.
`estimand="final"` counts final failures. A fully observed successful recovery can
remove an initial error from the final-failure count. Incomplete outcomes stay in
`missing_ids`; the complete-case denominator, eligible demands and missingness
flags remain separate. Recording a recovery is not an additional task demand.

`posterior` requires an explicit `BetaPrior`, an independence review and, when
outcomes are missing, a missingness/selection review. Its interval is conditional
on those statistical assumptions. `catalog_record` exports a compatible count
record to a user-owned catalog; source rights must still be supplied separately.

`annual_demand_exposure` counts all eligible observed demands, including those
with unknown human outcomes, and annualizes their nonoverlapping observation time.
It requires coverage and stationarity reviews and one source/clock population.
Conditional exposure additionally requires windows dedicated to that context;
filtering events alone cannot supply time-at-risk for a condition. The returned
annualized estimate is not an observed annual frequency series.

The evidence schema now supports `reported_observed_probability`: an observational
estimate with no exact counts, an observational origin and explicit limitations.
It binds as a research estimate, cannot receive invented Bernoulli counts and
cannot be updated with a count prior. Published bounds remain reported bounds,
not a fitted distribution. The bundled catalog currently contains zero records of
this new kind. Do not recover an exact denominator from a rounded published HEP.

Field-source acquisition remains source-specific. Follow underlying reports,
opportunity definitions and reuse terms before importing numeric evidence. Source
tables and participant logs have not been added to the release. Keep private
operational data in ignored raw/processed storage and minimize personal identifiers.

## G07 Compare interventions without rewriting evidence

`Intervention` identifies a version, rationale, evidence and concrete `CaseChange`
objects. A change supplies a tuple path through existing case fields, its value
and unit. For example, `("estimates", "0", "probability")` changes the first
supplied estimate. Numeric list indices are explicit. Unknown or overlapping
paths are rejected; the original case is not mutated.

The alternative receives an `assumed` intervention evidence record and its
baseline fingerprint. Overridden estimate probabilities become
`intervention_override`/`assumed`. Their old fitted uncertainty is removed and the
original estimate is retained in the trace. An assumed improvement must not keep
an empirical label or an inconsistent old posterior. Changed graph-leaf
probabilities cite the intervention evidence. Observed count fields cannot be
rewritten as an intervention. Changing exposure or initiator populations requires
`exposure_change_review`.

`compare_intervention` returns complete baseline/alternative ledgers and absolute
and relative differences in annual frequency, individual risk and expected loss.
A zero baseline has no defined relative reduction. Withheld inputs remain withheld.
An assumed training or design effect remains a modeled hypothesis, even if the
resulting reduction is large.

`paired_model_comparison` draws the same input samples for two callables, with a
seed and optional latent correlation. It reports paired reduction quantiles and
Monte Carlo standard error separately. Pairing reduces numerical noise; it does
not identify a real-world causal effect. `risk_importance` adds FV, RAW and RRW
to Birnbaum importance for independent primitive events in monotone static logic.
Zero-denominator worth measures are `None`; dependent or chronological models
need a separately justified importance definition.

## G04 Couple task execution to a process

The `dynamics` extra installs SimPy. Existing `simulate_task` retains its original
chronological replay behavior. Use `run_coupled_episode` for physical feedback
before the next decision. The two functions intentionally have different contracts.

`bind_task_execution` links the existing `Task` IDs, procedure version, actors,
predecessors and deadlines to executable actions and supplied duration values.
Every textual precondition/latent-safety requirement must have a reviewed
`StatePredicate` binding; an unresolved name is rejected. The predicate is true
when the required safe condition holds, including a safe-state condition for a
named latent hazard. Nominal targets must match and executable action IDs remain
distinct. Optional per-step job parameters add priorities, eligibility and reviewed
failure/retry assumptions without replacing the native task identity/order.

`ProcessBackend` has four methods:

| Method | Meaning |
|---|---|
| `advance_to(time_s)` | Advance the existing physical model to the common event clock |
| `snapshot()` | Return the analyst's physical state for action/interlock evaluation |
| `observe(actor, time_s)` | Return only information available to that role at that time |
| `apply(execution, time_s)` | Apply an atomic completed command to the synchronized physical model |

`StateProcess` is a lightweight implementation with an optional
`advance(state, elapsed_s, target_time_s)` callback. The callback returns a
`ProcessState`. Its visibility allowlist maps roles to observable keys; an
unconfigured role receives no state channels. Observations carry the scheduler's
`observed_at_s`. Real process models implement the same protocol or provide an
adapter; retain their solver, units, applicable state range and conservation checks.
CoolProp remains available through the existing thermodynamic module when needed.

Each `RuntimeJob` identifies an action, eligible actors, predecessor jobs, release
time, duration, priority, deadline and bounded attempt policy. Capacity is configured
per actor. Smaller priority numbers take precedence. A higher-priority eligible
job may interrupt another job; the interrupted job resumes its remaining work.
Selection among eligible actors defaults to the least-loaded actor, with a stable
tie order. An optional selector can implement a reviewed allocation rule using the
provided role views and resource loads.

Policies use `policy(public_task, observation, own_history, rng)` and return a
typed `Command` or `None` for a deliberate omission. `PolicyTask` carries planned
task information, without injected-error probability, hidden error command or
realized failure labels. History contains that role's perceived command choices,
not another role's actions or an injected hidden deviation. Analyst records retain
the actual command and before/after states separately.

`error_probability` is an optional injected-error model, requiring
`error_evidence` when nonzero. On an error it uses `error_command`, or omission
when that command is absent. These are supplied assumptions, not automatically
calibrated human behavior. Duration may use a `duration_provider` callback and
the existing time models. Physical commands apply at completion, not at the start
of interrupted work; model continuous manipulation separately if required.

The default is one attempt. More attempts require `retry_mode="repeat"` or
`"policy"`. Repeat schedules the declared attempts regardless of hidden success.
Policy retry requires `retry_decider(public_task, observation, own_history,
attempt_number, rng)` returning a boolean. Thus a hidden wrong action does not
automatically produce an all-knowing corrective retry. The fixed JSON runner
supports bounded repetition; custom retry policies use Python. Retries and
interruption decisions are visible in the audit. `reconsider_on_resume` explicitly
selects a fresh decision on resumption rather than retaining the prior choice.

`requires_success` is an explicit system-level prerequisite gate. Without it,
failed prior attempts remain possible and the next action's physical conditions
and permissives determine what happens. Do not use this gate as a substitute for
an operator's uncertain belief that an earlier task succeeded.

The scheduler processes completions exactly at the horizon. Later work is listed
as `unfinished_jobs` with `incomplete_horizon`. Event-budget exhaustion raises an
error rather than returning a success. Same-time ordering follows the deterministic
SimPy event order; validate ordering/refinement for a coupled physical application.
The supplied linear-rate JSON model is useful for contract tests, not facility QRA.

## G08 Verify completion and discrete deadlines

`compile_task_net` converts the native task DAG into an untimed net. Separate
tokens for each predecessor edge preserve fan-out. It emits distinct
`attempted:<step>` and `success:<step>` places and can add reviewed named error
alternatives. An omitted attempt may terminate a procedure while failing its
safety goal. Use the appropriate goal and unsafe predicates; attempted completion
alone does not prove successful operation. Physical predicates are evaluated by
the action/process model, not inferred from old textual task preconditions.

`verify_progress` explores the finite supplied net. Goals terminate an episode.
It distinguishes an unreachable goal, a possible completion, nonterminal deadlock
and a reachable nonterminating cycle. All-path completion assumes no fairness:
an enabled exit does not exclude an infinite loop. A state limit returns
`incomplete_state_limit`. The older `WorkflowNet.verify` remains a safety/deadlock
query and is not changed into an implicit liveness proof.

`TimedTransition` declares integer duration bounds and optional earliest/latest
start ticks. `DiscreteTimedNet` enumerates serial atomic firings on a declared
`tick_seconds` grid. It checks possible or all-path completion by a deadline,
including zero-time cycles and durations exactly on the deadline. Earliest-start
waiting is explicit in that semantics. It does not enumerate arbitrary idle
strategies or represent general concurrent timed Petri nets. Duration-choice and
state budgets bound exploration. A discretized proof applies to that discretized
model; refine the grid or use a suitable external formal tool for other semantics.

## G09 Represent available information and diagnosis

`Cue` retains measured/available/expiry times, visible roles, its typed observation,
underlying evidence identity and optional likelihoods for each hypothesis.
`CueStore` exposes only currently available, unexpired cues for the requested role.
It rejects repeated observation identities and requires reconciliation of competing
same-time cues. New availability is not automatically the newest measured state.

`BeliefState` starts from an explicit normalized prior. Each update requires a new,
visible, known cue, likelihoods for every hypothesis and a conditional-independence
review. Impossible observations are rejected rather than normalized into a
plausible answer. A posterior is a declared diagnostic model, not an inferred
human mental state. `choose` needs one action per hypothesis and a confidence
threshold; ties or insufficient confidence request more information.

`monitor_cues` combines `PollChannel` intervals and dwell times with a single
observer's capacity. Polls queue, so attention is not unlimited. An
`adaptive_interval(channel, visible_cue, time_s)` callback can change sampling
based on the observed distance to a boundary, for example. It must return a
positive interval. Keep missing cues explicit. An alarm missed in a sampling
episode is not by itself evidence for a particular cognitive cause or a universal
complacency multiplier.

## G10 Estimate sparse probabilities and preserve elicitation origin

`fit_partial_pooling` uses compatible `BinomialGroup` objects and an explicitly
supplied finite hyperprior grid of `BetaHyperPoint(alpha, beta, prior_weight)`.
Conditional on one grid point, each group's probability has a beta prior and the
observed counts have a binomial likelihood. The grid's posterior weight is
proportional to its prior weight times the product of beta-binomial marginal
likelihoods. Group posteriors are weighted beta mixtures.

```python
# executable
from human_reliability.calibration import BinomialGroup, BetaHyperPoint, fit_partial_pooling
groups = (
    BinomialGroup(id="small", group_id="small", failures=0, opportunities=2,
        opportunity_definition="One authored demand", domain="authored", evidence="Authored fixture"),
    BinomialGroup(id="larger", group_id="larger", failures=3, opportunities=40,
        opportunity_definition="One authored demand", domain="authored", evidence="Authored fixture"),
)
posterior = fit_partial_pooling(
    groups, (BetaHyperPoint(alpha=0.5, beta=5.0, prior_weight=1.0),
             BetaHyperPoint(alpha=1.0, beta=20.0, prior_weight=1.0)),
    exchangeability_review="Authored compatible groups; no real operator inference",
)
summary = posterior.summary("small")
assert 0 < summary["lower"] < summary["posterior_mean"] < summary["upper"] < 1
```

The grid is part of the model, not a continuous-hyperprior approximation with an
automatic convergence guarantee. Include defensible prior support and compare
alternative grids using `transfer_sensitivity`. Posterior intervals use the
mixture CDF; draws and predictive count checks retain seeds. A one-point grid
reduces to the independently checked beta-conjugate case. NumPy and SciPy provide
the numerical backend; an additional MCMC package is not required.

Groups must have distinct observation and grouping identities, compatible domains
and denominators, and an exchangeability review. A shared context code is not a
recovered crew identity. Released SACADA aggregates do not support inventing
operator-level random effects. `heldout_binomial_scores` checks disjoint train/test
identities and reports count-weighted Brier/log scores and calibration rows.
An impossible zero/one prediction is flagged without writing infinity into JSON.
`posterior_predictive_check` is an internal replicate check, not independent
holdout validation or proof of plant transfer.

`ExpertJudgment` records three explicit probability quantiles. `fit_elicited_beta`
fits a beta distribution with a selected maximum quantile-error tolerance and
reports its fit error. It does not pretend every elicited distribution is beta.
`expert_calibration_weights` scores predictions on independently known binary seed
items, using an explicit temperature. `sample_expert_mixture` samples fitted
judgments with declared normalized weights. These remain elicited evidence, not
observed Bernoulli denominators; good seed scores do not establish target-domain
calibration.

## G11 Check procedures and maintain qualification

`TraceStep` records step, actor, actual target, start/completion times, procedure
version, result and evidence. `procedure_conformance` checks unknown steps,
unapproved repeats, mismatched actors/targets, stale versions, predecessor timing
and undemonstrated completion. Configure retry allowances and which steps require
successful predecessors. Missing steps become omissions only with a declared
complete observation window; otherwise they are `not_observed`. Restoration steps
remain identifiable. These are trace comparisons, not inference about intent.

`import_task_csv` reads reviewed structured columns: id, action, kind, target,
actor, cue, completion and predecessors. A column map, predecessor separator and
equipment aliases are configurable. JSON import already uses the native `Task`
contract. Neither importer silently constructs verified procedures from prose.

`ArtifactFingerprint.of` fingerprints configuration meaning. `Assumption` includes
evidence, review status and optional expiry. `AssuranceLifecycle` validates a
dependency DAG and compares current artifacts/assumptions at an explicit review
date. Changes, deletions, expired/unapproved assumptions and `IncidentLesson`
records propagate to dependent artifacts and existing `SafetyCase` claims.
Refuted assumptions invalidate the modeled qualification. New identities request
scope review. Content hashes detect change; they cannot decide semantic validity.

`baseline_json` and `AssuranceLifecycle.from_json` preserve artifacts, assumptions,
claims and evidence versions for a later session. Lessons retain findings and
recommendations separately. No method automatically reapproves a safety argument.

## G12 Run reviewed reference workflows

`MethodWorkflowCase` combines a method, defined event, applicability/scope review,
method parameters and optional conditional recovery/dependence adjustments.
`run_method_workflow` returns an `EvidenceBinding`; attach its evidence to a native
assessment or risk case. `workflow_estimator` integrates the case with the existing
registry. `AssessmentEngine` also accepts `method="method_workflow"` with one
`workflow` parameter and the exact resulting evidence identities.

| Method | Parameters and implemented boundary |
|---|---|
| `spar_h_profile` | One or two unique stages in diagnosis/action order, all eight reviewed levels, stage conditioning and explicit permission for unknown levels. Later-stage failure is conditional on earlier-stage success. Available-time scope already includes timing. |
| `heart_profile` | Generic task code, EPC record IDs with assessed proportions, and explicit `base_includes`. Repeated or alternative levels of one EPC cannot be combined. |
| `idheas_function` | Function, all three base-family selections, modifier record IDs, optional recovery divisor/evidence and `base_includes`. Sources must match function/family; placeholders and duplicate alternative modifier levels are rejected. This remains single-function arithmetic, not the complete official HFE/timing system. |
| `cream_range` | A reviewed control-mode interval, an explicit selected point and `base_includes`. The workflow does not infer a control mode or select a midpoint. It is not the full extended CREAM/CPC system. |

An absent IDHEAS base selection is an explicit inactive influence. The function
floor applies only when all three base influences are inactive. Modifier weights
combine through the existing additive-excess kernel, not by multiplying them.
Published placeholder values do not become calibrated inputs. Numerical source
reuse must be cleared in the catalog.

Recovery uses the conditional failure-to-recover probability with separate
evidence. A dependence adjustment explicitly identifies the preceding failure,
level and final conditioning. Its output is conditional, not an unconditional
HEP to multiply again without a suitable model. The final `included_effects`
review must exactly match the workflow's effects; existing timing/recovery cannot
be applied twice. Native event scope must be covered. Unknown reference levels
retain a research status. Named calculations do not establish an official-method
system certification or field qualification.

## Reproduce the extension checks

```console
python examples/operational_research.py
human-reliability risk-run artifacts/operational_research/risk_case.json --out artifacts/risk-replay.json
python scripts/run_verification.py --integrations
python scripts/inventory_environment.py
python scripts/build_release.py
```

The integration option requires the pinned existing-project targets described in
[Integration](INTEGRATION.md). CI checks software without retrieving participant
datasets. [Extension validation](EXTENSION_VALIDATION.md) maps acceptance cases to
tests, examples and limitations. [Research handoff](RESEARCH_HANDOFF.md) describes
reproduction and release records. The public requirement status is
`research/extension_implementation.json`.

Original code, comments and scenarios are independently authored. SimPy is an
optional MIT dependency; numerical source records keep their separate notices.
No source publications, original worksheets, participant records or restricted
field tables are included. See [Data licenses](../DATA_LICENSES.md) and
[Reuse policy](LICENSING.md).
