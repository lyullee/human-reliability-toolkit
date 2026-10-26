# Extension acceptance and validation record

Version 0.3.0 implements twelve bounded operational modeling capabilities. The
requirement/status matrix is `research/extension_implementation.json`. The
generated acceptance record is `research/extension_validation.json`; it links
successful JUnit cases to the verified source set. Numerical and state-machine
verification does not establish field calibration of a cognitive or physical model.

## Acceptance cases

| Requirement | Implemented acceptance evidence | Qualification |
|---|---|---|
| G01 | Wrong-target command changes the actual alternate valve; the intended valve stays unchanged. Unknown safety information withholds, and an unknown enabled interlock blocks. Capability/unit limits and mutation budgets reject invalid cases. | Atomic state-command semantics, not complete plant dynamics |
| G02 | Repeated-event identity is exact; fully dependent joint failures differ from independent multiplication; joint marginals, conditioning, cycles, effect duplication and expansion limits are checked. | User-specified causal structure and dependence evidence |
| G03 | An independently calculated demand/harm/occupancy case reproduces frequency, individual risk, loss and F-N outputs; JSON replay agrees; unknown exposure/provider results remain explicit. | No automatic facility initiating-rate or consequence calibration |
| G05 | Wrong-recipient, receipt-only, incorrect interpretation and expired messages cannot authorize commands. Personal lock ownership, stale handovers, incompatible work and restoration closeout are checked. | Modeled protocol/authorization records |
| G06 | Recovered initial error counts differ from unrecovered final counts; unknown outcomes stay missing. Repeated/overlapping exposure and late recovery are rejected. Annualized demand exposure includes known demands with missing human outcomes. | Observation coverage, selection and stationarity require review |
| G07 | An intervention leaves its baseline unchanged, preserves source estimates, replaces empirical labels for assumed overrides and clears stale fitted uncertainty. Paired constant differences and analytic OR-tree importance are reproduced. | Model contrasts do not identify field intervention effects |
| G04 | A prior valve action changes pressure before the next decision. Higher-priority work interrupts/resumes remaining work. Completion on the horizon, explicit retries and model clock partitioning are tested. Policy inputs exclude hidden injection parameters and actual wrong-target truth. | Atomic completion, explicit role observations and supplied process model |
| G08 | An available exit does not prove inevitable completion when a self-loop remains possible. Possible/all-path deadline results differ; zero-time cycles, state bounds, exact deadline boundaries and DAG fan-out are tested. | Finite untimed nets or serial atomic integer-time firings |
| G09 | Delayed/role-hidden cues cannot be read early or by another role; posterior updates match a simple analytical Bayes result; duplicate evidence, ties and dwell-time capacity are checked. | Declared diagnostic model, not validated operator cognition |
| G10 | One-point hyperprior matches an independent beta posterior and its interval. Group/domain guards, held-out Brier scores, fit error for known beta quantiles, expert seed weighting and seeded predictive draws are checked. | Explicit finite hyperprior and review of exchangeability/transfer |
| G11 | Trace checks detect wrong target, stale version, missing predecessor and omission; incomplete observation stays unobserved. Assumption expiry propagates to a supported claim; assurance JSON round-trips preserve the review result. | Review propagation, not automatic semantic approval |
| G12 | SPAR-H stage/recovery combination matches an independent expression; evidence-bound native assessment agrees. HEART conditional dependence is labeled, IDHEAS source floors/placeholders are checked, and CREAM range selection remains explicit. | Selected numerical workflows; no full IDHEAS/extended-CREAM system claim |

The primary new tests are
[`test_execution_risk.py`](../tests/test_execution_risk.py),
[`test_operational_extensions.py`](../tests/test_operational_extensions.py) and
[`test_dynamic_workflows.py`](../tests/test_dynamic_workflows.py).
Existing regression tests remain part of the full suite. Warnings are treated as
errors and the verification record retains failures/errors/skips separately.

## End-to-end execution and existing-project checks

[`operational_research.py`](../examples/operational_research.py) demonstrates the
connected features using original scenarios, explicit statistical assumptions
and one source-qualified SACADA count row. It writes an input risk case,
intervention and result under ignored artifacts. The command-line replay consumes
that saved case. Three additional packaged templates exercise the ordinary
risk, method-workflow and coupled runners.

The existing integration check still exercises eight actual object boundaries.
It now also registers the real pinned DynaSense solver as a RiskEngine consequence
provider, checks the baseline fingerprint and compares the resulting annual risk
rate with the solver's conditional harm output times the declared initiating rate.
The resulting partition is constructed as real PRISM `EventBranch` objects.
This additional check does not qualify the full station dependency environment or
add a receiving PRISM human-initiator implementation. See
[Integration](INTEGRATION.md) for pins and physical-domain limits.

## Corrections retained during development

The first finite-grid sensitivity assertion compared entire summaries even though
the review text intentionally differed. It was corrected to compare the numerical
result while preserving the different provenance. Numerical agreement must not
discard an application review.

Review also identified two ways a dynamic model could acquire unrealistic
information. Actual injected commands were separated from perceived command
history, and a dedicated public task view replaced the full job/injection
configuration in policy inputs. Automatic retries based on hidden success were
replaced by explicit repetition or an observed retry callback. A counterexample
with a forced wrong-target injection now checks that the next policy sees the
perceived original command rather than the hidden actual target.

Intervention review found that an overridden probability could otherwise retain
an empirical status and its old beta uncertainty. The alternative now records an
assumed intervention, preserves the original estimate in its trace, and removes
the stale fitted distribution. Observed count fields cannot be rewritten through
the intervention interface.

Consequence-provider failure was separated from missing event frequency. A known
frequency survives an unavailable harm provider, while harm remains withheld.
Missing exposure still withholds frequency. A handover fingerprint uses JSON
meaning of state facts rather than attempting to serialize nested model objects
as ordinary Python values.

## Reproduction and release checks

The first extension clean-install check used exact equality for a nominal workflow
probability of 0.001. Conditional-success arithmetic returned
0.0010000000000000009. The install assertion now uses an explicit absolute
tolerance of 1e-12, consistent with the independently calculated risk check.
This correction changes the numerical assertion, not the model or its parameters.

```console
python -m pip install -e ".[data,curation,learning,survival,thermo,sensitivity,bdd,dynamics,dev]"
python scripts/run_verification.py --integrations
python scripts/record_extension_validation.py
python scripts/inventory_environment.py
python scripts/build_release.py
```

The integration option requires the external targets. Ordinary CI runs the core
software, all optional research tests, executable documentation examples and the
three extension CLI cases. The release gate verifies the source/data/documentation
hash set before compiling distributions. `record_extension_validation.py` refuses
stale verification and requires the named acceptance cases and executed example.
The build script runs it before packaging.

Archive inspection excludes raw publications, spreadsheets, participant data,
source caches, environments and credentials. Clean-wheel testing loads the entire
numeric catalog and executes the risk and method workflows in an isolated core
environment where optional numerical/data/scheduler libraries are absent. The
coupled runner is exercised in the full environment with `[dynamics]`.

Final pass counts, environment versions, source hashes, integration pins, package
inspection and clean-install records are retained in `research/`. The emitted
acceptance report is generated after software verification. Build and install
reports do not recursively hash themselves into the source archive.
