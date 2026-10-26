# Verification and empirical evaluation

## Version 0.4 public measurement evaluation

[Field validation](FIELD_VALIDATION.md) records six executed retrospective studies
with a frozen protocol, source byte hashes and retained unfavorable results. Three
additional source families were acquired under reviewed CC BY terms. Steel energy
prediction improves its prespecified baseline; ambient-only turbine prediction,
the frozen monitoring baseline and simulator context models do not establish a
broad accuracy improvement. Physical property comparisons remain diagnostics.

The new record is `research/field_validation_results.json`. Source-clock and
annotation deviations remain in `research/field_protocol_deviations.json` and
partial stopped runs in `research/retained_experiments/`. A current software test
record alone is not a field HEP validation claim. Offline CI checks authored
counterexamples and empirical-record freshness; it does not reacquire raw data.

## Version 0.3 operational acceptance

[Extension validation](EXTENSION_VALIDATION.md) maps all twelve implemented scopes
to independent limiting cases, failure counterexamples, state-machine tests and
end-to-end execution. `research/extension_validation.json` is generated only from
passing named tests and the current verified source/data/documentation hash set.
It complements the original software, empirical-study and object-contract checks.

The integration check now also exercises RiskEngine with the real pinned
DynaSense consequence provider and exports its partition as real PRISM objects.
Core-wheel checks exercise risk and reference workflows without optional libraries;
coupled scheduling is verified in the full `[dynamics]` environment.

Software invariants, model reproduction, source-contract compatibility, experimental
prediction and actual plant/operator effectiveness are separate evidence levels.
This release records the first four at specified scopes. It does not claim field
calibration of all human error probabilities or certification of a protection layer.

## Reproduce the checks

```console
python scripts/run_verification.py
python scripts/run_verification.py --integrations
python scripts/acquire_data.py
python scripts/audit_data.py
python scripts/run_studies.py
python examples/process_context.py
python scripts/inventory_environment.py
python scripts/build_release.py
```

Install the optional testing/data libraries before running the full suite.
Integration checks require the pinned external package targets described in
`docs/INTEGRATION.md`. The compact recorded result is
`research/verification_summary.json`; temporary logs and JUnit results remain in
ignored artifacts. A changed verification-input digest invalidates release
preparation until verification is rerun. Inputs include Python, packaged JSON,
case specifications, primary documentation and build/CI configuration.

## Software coverage

Version 0.2 adds 17 catalog tests for source/kind separation, observed-count
posteriors, application review, codebook missingness, disjoint-context summaries,
method-component rejection, explicit interval selection, exposure units, source
rights and reference-method arithmetic. A complete evidence-to-event-tree example
checks that annual consequence frequency agrees with the explicitly derived
manual-demand exposure. Documentation checks execute the README Python example
and check local Markdown links. The isolated core-wheel check loads all 1,334
records without installing optional data or numerical backends.

Tests check probability bounds, zero-failure posterior uncertainty, rate versus
interval-probability conversion, recovery scope, dependency ordering and method
evidence. Randomized property checks cover Boolean shared-event identities and
frequency conservation. BDD results are compared with exact state enumeration.
Dependent-event probabilities are independently computed from a declared Bayesian
joint distribution.

Kaplan-Meier tied event/censor calculations are compared with lifelines. Censored
Weibull recovery is checked against a known stochastic generator. AFT and Cox
context effects are checked on authored data. These are implementation checks,
not human-behavior validation. Alarm tests retain invalid observations and break
persistence across unknown intervals. Task tests prevent future outcomes from
entering an earlier conditional failure decision and verify chronological replay.

Reachability tests expose an unsafe error transition and withhold results at an
exploration limit. Thermodynamic checks compare the water saturation state with a
known reference and close mass/energy accounting. Adapter tests preserve clocks,
invalid measurements, command versus completion time and frequency normalization.

## External object checks

Eight object/implementation boundaries are exercised: PRISM DemandFailure and
EventBranch, DynaSense Scenario and simulator, SAGA HAZOP request, monitoring result,
QSafety mixture, LH2DT ObservationTable and the isolated station SafetyPLC.
The exact source pins and module hashes are in `research/integration_checks.json`.
No live LLM/API call, actual actuator command, full station loop or operator
effectiveness study is part of those checks.

## Experimental results

The frozen protocol predates model fitting but follows source-schema inspection.
Its digest, seed, excluded predictors, split unit and metrics are retained.
Participants do not overlap between train and test. Post-task workload,
consequence, accuracy and response summaries are excluded from the predictive input.

For released HITL simulator summaries, 32 participants/94 rows train the model and
15 participants/45 rows evaluate it. A categorical context logistic model using
only experimental group and scenario obtains Brier score approximately **0.1342**,
compared with **0.2359** for the smoothed training-prevalence baseline. ROC-AUC is
approximately **0.9002** in this split. The target is the source's `Poor` performance
label, not a chemical-plant failure-on-demand event. Small-sample uncertainty,
experimental group construction and population transfer remain unresolved.

The monitoring-response distribution uses 2,141 training and 966 held-out observed
responses. Held-out coverages at the training p50, p90 and p95 native-unit thresholds
are about **0.4451, 0.8758 and 0.9286**. These deviations are retained; the observed
distribution is not claimed universally calibrated. Unrecorded responses and native
unit mapping prevent a missed-alarm HEP or physical deadline claim.

The PVT flag analysis is **withheld**, because every session has the same positive
flag position. The rejected diagnostic and protocol deviation are retained. A
degenerate bootstrap interval is not evidence of precisely known human error.

## Process example

The real MetroPT compressor example calibrates a descriptive motor-current
threshold on March and applies a causal persistence policy from April onward. It
retains source timestamps, channel units and gap handling. It demonstrates context
ingestion only. The equipment data does not supply human response or HEP labels.

## Outstanding qualification

Needed evidence includes actual work opportunities and response outcomes, verified
time semantics, independent recovery/dependency studies, task/domain transfer and
prospective performance. Keep operational data rights and controlled facility details
separate from public package examples. Repeatedly inspecting the same holdout does
not create a new independent validation set.
