# Field task opportunities: collection and HEP validation

Version 0.5 supplies original blank forms, a strict offline importer and a
denominator-aware evaluation API. It enables a prospective site study; it does
not supply a calibrated chemical-plant HEP. The separate public aggregate study
and its unfavorable temporal result are documented in
[DENOMINATOR_VALIDATION.md](DENOMINATOR_VALIDATION.md).

## Start a local study

```console
human-reliability collection-template data/raw/site_study
human-reliability collection-audit data/raw/site_study --out data/processed/site_audit.json
human-reliability collection-validate data/raw/site_study data/raw/site_study/validation-plan.json --out data/processed/site_validation.json
```

The first command creates **blank** UTF-8 CSV forms and JSON schemas. It refuses
an existing directory. Configure `protocol.json` before collecting observations;
its empty required fields deliberately fail validation. The second and third
commands run after the forms have been populated. Audit exits with code 2 when
coverage or register reconciliation is blocked. Invalid records fail with the
file and line number. An unreconciled denominator prevents HEP estimation and
prediction scoring.

The same blank forms are available in [templates/field_collection](../templates/field_collection).
They are plain interchange files that can be entered using a text editor, a
controlled form application or CSV-capable office software. Preserve field names,
column order and decimal seconds when exporting. There are no hidden formulas,
macros, remote connections or prefilled real observations.

`data/raw/`, `data/processed/` and `field_records/` are ignored by this repository.
An ignored directory helps avoid accidental commits; it does not implement access
control, encryption or an institutional retention policy. Keep study records in
the site's authorized storage and back them up according to its requirements.

## Define the event before looking at outcomes

One protocol represents one task, event definition, population, conditioning and
opportunity unit. Use separate bundles when these meanings change. Suitable
examples of opportunity units include one independently triggered valve-position
verification or one scheduled permit handover. Do not treat each sensor sample,
action, retry or report as a fresh human task opportunity.

Write an observable criterion for the initial error and final human failure.
Specify the cue, required action, acceptable tolerance, omission rule, completion
deadline, permitted recovery and evidence needed to establish success. Record
equipment-only faults as such in the supporting evidence. If human attribution
is unresolved, the human endpoint is unknown. A process defect does not itself
establish a human failure. A justified safe stop or a demand withdrawn before its
trigger must be handled by a frozen rule, rather than reclassified after seeing
an unfavorable outcome.

For omission detection, build the task-demand register from an independent
schedule, authorized work order, alarm/trigger register or other documented
source. An action log alone cannot enumerate tasks that were never attempted.
The protocol's `registry_review` must describe the comparison source and who
reconciled it. The software verifies consistency with the supplied expected
counts; it cannot prove that a site supplied every real-world demand.

Freeze a versioned protocol before the first registered demand. Use one clock
with a documented origin and unit; store nonnegative elapsed seconds, including
the protocol and model freeze times. Preserve the conversion from original
timestamps, timezone and daylight-saving treatment in supporting records.
`deadline_s` is an absolute coordinate on that same relative clock, not a duration.
Store supporting evidence by stable reference; keep names, badge numbers,
medical details and sensitive plant documents outside these exchange tables.

## File and field dictionary

The generated `protocol.schema.json` and `tables.schema.json` are authoritative
machine schemas. Extra or reordered CSV columns are rejected to expose accidental
mapping changes. Strings are identifiers/references, numbers must be finite,
booleans are exactly `true` or `false`. Only nullable fields accept an empty cell
as unknown. `0`, `False`, `NA`, spaces and `yes` are not Boolean substitutes.

### protocol.json

| Fields | Meaning |
|---|---|
| `id`, `version`, `source_id` | Immutable study/protocol and source identities |
| `domain`, `task_id`, `event_id` | Population and modeled event; use IDs compatible with receiving task/risk models |
| `failure_definition`, `opportunity_definition`, `conditioning` | Explicit endpoint, denominator and scope; these are not inferred from a task title |
| `setting` | `natural_field`, `simulator`, `induced` or `synthetic`; never relabel drills as field observations |
| `sampling` | Implemented design is `window_census`: enumerate every eligible demand in declared windows |
| `clock_id`, `clock_origin_and_unit`, `frozen_at_s` | Common clock identity, original conversion record and pre-observation freeze coordinate |
| `coverage_review`, `registry_review` | Evidence of complete observation coverage and independent demand reconciliation |
| `adjudication_rule` | Frozen error/attribution/recovery criteria, training and blinded review process |
| `collection_authorization` | Internal permission reference for the observation study |
| `data_license`, `license_evidence` | Data-owner terms and evidence; starter defaults to `internal_only` |
| `public_release_authorization` | Optional separate release authorization reference, blank by default |

The release-authorization flag merely reports whether a reference was supplied.
It does not verify its validity or override the data owner's terms. No command
uploads field data or publishes user records.

### windows.csv

| Field | Meaning |
|---|---|
| `id` | Unique census-window identity |
| `start_s`, `end_s` | Positive-duration, nonoverlapping coverage on the protocol clock |
| `coverage_complete` | Explicit assertion that the defined census coverage was achieved |
| `expected_register_rows` | Integer count independently reconciled to the source register, including audited exclusions |
| `reconciliation_evidence` | Reference to the reconciliation record, observer coverage and gaps |

Split windows around observer absence. Do not mark partial observation as complete.
Unequal-probability sampling, convenience samples without a complete window census
and weighting designs require a separate statistical design; this importer does
not silently apply a census estimator to them.

### demands.csv

| Field | Meaning |
|---|---|
| `id`, `source_event_id` | Stable local demand and independent source-register event identities |
| `window_id` | Existing census window |
| `start_s`, `end_s`, `deadline_s` | Trigger, end of documented observation/follow-up and optional failure deadline; deadline must lie inside follow-up |
| `group_id` | Pseudonymous dependence cluster, for example crew-day; define grouping before analysis |
| `disposition` | `eligible`, `withdrawn_before_trigger` or `duplicate_record` |
| `disposition_evidence` | Source trigger or independently reviewed exclusion record |
| `duplicate_of` | For duplicates only: retained eligible demand with the same source event, window, timing, deadline and group |
| `withdrawn_at_s` | For withdrawals only: known time strictly before the trigger |
| `context`, `context_evidence` | JSON object of typed conditions and its provenance reference; use `{}` when none are recorded |

All eligible demands remain in the denominator, including unattempted tasks and
tasks with unknown outcomes. Cancellation after a trigger does not meet the
pretrigger exclusion rule. A recovery/retry belongs to the same demand. Duplicate
rows remain auditable but do not add exposure. Expected register rows count these
administrative rows; eligible opportunity counts do not.

Use `context` for pseudonymous site/equipment, procedure version, shift, task
complexity, work-order type and prespecified environmental/process conditions.
For example, a CSV cell can contain the JSON object
`{"shift":"night","procedure_version":"v3","noise_dBA":78.5}` with a reference
to the observation/instrument and units in `context_evidence`. A CSV writer must
escape its quotes correctly; use `json.dumps` for the cell value. Context values
are scalar integers, finite numbers, strings or booleans, and nonempty context
requires provenance. Keep units and measurement timing in the supporting schema.
Record whether a factor was measured, reported or assessed; do not invent a
numerical HEP multiplier from a factor name. Prospective model predictors must
have been available at forecast issuance; this importer does not time-qualify
arbitrary context measurements. Outcome-derived context is unsuitable as a
pre-outcome predictor. The ledger preserves typed conditions for exact filtering.

### outcomes.csv

| Field | Meaning |
|---|---|
| `demand_id` | One eligible demand; at most one adjudicated result row |
| `initial_error` | Nullable Boolean for the frozen initial human-task error endpoint |
| `final_failure` | Nullable Boolean for the human-task failure endpoint after allowed recovery/deadline |
| `followup_complete` | Must be true for a known final outcome; must be false for unknown final outcome |
| `endpoint_adjudicated` | Human attribution and endpoint criteria resolved; false requires both outcomes unknown |
| `coder_id`, `adjudicator_id` | Distinct pseudonymous identities; supporting independent coding records remain with the study |
| `evidence` | Traceable source observation, review and adjudication references |

A wholly absent outcome row becomes unknown, never a successful task. This
importer disables the older ledger's optional final-outcome inference by refusing
unknown-final/complete-follow-up combinations. An initial error recovered in time
may have `initial_error=true`, `final_failure=false`. A later error can make an
initially correct task fail; do not force the two columns to be equal.

### recoveries.csv and predictions.csv

Recovery fields match the existing `RecoveryAttempt` contract: `id`,
`opportunity_id` (the demand ID), `time_s`, nullable `successful` and `evidence`.
The referenced demand must have an observed initial error. A successful recovery
after the deadline, outside follow-up or alongside a declared final failure is
rejected. Record actual attempts; do not invent a successful recovery merely
because a final result was favorable.

Prediction fields are `demand_id`, `model_id`, `probability` and `issued_s`.
Probabilities must be finite and in [0,1]. Predictions are required for **every**
eligible demand in the selected evaluation windows, including demands whose
outcomes later remain unknown. They must follow the frozen validation plan and
precede each demand trigger. This prevents scoring only easy or already observed
cases. Preserve the original immutable prediction stream and model artifacts;
CSV timestamps alone cannot establish that a researcher did not edit a file.

## Prospective validation procedure

1. Assign a site study owner, data steward, observers and an independent endpoint
   reviewer. Obtain the site's collection authorization, privacy arrangements and
   required participant/organizational consent before observations. Observation
   does not authorize changes to operating procedures or plant controls.
2. Define one event/denominator population. Pilot the forms to find ambiguous
   triggers, recovery and equipment/human distinctions. Train coders on pilot
   cases. Keep pilot data separate from the final evaluation cohort.
3. Freeze protocol, sampling windows, group definition, model specification,
   training membership and intended evaluation periods before the evaluated work.
   Hash and retain a read-only copy. Choose an evaluation period/site/crew not used
   to fit or select the model, and record exclusions before inspecting results.
4. Reconcile every shift/window against the independent source register. Preserve
   withdrawn/duplicate rows and evidence. Record omissions and unknown outcomes.
   If coverage fails, retain the failed audit and withhold a qualified HEP result.
5. Log model predictions before triggers. Blind endpoint coding and adjudication
   to the predictions. Retain the two original ratings before consensus, report
   disagreement/missingness and investigate systematic detection differences.
   Distinct reviewer IDs alone do not prove independent review.
6. Use `collection-audit` and resolve structural contradictions against source
   evidence. Version corrections; do not overwrite the original register. Inspect
   initial and final endpoint counts separately, including eligible count, known
   count, missing IDs, exclusions and missingness bounds.
7. Freeze a `ValidationPlan`. Its `training_demand_ids` and `training_group_ids`
   describe the model's development set; include external lineage in
   `training_manifest_digest` and `external_training_review`. Known training
   outcomes must precede model freeze. The API rejects overlapping groups and
   demands, late forecasts, missing eligible forecasts and late plans. It cannot
   discover unreported external training records.
8. Score held-out forecasts with Brier score, log loss, observed/predicted rates
   and prespecified calibration bins. Report outcome coverage and subgroup
   results. A wrong certain prediction makes log loss undefined/infinite; the
   serialized metric is `null` with `impossible_prediction=true`, not a clipped
   favorable score. Avoid accuracy dominated by successful tasks.
9. Specify acceptance criteria with the site owner **before** evaluation: endpoint
   agreement, required coverage, calibration tolerance, baseline comparison,
   acceptable uncertainty and intended risk decision. This toolkit supplies no
   universal safety acceptance threshold. Preserve failures and excluded runs.
10. Review dependence, selection and missingness before interpreting uncertainty.
    Optional bootstrap resamples whole declared groups; two groups is a software
    minimum, not evidence of statistical adequacy. Correlated crews, changing
    work mix and informative missingness require an appropriate analysis. A
    corrected/retrained model needs a new untouched evaluation cohort.

## Python API and integration

```python
# executable
from human_reliability.opportunity_validation import zero_error_plan

plan = zero_error_plan(0.001, confidence=0.95,
                      independence_review="Planning assumption: independent, representative demands")
assert plan["independent_opportunities_required"] == 2995
```

For an actual populated local bundle:

```python
from human_reliability import load_collection, BetaPrior
from human_reliability.opportunity_validation import ValidationPlan, validate_collection

bundle = load_collection("data/raw/site_study")
audit = bundle.require_reconciled()
estimate = bundle.hep(
    estimand="final",
    prior=BetaPrior(alpha=1, beta=1, evidence_id="approved-prior-record"),
    independence_review="Reference to the actual dependence assessment",
    missingness_review="Reference to the actual missingness/selection assessment",
)
```

`CollectionBundle.ledger()` returns the existing `ObservationLedger` with typed
`TaskOpportunity` and `RecoveryAttempt` records. `hep` accepts the ledger's
`window_ids` and `conditions` selections and returns the existing `Estimate`,
including event ID, conditioning, evidence IDs, uncertainty and audit trace.
The audit fingerprints both the protocol and the complete supplied table snapshot.
Changing observations, coverage or forecasts changes `collection_digest`; HEP
observation evidence IDs use this snapshot digest rather than only the protocol ID.
Prior alpha/beta are explicit parameters. Use a documented justified prior; the
example values are assumptions. A synthetic/simulator/induced bundle returns
`status="research"`; it cannot acquire natural-field status through this wrapper.
Natural-field status describes evidence origin, not safety qualification.

Use the returned estimate with existing reviewed task/risk bindings. Supply
matching evidence records and applicability reviews. FTA leaves must retain the
same event meaning and recovery scope. Demand rate and consequence are separate
inputs; a probability per task is not an annual failure frequency. The toolkit's
existing annualization API requires compatible coverage and stationarity reviews.
Do not transfer a clinical or simulator rate to a plant task by changing its label.

`validate_collection(bundle, plan, bin_edges=..., bootstrap_replicates=..., seed=...)`
returns a JSON-compatible report. `ValidationPlan` can be saved with
`model_dump_json()` and loaded with `model_validate_json()` for the CLI. Select
`initial` or `final` explicitly. Complete-case scores exclude unknown endpoints,
while `failure_fraction_bounds` covers all eligible evaluation demands. Missing
outcomes are not assumed missing at random. The optional group bootstrap's Brier
interval is a sensitivity calculation conditional on representative independent
groups, not a guarantee of field performance.

`exact_binomial_interval` implements a conditional Clopper-Pearson interval after
an explicit independence review. `zero_error_plan` calculates the independent
opportunities needed for a one-sided upper bound after **zero** observed failures.
At 95%, a target of 0.001 needs 2,995 independent opportunities; 0.0001 needs
29,956. These are not total-workforce quotas when demands are correlated, and zero
observed errors never establish zero risk. The Bayesian posterior and the exact
frequentist interval answer different uncertainty questions; label them separately.

## Reproduction and handoff

```console
python examples/field_collection.py
python scripts/run_denominator_study.py
python -m pytest tests/test_collection.py -q -W error
```

The first command writes a clearly marked **synthetic** study under `artifacts/`.
It exercises CSV round-trip, missing outcomes, frozen prediction evaluation,
cluster resampling, an explicit-prior posterior and the existing repeated-event
FTA path. It does not generate empirical validation evidence. The second command
recomputes the separate licensed aggregate study; it never fabricates individual
subjects. The third checks denominator, missingness, coding and leakage gates.

Retain protocol versions, raw register exports, observation coverage, original
ratings, adjudication, prediction artifacts, model/training lineage, rights,
audits, analysis environment and unfavorable results in the study archive. For a
public contribution, publish original code/forms and reviewed aggregates under
verified terms; user field records stay private unless their owner separately
authorizes release. See [DATA_LICENSES.md](../DATA_LICENSES.md) and
[RESEARCH_HANDOFF.md](RESEARCH_HANDOFF.md).
