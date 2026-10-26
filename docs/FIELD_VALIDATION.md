# Public-data evaluation and field evidence

Version 0.4.0 adds source-qualified measurement readers, reusable validation
functions and six executed retrospective studies. This is a record of what was
tested, including poor results and unavailable evaluations. It does not qualify a
chemical-plant human error probability, certify an alarm function, or establish a
facility's annual accident frequency.

## Evidence classes and acquired assets

| Source | Acquired material | Evidence class | Supported use |
|---|---|---|---|
| [Continuous distillation](https://zenodo.org/records/17628963) | Version 1 archive, 28 experiments, 69,528 sensor rows; three experimental chemical systems | Physical laboratory measurements with source anomaly annotations | Condition-matched monitoring replay and a pure-water property check |
| [Steel energy](https://doi.org/10.24432/C52G8C) | 35,040 measured consumption records from one Korean steel facility | Production-process measurements | Rolling quarter-hour energy prediction under the declared clock interpretation |
| [Rail investigations](https://zenodo.org/records/18310486) | Released derivative CSV of 105 investigated accidents and its readme | Field incident cases with investigator-derived C1-C8 codes | Descriptive case composition and overlap; successful task opportunities are absent |
| [Gas turbine](https://doi.org/10.24432/C5WC95) | Previously acquired 36,733 observations across five source-year files | Power-plant measurements | A new cross-year prediction evaluation |
| Existing SACADA catalog | 578 released function/context count records, analyzed separately by function | Observed simulator UNSAT/opportunity counts | Context-level holdout prediction; no new independent crew or field population |

Three additional source families were acquired. The five pinned file assets,
including the reused turbine archive, total **5,139,756 bytes**. Exact byte sizes,
SHA-256 values, supplier checksums and direct acquisition URLs are recorded in
[`field_assets.json`](../research/field_assets.json). The additional archives,
CSV and readme remain under ignored `data/raw/`; they are not published in Git or
the source/wheel distributions. The earlier seven-source, 1,334-record numeric
HEP/method catalog remains unchanged.

The four field/process source entries are packaged as independently written
metadata in `human_reliability/data/field_sources.json`. Every entry records its
origin, domain, conditions, attribution and verified license evidence. All four
selected source datasets declare **CC BY 4.0**. Software remains MIT; the software
license does not replace data attribution. See [Data licenses](../DATA_LICENSES.md).

The rail CSV is an explicitly released derivative. The primary investigation
reports have a different reuse boundary and are not acquired or redistributed.
Incident selection and investigator coding are distinct from direct observations
of all operations. Overlapping C-codes are not an exclusive causal partition.
The source CSV/readme does not establish a currency field, so this implementation
does not bind its cost column to currency-specific consequences.

## Search decisions and access limitations

[`field_source_review.json`](../research/field_source_review.json) records the new
source decisions alongside the earlier human-evidence review. Relevant production
welding judgments were found in [Zenodo 20428512](https://zenodo.org/records/20428512),
but its data license is **CC BY-NC-ND 4.0**. Its rows and derived probability values
were not acquired for the public adapted-data boundary. An article's open license
does not override a different license on its accompanying dataset.

Official PHMSA incident-file downloads returned HTTP 403. The reviewed catalog
reported public access but did not establish an explicit reusable-data license.
No blocked download was bypassed and no PHMSA dataset is claimed acquired.
PRONTO is reusable under CC BY 4.0, but its large multimodal archive and induced
fault population were outside this frozen study. HuREX/EMBRACE raw access and the
reported/scaled denominator in a recent pre-initiator study did not establish a
new openly acquired task-opportunity dataset. These remain acquisition leads.

## Frozen design and deviations

[`field_protocol.json`](../research/field_protocol.json) fixes populations,
predictors, model settings, splits, baseline methods and metrics. The initial
protocol preceded prediction fitting. One subsequent amendment concerns the steel
source clock and was made before fitting the steel model. Algorithm settings and
evaluation periods were retained. The complete decision record is
[`field_protocol_deviations.json`](../research/field_protocol_deviations.json).

The study is retrospective. Published labels and source schemas were inspected
before freezing the protocol. This is not a prospective preregistered experiment.
Evaluation results were not used to tune the models and unfavorable results are
retained. Partial runs stopped by source-schema guards remain in
`research/retained_experiments/field_*_attempt.json`.

Four issues were retained rather than silently repaired:

1. The steel file puts each day-ending midnight after that day's 23:45 while
   retaining the earlier date. Literal timestamps reverse 365 times. The reader
   rejects this by default. The benchmark explicitly opts into
   `midnight_policy="end_of_recorded_day"`, checks adjacent records, preserves
   `source_time_raw`, and records 365 interpreted rows. Forecast timing is
   conditional on that interpretation; measured consumption values are unchanged.
2. The installed numerical stack warned on a generic-unit `Timedelta`
   constructor. Explicit integer seconds and a unit removed the warning without
   changing a model parameter or measurement.
3. One advanced annotation in the pinned distillation archive is **0.5**, outside
   its documented integer vocabulary. The reader preserves and flags it. The
   benchmark uses the separate valid binary common label. Strict phase-consuming
   applications can request rejection.
4. In the second evaluation run at water operating point 007, a mass-flow column
   contains **3,564 TRUE/FALSE cells**. Numeric views mark these as unavailable;
   they never become flow values 0 or 1. Raw cells remain intact. **1,666** of the
   unavailable rows have positive anomaly labels, so known-sample recall is
   reported together with measurement coverage.

Version pinning matters: the acquired archive and the later article describe
different timestamp conventions and data totals. Results here are computed from
the pinned archive, not inferred from a publication overview. In particular,
only **22 of 28** run clocks pass the complete physical-delay qualification.

## Measured versus estimated quantities

- Sensor readings and energy consumption are acquired observations. Reported
  anomaly annotations and incident codes are source assessments of those records.
- Regressor outputs, detection scores, calibration intervals and thermodynamic
  predictions are computed estimates. Their provenance never becomes observed
  simply because they are compared with a measurement.
- Simulator UNSAT counts remain simulator counts. Their fitted probabilities
  remain research estimates under the declared context and denominator.
- A labelled fault, an accident-code proportion, a sensor score, and energy error
  are not HEPs. `FieldSource.require_human_opportunities()` rejects the four
  packaged measurement/incident sources as human task-opportunity evidence.

The final machine-readable results are
[`field_validation_results.json`](../research/field_validation_results.json).
They retain protocol identity, source hashes, model parameters, library versions,
train/calibration/test counts, metric definitions, data-quality findings,
unavailable cases, and explicit application limits.

## Study 1: turbine output across source years

Only ambient temperature, pressure and humidity are predictors of `TEY`. Source
years **2011-2013** train the fixed histogram gradient boosting regressor;
**2014** supplies residual calibration; **2015** supplies evaluation. The baseline
is the training-target mean. The split contains 22,191 / 7,158 / 7,384 records.
No random intermixing of years is used.

| Evaluation on 2015 | Ambient model | Training-mean baseline |
|---|---:|---:|
| MAE, MWh | 14.9019 | 12.9569 |
| RMSE, MWh | 18.0668 | 16.1845 |
| Bias, MWh | +3.6250 | -0.4560 |
| R2 | -0.2471 | -0.0008 |

The model RMSE is **11.63% worse** than the prespecified baseline. The descriptive
paired block-resampling interval for model-minus-baseline RMSE is
**[1.0662, 2.6206] MWh**. The nominal 90% calibrated interval covers **84.47%** of
evaluation observations, with width 49.4857 MWh.

This ambient-only model is **not accepted as a validated output backend**. The
result is consistent with a limitation of using ambient measurements without a
load/control description, but the study does not identify a causal explanation.
Do not add predictors and reuse this evaluation period as an untouched test.
A revised model needs a new, explicitly qualified evaluation design.

## Study 2: steel next-interval consumption

Calendar features and already observed consumption at lags 1 and 96 are the only
predictors. Same-interval reactive power, carbon quantity, power factors and load
type are excluded. Training ends before July 2018, residual calibration occupies
July-September, and evaluation occupies October-December under the declared clock
interpretation. The split contains **17,279 / 8,832 / 8,832** records. The initial
96 lag-unavailable rows and the final interpreted 2019 boundary row are excluded
explicitly, for 97 excluded rows in total.

| Held-out evaluation | Fixed model | Previous-interval baseline |
|---|---:|---:|
| MAE, kWh | 4.5870 | 5.7996 |
| RMSE, kWh | 9.3124 | 12.7905 |
| Bias, kWh | +0.5610 | -0.0001 |
| R2 | 0.9151 | 0.8398 |

RMSE is **27.19% lower** than the persistence baseline. The descriptive paired
block interval for model-minus-baseline RMSE is **[-3.9051, -3.0590] kWh**.
The nominal 90% interval covers **89.54%**, with width 28.7338 kWh.

This supports a scoped retrospective prediction result at one facility. It is a
rolling forecast: each later prediction may use earlier measurements that have
actually arrived. It is not a quarter-long open-loop forecast, an intervention
effect, a human-reliability calibration or a result transferable to another plant
without new evidence.

Both regression studies use 1,000 paired moving-block resamples. Blocks contain
24 successive turbine records or 96 steel records. Serial dependence, operating
changes and limited sites prevent an IID confidence or guaranteed future-coverage
claim. The reported intervals and coverage remain descriptive.

## Study 3: condition-matched distillation monitoring

The reader acquires all 28 experiments, but monitoring is evaluated only when a
normal reference exists at **the same scenario and operating point**. There are
11 normal reference experiments and 17 source-named evaluation experiments.
Six evaluation runs have a matched reference; **11 are withheld**. No reference
from another chemical system or operating point is substituted.

A fixed robust maximum-deviation score uses the prescribed twelve sensor
channels. The first 75% of reference rows train location/scale, a ten-row gap
separates calibration, and the remaining reference rows determine the empirical
99th-percentile threshold. Three high samples activate an alarm; two low samples
reset it. These are sample counts, not an invented number of physical seconds.
Reference and evaluation runs are distinct. Some reference runs were acquired
after an evaluation run, so this is retrospective replay rather than prospective
deployment.

| Scenario / operating point / evaluation run | Point recall on known samples | Event recall | Event precision | Physical delay qualified |
|---|---:|---:|---:|---|
| Water / 004 / 001 | 0.0034 | 1.0000 | 0.3333 | Yes |
| Water / 006 / 001 | 0.0015 | 0.5000 | 0.1429 | No |
| Water / 007 / 001 | 0.0000 | 0.0000 | 0.0000 | Yes |
| Water / 007 / 002 | 0.0332 | 0.5000 | 0.0526 | No |
| Butanol-water / 001 / 001 | 0.0000 | 0.0000 | 0.0000 | Yes |
| Butanol-water / 001 / 002 | 0.0688 | 0.6667 | 0.2857 | Yes |

An event is a contiguous positive source-label interval. A new alarm activation
must occur within that interval and can match it only once. A continuing false
alarm from before an event receives no event credit. No point adjustment fills
an entire event as detected after one positive sample. Exact per-event sample
delays, qualified physical delays, unknown positive samples and false activations
are in the JSON report.

These results **do not qualify the detector as a safety alarm**. Event recall alone
can look favorable while point recall and false-activation burden remain poor.
The frozen baseline is retained without tuning thresholds on evaluation labels.
The OME scenario has no matched normal reference at its anomalous operating
points; its monitoring accuracy is unavailable in this study.

## Study 4: water property consistency using CoolProp

For all source-named normal water runs, the measured `T102` is compared with
`HEOS::Water` saturation temperature at `PIC101 * 100` Pa and quality zero. No
offset is fitted. **31,315** observed pairs yield MAE **1.5238 degC**, RMSE
**1.6980 degC**, bias **-1.2700 degC**, and R2 **-0.9098**. The prediction is lower
than the measurement on average.

This is an unfitted consistency diagnostic, not a complete column model. Local
pressure gradients, sensor location/immersion, heat transfer, composition and
instrument uncertainty limit a head-pressure saturation comparison. A fitted
offset would require separate calibration and evaluation data. The result does
not validate hydrogen release or full station consequences.

## Study 5: real incident-code composition

Across 105 released investigated cases, C1-C8 counts are respectively
**45, 8, 50, 44, 34, 13, 25 and 3**. Codes overlap. The module returns counts and
fractions conditional on a recorded investigated accident, together with the
overlap count. It returns `None` for HEP, annual human-error frequency and
currency-specific loss. This preserves the distinction between field incident
evidence and a sample of all operations.

`field_data.incident_lessons(frame, code_to_artifacts, analyst_review=...)` creates
the existing typed `IncidentLesson` records for explicitly reviewed artifact
bindings. Recommendations remain separate caller inputs. Findings state the
investigated-case denominator and can be supplied to `AssuranceLifecycle.review`.
The code does not automatically assign an independent basic-event
probability to a C-code. No primary report narrative or third-party notebook was
copied into this implementation.

## Study 6: simulator context prediction

SACADA functions are evaluated separately. Within each function, context IDs are
sorted, shuffled once with the frozen seed, and 30% are held out. A pooled
training-count model uses an explicit Beta(0.5, 0.5) prior. A fixed C=1 logistic
model uses numeric released context codes and aggregate error/success weights.
No fitted model is automatically registered as a plant HEP estimator.

| Function | Held-out opportunities | Pooled Brier | Context-model Brier |
|---|---:|---:|---:|
| Action | 1,896 | 0.010440 | 0.013237 |
| Decision | 1,710 | 0.004080 | 0.004113 |
| Alarm detection | 515 | 0.005792 | 0.005771 |
| Indicator reading | 773 | 0.003905 | 0.003936 |
| Understanding | 717 | 0.019286 | 0.019823 |

The context model is worse on Brier score for **four of five** functions. The
small alarm-detection improvement does not establish good calibration: its mean
predicted probability is 0.00160 against observed UNSAT fraction 0.00583.
Rare outcomes and numeric treatment of categorical codes limit interpretation.
Log loss and predicted/observed rates are retained, not replaced by an accuracy
score dominated by successful trials.

Crew/episode identities are unavailable. This is not independent-crew validation,
and separate function counts must not be summed into independent person-level
exposure. Recovery and timing are not separately identifiable in these aggregates.

## Python API and existing-module integration

The core metadata and metric functions require only the existing core libraries.
Physical CSV readers use `[data]`; the fixed regressors use `[learning]`; the
property study uses `[thermo]`. `field_studies` imports optional packages only
when the corresponding runner is called.

```python
# executable
from human_reliability import field_sources
from human_reliability.field_validation import regression_metrics

source = field_sources()["korea_rail_incidents"]
assert source.origin == "observed_incident_codes"
assert source.human_opportunity_counts is False
assert "CC-BY-4.0" in source.evidence().limitations[-1]

# Authored arithmetic example, not acquired rows.
result = regression_metrics([1.0, 3.0], [2.0, 4.0])
assert result["rmse"] == 1.0
```

With the acquired archive available:

```python
from human_reliability import field_sources
from human_reliability.field_data import continuous_distillation
from human_reliability.monitoring import AlarmPolicy

runs = continuous_distillation("data/raw/continuous_distillation/source.zip")
run = next(r for r in runs if r.clock.qualified)
state = run.process_state(0, {"T102": "degC", "PIC101": "mbar"})
source = field_sources()["tum_continuous_distillation"]
context = source.context("measured-state", state, operating_mode=run.operating_point)
evidence = source.evidence()  # Includes attribution, conditions and data terms.
series = run.signal("PIC101", "mbar")

# An analyst-selected monitoring threshold; not a qualified protection function.
alarm = AlarmPolicy(1500.0, 1450.0, persistence_s=60.0, maximum_gap_s=90.0)
information = alarm.evaluate(series)
```

`process_state` and numeric views exclude evaluation labels from observations.
`numeric_matrix(channels)` returns both a matrix and its missing/malformed-cell
audit. `signal` requires a qualified source clock by default. An explicitly
assumed sample period produces `origin="measured_values_on_assumed_clock"` and an
`assumed_grid:` clock identity. Such a grid does not establish observed physical
response times. Keep the complete `FieldSource` alongside exported evidence.

Reusable entries in `field_validation` are `regression_metrics`,
`calibration_width`, `interval_metrics`, `paired_block_rmse`,
`fit_robust_reference`, `SampleAlarmPolicy`, `detection_metrics` and
`aggregate_binomial_metrics`. `field_studies.regression_holdout` accepts explicit
disjoint masks, features, target, baseline predictions, units, model parameters
and a model factory. Dataset-specific runners accept the frozen specification;
change it only for a new, separately recorded research design.

Process measurements can inform operating conditions and supplied simulators.
They do not supply missing initiating frequencies or harm probabilities. Existing
RiskEngine, FTA/ETA, recovery and method workflows retain their own evidence and
conditioning checks. Incident-case fractions cannot be inserted as demand HEPs.

## Reproduction, verification and publication

```console
python -m pip install -e ".[data,learning,survival,thermo,sensitivity,bdd,dynamics,curation,dev]"
human-reliability field-sources
python scripts/acquire_field_data.py
python -W error scripts/run_field_studies.py
python scripts/check_field_record.py --require-assets
python examples/field_evidence.py
python scripts/run_verification.py
python scripts/build_release.py
```

The complete software suite uses the full extras shown above. Add
`--integrations` to the verification command when the pinned external targets in
[Integration](INTEGRATION.md) are available. The field
acquisition script refuses changed bytes at a pinned URL, verifies existing files
without downloading them again, and supports `--only SOURCE_ID` and
`--verify-only`. It does not replace a changed source with a convenient mirror.

The empirical record binds its canonical protocol digest, exact raw-asset hashes,
source catalog and relevant implementation. Text-source fingerprints normalize
CRLF to LF so Git line-ending conversion does not appear to change a model.
The original byte-level protocol fingerprint is retained as a local snapshot;
the canonical JSON digest identifies its meaning across platforms.
Package versions are stored with the results and in `research/environment.json`.

`check_field_record.py` rejects stale implementation or protocol records.
`--require-assets` additionally rechecks the acquired bytes. Ordinary offline CI
checks the retained record and authored counterexamples without reacquiring raw
datasets or claiming to rerun the empirical studies. A researcher can run the
complete acquisition and evaluation sequence above to reproduce them.

Tests cover clock reversals, explicit midnight interpretation, fractional labels,
boolean contamination of a physical measurement, observation validity, native
context binding, non-HEP incident evidence, disjoint fitting, finite calibration
order statistics, paired block arithmetic and one-to-one event matching. An
always-on alarm cannot earn event credit by spanning a later event.

The next research gate remains a rights-cleared chemical-process dataset with
unique operator/task opportunities, outcomes, observation completeness, recovery,
timing and actual compatible exposure. New plant data should be evaluated with a
fresh facility/time holdout before human-error or protection-credit claims are
made. The public results here provide evidence about the tested processes and
show exactly where broader claims remain unavailable.
