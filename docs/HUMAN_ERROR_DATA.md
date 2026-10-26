# Human-error evidence: provenance, selection and API guide

Numeric catalog revision 0.2.0, shipped with software 0.4.0, packages **1,334 records from seven numeric sources**. The records
are available offline after a core installation. Eighteen candidate sources were
reviewed; selection/exclusion decisions are retained in
[`human_evidence_review.json`](../research/human_evidence_review.json).

This guide distinguishes observations, statistical estimates, method parameters,
published model outputs and derived frequency. These categories must remain
visible when an assessment is connected to a risk model.

## 1. What the catalog contains

| Kind | Count | Can be bound directly to a reviewed event? |
|---|---:|---|
| `observed_count` | 578 | With an explicit prior and applicability/scope review |
| `method_probability` | 176 | With an applicability/scope review |
| `method_interval` | 4 | With review and an explicitly selected point |
| `method_component` | 96 | No; an intermediate base input |
| `method_multiplier` | 476 | No; a dimensionless factor |
| `method_rule` | 4 | No; applied by the relevant profile calculator |

Only the first category contains released UNSAT/opportunity counts. The catalog
does not contain acquired chemical-plant field calibration or observed annual
task-error frequency series. It cannot turn a process alarm, fault label, expert
rating, report count or questionnaire score into an observed human-error rate.

### Source inventory

| Source ID | Included evidence | Scope and rights |
|---|---|---|
| `sacada_2019` | Five released function/context count files | Nuclear simulator observations; NRC public-data/site policy |
| `idheas_eca_2022` | 468 numerical entries: components, modifiers and five function floors | NRC staff method reference; explicitly flag placeholders |
| `spar_h_2005` | 76 entries: two nominals and stage-specific at-power profiles/rules | Numerical facts with original labels and attribution; no full contractor report relicensing |
| `plos_powerline_2021` | Nine HEART task nominals, 39 EPC variants and 52 Z/fuzzy case outputs | CC BY 4.0; method/expert estimates for electrical isolation |
| `plos_flight_2020` | 34 HEART and 34 IAHP-HEART case outputs | CC BY 4.0; expert-derived aviation case |
| `plos_cream_2024` | 13 nominal modes and 26 CREAM case outputs | CC BY 4.0; published secondary nominals and aviation case |
| `mdpi_lng_2022` | Four CREAM category intervals and one LNG model prior | CC BY 4.0; questionnaire/model inference |

The authoritative rights, authors, versions, links and limitations are in the
packaged `human_evidence_sources.json`. Every numerical record identifies a source
and table/row locator. See [Data licenses](../DATA_LICENSES.md) for attribution and
transformation notices. An open article is not proof that an underlying complete
raw database is openly available.

## 2. Understand the observed SACADA data

The NRC release covers licensed-operator simulator training/experiments through
March 2019, released in April 2019. One row groups a context within a macrocognitive
function. Its denominator is an evaluated **Training Objective Element (TOE)**;
its numerator is the **UNSAT training assessment outcome**.

| Function key | Context groups | UNSAT | Opportunities |
|---|---:|---:|---:|
| `detect_alarm` | 61 | 13 | 2,099 |
| `read_indicator` | 95 | 17 | 2,198 |
| `understanding` | 116 | 28 | 2,613 |
| `decision` | 147 | 32 | 6,019 |
| `action` | 159 | 59 | 5,167 |

The function totals sum to 18,096 opportunities. Do not interpret this sum as
18,096 independent trials, people or complete episodes. Crew and episode identities
are absent, and related activities can appear in different functions. Never pool
the five files into a global HEP or use them to estimate a stage-dependence matrix.

Within a function, the retained rows have distinct full context vectors. Some
groups have only two opportunities. The released aggregate data cannot support
crew-cluster bootstrap or complete hierarchical operator effects. Statistical
intervals need stated model assumptions and do not resolve that missing structure.

UNSAT is not automatically equivalent to a hazardous wrong-valve operation,
unrecovered safety failure, missed-alarm omission or fatal outcome. A released row
does not identify a specific valve at your facility. Transfer to a target event
requires a review of failure definition, demand, context and response scope.

### Context codes

`conditions` retains normalized field names and integer source categories. The
codebook preserves original column names, available categories and explicit missing
codes. It does not infer continuous workload, stress or time from a category.

| Common field | Interpretation |
|---|---|
| `workload` | 0 unspecified; 1 reference; 2 concurrent demand; 3 several concurrent demands |
| `time_criticality` | 0 unspecified; 1 large margin; 2 reference margin; 3 small margin |
| `extent_of_communication` | 0 unspecified; 1 reference exchange; 2 extensive on-site; 3 extensive control-room exchange |
| `non_standard` | Binary: absence/presence of the source condition |
| `noisy_background` | Binary source noise condition |
| `communicator_unavailable` | Binary source availability condition |
| `multiple_demand` | Binary source demand condition, distinct from the workload category |
| `memory_demand` | Binary source memory condition |

Zero is **missing only where the source legend declares NULL**. Zero in a binary
condition means absence. The alarm and indicator detection-mode codes differ.
Indicator code 2 has an ambiguous combined label in the original header; the
codebook preserves that ambiguity instead of inventing a clean category.

Additional function-specific conditions include board congestion, cue expectation,
indication type, change magnitude, information availability, decision context,
action location/guidance and recoverability. `sacada_context_labels(record)` or
`evidence show` displays their labels. The original dictionary and column legends
remain in the pinned, locally acquired sources for detailed independent review.

## 3. Query the evidence

```console
human-reliability evidence summary
human-reliability evidence sources
human-reliability evidence search --kind observed_count --function action --condition workload=2 --condition time_criticality=2 --limit 5
human-reliability evidence show sacada.action.r0003
human-reliability evidence search --method idheas_eca --text noise --limit 20 --out artifacts/noise_candidates.json
```

Python provides the same exact filters:

```python
from human_reliability import builtin_evidence_catalog, sacada_context_labels

catalog = builtin_evidence_catalog()
matches = catalog.search(
    source_id="sacada_2019", kind="observed_count", function="action",
    conditions={"workload": 2, "time_criticality": 2},
)
record = catalog.get("sacada.action.r0003")
print(record.failures, record.opportunities, record.observed_fraction)
print(sacada_context_labels(record))
print(catalog.sources[record.source_id].rights)
```

Unknown filter names/values and unavailable condition fields raise errors. Integer
code 1 is not matched by Boolean `True`. A valid filter combination with no matching
rows returns an empty collection. Text filtering searches the project label/ID;
it does not perform semantic similarity or authorize context transfer.

Do not select the lowest observed fraction simply because it is favorable. Define
eligibility before examining outcomes and record why omitted contexts differ.
There is no automatic nearest-neighbor borrowing or hidden fallback to another
domain. A sparse group can have much greater uncertainty than a broad method prior.

## 4. Convert counts into a reviewed estimate

`catalog.bind(record_id, event, review=..., prior=...)` returns an `EvidenceBinding`:

- `.estimate`: the existing `Estimate` contract used by downstream modules.
- `.evidence`: source and prior `Evidence` records to retain with an assessment.

Supply `HumanFailureEvent` with an exact target failure, demand and conditioning.
Supply `ApplicabilityReview` with analyst, target domain, transfer rationale,
timing/recovery rationale and explicitly chosen `included_effects`. Supply a
`BetaPrior` with alpha, beta and its own evidence identity.

For counts `k` out of `n`, posterior parameters are `alpha+k` and `beta+n-k`.
The raw fraction `k/n` remains in the trace. A zero numerator does not force a zero
posterior or certain success. Method probabilities never accept fabricated
Bernoulli denominators.

The fully executable example is [evidence_to_risk.py](../examples/evidence_to_risk.py).
Its selected group `sacada.action.r0003` is Excel row 3 of the released action file:
1 UNSAT, 103 opportunities. With the explicitly chosen Beta(0.5, 0.5) example prior,
the posterior mean is `1.5/104`, approximately 0.0144231. The raw observed fraction
is approximately 0.00970874. A different justified prior changes the posterior.

The trace retains source domain, setting, conditions, failure/demand definition,
observed fraction, prior/counts, target review and source license. Cross-domain
binding of observed counts is marked `research`. It is not labeled field-validated.

### Timing and recovery scope

SACADA's released counts cannot separate late response and recovery. The example
sets `included_effects=("timing", "recovery")` to prevent adding either again.
This is a conservative scope lock for an aggregate outcome, not proof that each
specific mechanism has been separately measured. If another treatment is justified,
document it explicitly and acquire the supporting event-level evidence.

### Pooling context groups

`count_summary(ids, disjoint_contexts_rationale=...)` permits count aggregation only
within one source/function/domain/demand definition. IDs and full context vectors
must not repeat. It returns counts and a descriptive fraction, with
`independent_trials_verified=False`.

It does not infer an independent sample, identify crews, merge overlapping events
or produce a qualified plant estimate. Pooling different functions or method
references is rejected. A subsequent statistical model remains the analyst's
responsibility.

## 5. Use a catalog-backed JSON assessment

The built-in method name is `evidence_catalog`. Its parameters are:

```json
{
  "record_id": "sacada.action.r0003",
  "review": {
    "analyst": "Example analyst",
    "target_domain": "illustrative_process_model",
    "rationale": "Software example; field transfer is not established.",
    "scope_rationale": "Do not apply timing or recovery again to aggregate UNSAT.",
    "included_effects": ["timing", "recovery"]
  },
  "prior": {
    "alpha": 0.5,
    "beta": 0.5,
    "evidence_id": "explicit_prior"
  }
}
```

Put the binding's evidence records in `task.evidence`. The `ModelSpec.evidence_ids`
must exactly match the estimate's source/prior IDs. The ordinary registry checks
that the evidence is available and the event/conditioning/scope match.

For method point values, omit `prior`. For method intervals, add `selected_value`
inside the source bounds and justify its choice in the review. No midpoint or
distribution is selected automatically. A component or multiplier cannot be bound
as a stand-alone HEP. `catalog.estimator(...)` also provides a callable for a
custom `AssessmentEngine` registration.

## 6. Numerical method profiles

### SPAR-H

```python
from human_reliability.reference_methods import spar_h_profile_probability

levels = {
    "available_time": "reference", "stress": "reference",
    "complexity": "moderate", "experience_training": "limited",
    "procedures": "weak", "ergonomics": "reference",
    "fitness": "reference", "work_processes": "reference",
}
p, trace = spar_h_profile_probability("action", levels)
```

All eight choices are mandatory. The bundled profile is the **at-power Appendix A**
profile from NUREG/CR-6883. Diagnosis and action use different values for some
factors, including experience/training and work processes. It is not a universal
low-power/shutdown or cross-industry profile.

Three or more adverse factors activate the source normalization. Inadequate time
or unfit duty are explicit terminal rules; all selections are still validated.
Unknown information requires `allow_unknown=True` and remains marked as unknown,
even where the source assigns multiplier one. Time categories carry their source
ratio/margin conditions. Selecting a category does not replace a physical response
feasibility check.

### HEART

```python
from human_reliability.reference_methods import heart_profile_probability

p, trace = heart_profile_probability("G", (("heart.epc.2.v1", 0.25),))
```

The nominal and effect references come from the cited CC BY article. The caller
supplies assessed proportions. Alternative levels of EPC 34 cannot both be applied.
The trace retains the uncapped product and all selected record IDs. Published
secondary bounds are not sampling distributions; the reversed interval for GTT E
is withheld and retained in the anomaly report without guessing a correction.

Z-HEART, fuzzy HEART and IAHP-HEART case outputs are retained as **published case
estimates**, not implemented universal estimators or evidence that one method is
more accurate. Their contexts and task IDs must not be dropped when comparing them.

### IDHEAS-ECA

The catalog indexes Appendix B base components and modification weights, including
all four C41 communication-complexity levels, subcategories and function-specific
not-applicable cells. Blank/NA cells are excluded rather than converted into zero.
Source boundary ambiguity at 11 signals and 15 messages is retained for review.

Values 1.1/1.2 remain `basis="placeholder"` where the source identifies insufficient
quantitative information. WP3 has a separate expert-elicitation limitation.
Inactive base-component values of zero do not mean zero human failure: the method
uses function floors of 0.0001 or 0.001 under the stated reference conditions.

`idheas_cfm_probability(function, base_probabilities, modifier_weights,
recovery_divisor=1)` implements the equations 3.4/3.5 arithmetic for one cognitive
function. It requires all three named base influences. Modification uses
`1 + sum(weight-1)`, not the product of weights. A cap at one and the uncapped result
are explicit. Attribute/PIF selection, overlap, recovery credit, uncertainty,
task/HFE aggregation and time remain application responsibilities. This is not a
complete official IDHEAS-ECA implementation.

### CREAM and LNG model outputs

Nominal failure modes, four control-mode ranges and published case HEPs are
distinguished. The LNG value 0.009841 is a questionnaire-informed fuzzy BN-CREAM
model prior. It is not an observed bunkering error frequency. The source assumes
the same HEP across its tasks and no duration dependence. Do not treat it as a
validated hydrogen-station shutdown probability. The full fuzzy BN/CPT is not
reproduced by retaining that published value.

## 7. Convert probability to annual frequency

```python
from human_reliability import annual_frequency_from_evidence

rate = annual_frequency_from_evidence(
    binding.estimate, 100.0,
    opportunity_definition=event.opportunity_definition,
    exposure_evidence="Documented schedule of matching demands; illustrative here",
)
```

The expected annual count is `matching_demands_per_year * probability_per_demand`.
The source supplies a conditional probability basis; the application supplies the
exposure. The API rejects mismatched demand definitions, records exposure evidence
and returns `observed_annual_frequency=False`.

If a task is demanded only after an automatic failure, its exposure must reflect
that conditioning. In the executable example, assumed initiating frequency 0.01/year
and automatic success 0.9 yield manual demands of 0.001/year. The same manual HEP
then yields the same unrecovered-path frequency through both exposure conversion
and ETA. That agreement is an implementation consistency check, not field validation.

## 8. Reacquisition and rebuild

```console
python -m pip install -e ".[data,curation]"
python scripts/acquire_human_evidence.py
python scripts/curate_human_evidence.py
```

Thirteen pinned assets are described in `research/human_evidence_assets.json`:
five SACADA count files, dictionary/readme, government method references and
published licensed article sources. SHA-256 and byte counts are recorded. A local
hash verifies retained bytes/version identity; it is not a publisher's digital
signature. Source binaries remain under ignored `data/raw/hra_evidence/`.

Some official servers reject non-browser requests with HTTP 403. Use an ordinary
browser on the linked source page, save the exact named files in an ignored folder
such as `artifacts/incoming`, then run:

```console
python scripts/acquire_human_evidence.py --import-directory artifacts/incoming
python scripts/curate_human_evidence.py
```

No login, CAPTCHA bypass or altered security setting is part of the acquisition
procedure. Changed bytes are rejected until the source/version review is updated.
The import flag is for named pinned files, not arbitrary workstation folders.
The acquisition report records failures instead of calling them acquired data.

The curator validates counts, complete context vectors and duplicate groups; parses
source tables; resolves merged cells and variants; applies independently written
labels; preserves source anomalies; and validates all resulting contracts. It
writes the packaged catalog/codebook and `research/human_evidence_audit.json`.

## 9. Add your own evidence

Use `load_evidence_catalog(source_document_or_path, record_document_or_path)`.
Both documents require `schema_version="1"`. Sources need identity, authors,
reference/version, measurement setting, rights and limitations. Records need source,
quantity/kind, failure/demand definitions, function/domain, conditions and locator.
Observed records accept field, laboratory, simulator or operational-record origins.

Observed counts need nonnegative integer failures, positive opportunities and
failures no greater than opportunities. Method records cannot contain invented
counts. Bounds must be paired and ordered. Components and multipliers retain
distinct quantities. `numeric_reuse="not_cleared"` prevents numerical binding.

Inspect `HumanEvidenceSource.model_json_schema()` and
`HumanErrorRecord.model_json_schema()` for the exact schema. Keep source rights
and measurement provenance with custom data; a user catalog is not automatically
approved for publication or field transfer.

## 10. Verification and continuation

```console
python examples/evidence_to_risk.py
python scripts/run_verification.py
python scripts/inventory_environment.py
python scripts/build_release.py
```

Checks cover counts and locators, posterior/raw-fraction separation, zero-error
uncertainty, context codes, transfer labeling, pooling restrictions, method scope,
license blocking, JSON assessment, stage-specific profiles, IDHEAS arithmetic and
frequency/ETA consistency. The installed wheel must load the catalog in a separate
core-only environment. See [Validation](VALIDATION.md).

Open research gaps remain: matching task-level field exposure, event-level timing
and recovery, crew dependence, prospective validation and safe domain transfer.
Preserve exclusions and do not convert a missing denominator into a method success.


## Operational evidence extension

Version 0.3 adds observation/recovery ledgers, reviewed annualized demand exposure
and a `reported_observed_probability` schema for user-owned catalogs. The bundled
external records are unchanged. See [Operational extensions](OPERATIONAL_EXTENSIONS.md)
for complete-case versus eligible-demand denominators, unknown observations and
source-qualified summary binding. A rounded reported HEP must not supply invented
counts, and an elicited distribution must not become observed evidence.

## Process measurements and incident evidence

Version 0.4 adds a separate source catalog and six retrospective evaluations.
See [Field validation](FIELD_VALIDATION.md). Physical process rows and incident
C-code fractions are not added to the 1,334-record HEP/method catalog. They lack
human task-opportunity denominators. The simulator holdout study also retains its
source population, crew-overlap and calibration limitations.
