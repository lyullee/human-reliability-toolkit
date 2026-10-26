# User guide

## Measured evidence and empirical checks

Run `human-reliability field-sources` to inspect the four process/incident source
entries and their rights. Follow [Field validation](FIELD_VALIDATION.md) to acquire
pinned assets, reproduce six retrospective studies and connect measured channels
to existing APIs. Acquired observations, annotations, incident composition and
model predictions retain separate meanings. The earlier probability catalog and
risk templates remain available; process prediction accuracy supplies no missing
HEP denominator or initiating exposure.

## Operational workflows in version 0.3

Start with [Operational extensions](OPERATIONAL_EXTENSIONS.md) to run configurable
risk, reference-method and coupled-process JSON templates. It explains twelve
composable capabilities, parameter definitions, failure states and Python APIs.
[Extension validation](EXTENSION_VALIDATION.md) maps their implemented scopes to
executable acceptance evidence. Original assessment cases remain supported.

The operational example writes an input case and detailed result to
`artifacts/operational_research/`; replay that case with `risk-run`. It combines
source-qualified count evidence with explicit illustrative exposure, consequences
and design changes. Authored observations and physical examples remain distinct
from the external numeric catalog and from validated plant data.

This guide explains how to build a traceable human-reliability assessment and
connect it to process-risk calculations. Version 0.2.0 supports Python use, JSON
cases and a command-line interface. No hosted service is required.

## 1. Installation

Use Python 3.12 or newer and an activated virtual environment. Install the core
with `python -m pip install -e .`. The core includes the catalog and needs no Excel
application, PDF reader or network connection for querying evidence.

| Extra | Needed for |
|---|---|
| `data` | Excel/RData and process/context readers |
| `curation` | Rebuilding references from pinned source publications |
| `learning` | Grouped classification and empirical metrics |
| `survival` | Censored AFT/Cox regression through lifelines |
| `thermo` | CoolProp properties in SI units |
| `sensitivity` | SALib sensitivity analysis |
| `bdd` | Decision-diagram FTA backend |
| `dev` | Tests, formatting and package builds |

```console
python -m pip install -e ".[data,curation,learning,survival,thermo,sensitivity,bdd,dynamics,dev]"
human-reliability doctor
```

`requirements-validated.txt` records one Windows test environment. It is not a
universal lockfile or a claim that every allowed dependency version is tested.

## 2. Define the assessment before choosing a probability

Document process state, task, responsible role, cue, successful outcome and scope.
Specify one demand and what makes it unsuccessful. Distinguish event roles:

- `initiating`: an action causes a disturbance.
- `latent`: an earlier action leaves an undetected defect or unavailable function.
- `response`: a demanded protective/mitigating action fails.

For a response, state what already occurred. Failure conditional on automatic
shutdown failure differs from unconditional operator failure. The same cue, power,
operator or actuator can affect several protections; model those shared causes.

Represent the task with `Task` and `TaskStep`. Step kinds cover observing,
identifying, deciding, communicating, manipulating, verifying and restoring.
Declare prerequisites, roles and resources. Graph validation rejects unknown
predecessors and cycles. Retain procedure versions and supporting `Evidence`.

`analyze_task` generates review candidates. Prompts are customizable; exclusions
need a rationale. Qualitative concerns do not assign a HEP. Review organizational,
design, communication and latent conditions even without quantitative coefficients.

## 3. Select an evidence path

| Basis | Appropriate path |
|---|---|
| Valid error/opportunity counts | Explicit-prior Beta-Bernoulli estimation, with dependence/missingness review |
| A matching packaged context group | Catalog query, source review, explicit prior and applicability review |
| A justified named method | Reviewed profile or explicitly supplied coefficients |
| An application model | Register a callable returning a compatible `Estimate` |
| Insufficient evidence | Explicit assumptions or justified ranges; no fabricated observations |

An observed simulator count is not a field measurement at your facility. An
expert-scored case probability is not a sample of errors. A multiplier is not a
probability. The catalog enforces several distinctions; substantive applicability
still needs analyst judgment. See [Human-error data](HUMAN_ERROR_DATA.md).

Define target failure, demand, conditioning, domain and timing/recovery scope.
Source conditions remain visible in the returned trace. A simulator-to-process
transfer is marked `research`, without a field-validation claim.

## 4. JSON workflow

```console
human-reliability template case.json
human-reliability schema
human-reliability run case.json --out result.json
```

The template uses illustrative assumptions and refuses to overwrite an existing
file. Edit `task`, `context`, `events` and `models`. Each event needs one model
specification containing method, parameters and available evidence IDs. Unknown
fields, invalid bindings, missing evidence and unsupported schemas are rejected.

Results include the input digest, estimates and qualitative findings. A result
does not acquire empirical plant validity merely because inputs pass validation.

`python examples/evidence_to_risk.py` creates a complete catalog-backed case:

```console
human-reliability run artifacts/evidence_example/case.json --out artifacts/evidence_example/cli_result.json
```

## 5. Python composition and extension

```python
from pathlib import Path
from human_reliability.assessment import AssessmentCase, AssessmentEngine

case = AssessmentCase.model_validate_json(Path("case.json").read_text(encoding="utf-8"))
result = AssessmentEngine().assess(case)
```

`engine.register(name, callable)` accepts a custom estimator. It receives event,
context, evidence and case parameters through `MethodInput`. Return an `Estimate`
for the exact event and conditioning. The registry checks evidence identities and
required timing/recovery scope. Preserve method versions and input/output digests.

Contracts reject unknown fields and nonfinite values. Frozen objects do not make
nested dictionaries deeply immutable. Revalidate imported JSON and do not reuse a
digest after mutation. `canonical_digest` identifies JSON meaning, not arbitrary
runtime object state.

## 6. Response time and recovery

Time observations require start/completion definitions, units, censoring and a
defined population. An unfinished response at a study cutoff may be right-censored;
a completed wrong action is a different failure outcome.

Use lognormal, Weibull, Kaplan-Meier or a qualified custom model. Optional AFT/Cox
regression requires assumptions appropriate to the observations. A nonparametric
unidentified tail is not silently extended beyond its support.

`apply_deadline` combines initial failure with otherwise-correct late completion.
`apply_recovery` uses failure to recover conditional on initial error. Scope flags
prevent applying an already included effect again. Aggregate SACADA UNSAT counts
do not separate lateness and recovery; the worked example locks both flags rather
than assigning another unmeasured benefit.

Separate cue, recognition, diagnosis, command and physical completion times.
Station logic needs a command time; a source-term model may need actual isolation
completion. Assign the same actuator delay only once.

## 7. Frequency and risk

An initiating task error can be converted from probability per demand into an
expected annual count using matching work exposure. Exposure must come from a work
schedule or operational evidence. The released SACADA counts contain no calendar
exposure. `annual_frequency_from_evidence` requires matching opportunity definitions
and marks the result as derived.

FTA evaluates failure combinations. Enumeration supports up to 20 unique events;
optional BDD supports larger Boolean structures. Reuse event identities for shared
events and provide a joint-state distribution when basic events are dependent.
Adding cut-set probabilities is not generally exact.

ETA requires a complete exclusive conditional partition. Allocate initiating annual
frequency once. Automatic success, automatic failure/manual success and both
failures form a partition when manual failure is conditional on automatic failure.

`individual_risk_rate` combines path frequency and receptor-specific harm.
`fn_curve` uses a conditional fatality-count distribution. Supply consequence,
weather, ignition and occupancy under consistent conditioning and include each
once. An annual rate differs from a finite-horizon event probability.

LOPA screening withholds independent multiplication when common dependencies,
missing independence evidence or unestablished response feasibility exist.
Risk-matrix classes remain ordinal.

## 8. Engineering integration

Adapters transform payloads or application-owned objects. They do not send network
requests or operate equipment. Pinned PRISM, DynaSense, monitoring, LH2DT, SAGA,
QSafety and station safety boundaries were checked at documented scopes.

Task-origin PRISM initiators require a receiving extension. The full station
physical/consequence loop needs additional dependency qualification. Contract
compatibility does not establish full plant integration. Read
[Integration](INTEGRATION.md) before connecting applications.

## 9. Uncertainty and alternative models

Separate statistical uncertainty, model uncertainty, context transfer and missing
scenario coverage. A narrow Bernoulli interval does not prove independence or
transportability. Method percentile ranges and control-mode intervals are not
automatically distributions for Monte Carlo sampling.

Use fixed seeds and preserve joint dependence. Copula latent correlations differ
from transformed marginal correlations. The Sobol wrapper requires declared
independent uniform inputs and does not automatically establish convergence.
Repeatedly using one evidence source must not create independent copies of it.

## 10. Preserve a reproducible assessment

Retain input cases, source versions, evidence identities, applicability reviews,
coefficients, uncertainty assumptions, result digests, library versions and checks.
Keep exclusions and unsuccessful assumptions visible. Follow
[Research handoff](RESEARCH_HANDOFF.md) to reproduce this project's records.

Stronger application claims require actual task opportunities and outcomes,
recovery/dependence evidence and qualified physical models. Software tests verify
implementation properties at stated scopes, not every site, crew or protection.
