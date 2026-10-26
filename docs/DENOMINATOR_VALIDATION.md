# Public task-opportunity evidence and validation record

Date: 2026-10-26. Software scope: version 0.5.0.

## Research outcome

The targeted search did not acquire a new openly reusable industrial field
dataset with both a directly observed task denominator and adjudicated human
error outcomes. This is a search result, not a claim that such data do not exist.
Relevant maintenance studies, CORE-DATA descriptions, nuclear operational
experience and electricity protection reports were screened. Some lacked public
microdata or verified reuse rights; others used inferred exposure, simulator or
induced errors, incident composition, or system demands rather than human tasks.

The decisions, inspection levels, links and rights status are retained in
[opportunity_source_review.json](../research/opportunity_source_review.json).
Unverified/restrictive numbers were not added to the usable HEP catalog. Existing
SACADA simulator counts remain separately labeled. The original seven-source,
1,334-record HRA catalog and the six version 0.4 studies remain intact.

One additional public source supplies real successes and failures for a different
endpoint: published hospital specimen-workflow aggregates. It is kept in a
**separate aggregate benchmark**, with human attribution and industrial transfer
both explicitly unqualified. The field collection fallback requested for limited
public data is implemented in [FIELD_COLLECTION.md](FIELD_COLLECTION.md).

## Selected evidence and rights

Tabatabaee et al. (2023), Patient Safety in Surgery 17:8,
[publisher article](https://doi.org/10.1186/s13037-023-00360-1),
[monthly table](https://link.springer.com/article/10.1186/s13037-023-00360-1/tables/3).
The publisher grants CC BY 4.0 for the article and states a CC0 waiver for its
data unless otherwise credited. Attribution, source links, license and changes
are retained conservatively in
[opportunity_benchmarks.json](../src/human_reliability/data/opportunity_benchmarks.json).

Only six published monthly success/failure aggregates were selected and
reformatted with original machine labels. Source prose, layout, photographs and
individual records are excluded. The article makes individual data available
only on request; those records were not acquired. Local HTML responses are kept
outside publication, with retrieval fingerprints in
[opportunity_acquisition.json](../research/opportunity_acquisition.json).
Dynamic HTML fingerprints identify this retrieval, not an immutable upstream
dataset release. Rechecking the source table is possible without downloading
any patient-level data.

The reported population comprises 5,617 assessed specimens, with 4,971 recorded
without a nonconformance and 646 with one. Each monthly row reconciles successes
plus failures to total opportunities. Department/category tables describe the
same population and are not added as extra trials. This is a clinical workflow
endpoint, not a proven count of individual human mistakes or harmful outcomes.

## Executed exploratory temporal check

[denominator_protocol.json](../research/denominator_protocol.json) records the
rule before computation, **after the source counts had been inspected**. This is
retrospective exploratory evaluation, not preregistration or prospective
prediction. April-June is the development period; July-September is evaluated
once. A constant predictor uses the Beta(1,1) posterior mean from development
counts. There is no fitted task taxonomy, PSF model or individual-data expansion.

| Result | Value |
|---|---:|
| Development failures / opportunities | 486 / 3,189 |
| Constant posterior mean used for evaluation | 0.1526167346 |
| Evaluation failures / opportunities | 160 / 2,428 |
| Evaluation observed fraction | 0.0658978583 |
| Brier score | 0.0690754941 |
| Mean log loss | 0.2785658342 |

The predictor overstates the later observed rate by approximately 8.67 percentage
points. **Temporal calibration is not established.** No alternative was tuned to
improve this held-out result. A lower training-to-test rate does not by itself
establish an intervention effect; changing mix, ascertainment and other factors
cannot be resolved from monthly aggregates. No confidence interval based on
independent crews, external site transfer, causal effect or industrial HEP
validation is claimed.

The denominator supports descriptive proportions and aggregate proper scoring.
It does not establish full human-error ascertainment, identifiable human causes,
independent Bernoulli trials, recovery probabilities or demand frequency per year.
Consequently these counts are not silently exported as human HEP calibration
records or risk-model leaves.

## Implementation and verification

`collection.py` defines strict collection contracts, blank-form generation,
explicit CSV parsing, independent-register reconciliation, missing-outcome
preservation and an adapter to `ObservationLedger`. `opportunity_validation.py`
adds predeclared cohort/prediction checks, training/group exclusion, proper
scores, calibration bins, optional whole-group bootstrap, conditional exact
binomial intervals and zero-error planning. Parameters and study identities are
supplied by the application; natural, simulator, induced and synthetic settings
remain separate.

Acceptance checks cover CSV round-trip; absent outcomes; unknown final results;
unresolved attribution; distinct adjudication identities; duplicate exposure;
pretrigger withdrawals; failed coverage/register counts; every eligible demand's
prediction; time and group leakage; explicit Boolean parsing; empty forms;
non-overwrite; nonzero upper bounds after zero failures; source rights and count
reconciliation; and exact reproduction of the retained aggregate result.

Software verification and source-byte checks are separate from empirical
validation. The tests exercise authored fixtures, while the public aggregate
calculation exercises published measured counts for its restricted endpoint.
Neither establishes safety protection credit. Executed counts/checks are recorded
in [verification_summary.json](../research/verification_summary.json).

```console
human-reliability opportunity-benchmarks
python scripts/run_denominator_study.py
python examples/field_collection.py
python scripts/run_verification.py --integrations
python scripts/build_release.py
```

[denominator_validation_results.json](../research/denominator_validation_results.json)
contains the counts, prediction, monthly calibration, proper scores and normalized
implementation hashes. The regression test recomputes the complete result and
compares it to the retained file, so a changed protocol/implementation requires a
new recorded result. It does not overwrite the earlier six-study record.

## Next empirical milestone

Complete a site-owned prospective task census using the supplied original forms.
The critical missing evidence is an independently reconciled eligible task
register paired with adjudicated successful/error outcomes and pre-outcome model
predictions in the intended industrial conditions. Preserve initial/final scope,
unknown outcomes, source rights, crew dependence and untouched evaluation data.
The detailed procedure specifies collection, review, analysis and research
handoff; its blank forms are ready to customize without importing restricted
third-party worksheets.
