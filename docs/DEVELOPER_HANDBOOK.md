# Developer handbook

## Extending operational models

Read [Operational extensions](OPERATIONAL_EXTENSIONS.md) and
[Extension validation](EXTENSION_VALIDATION.md) before changing execution semantics.
Keep unknown, blocked, omitted, attempted and physically completed states distinct.
A predicate name is not an executable precondition. Keep alternative causes
separate from within-mechanism modifiers and preserve shared-event IDs.

A process backend owns continuous physics; the scheduler owns time/resource order.
Policy inputs must contain visible information and public task data only. Preserve
perceived versus injected commands, and require an explicit observed retry rule.
A deterministic replay proves the configured model's behavior, not operator
performance. New inference needs a defensible population/denominator and independent
validation. An assumed intervention cannot inherit an empirical label or fitted
posterior from its baseline.

Update the requirement acceptance map in `scripts/record_extension_validation.py`
when a scope changes. Its source-hash guard and named JUnit cases prevent a stale
implementation matrix from serving as current acceptance evidence.

## Code map and extension rules

The import package is `human_reliability` under `src/`. Contracts and estimation
are independent of external engineering projects. Optional data, thermodynamic,
learning, sensitivity and BDD dependencies load at their use boundary. An adapter
may accept a caller factory to construct the receiving project's real object.
Do not import downloaded project source from the distributed package.

For a new estimator, register a callable accepting `MethodInput` and returning
`Estimate`. Read `request.parameters` for case-level configuration, `context` for
declared conditions and `evidence` for provenance. Preserve event identity and the
exact conditioning definition. Record whether time and recovery are included.
The registry rejects incompatible results. Use new names rather than silently
changing an established method's mathematical meaning.

For a new dataset, add its source, immutable version, creators, terms and intended
grain to `research/datasets.json`; then add acquisition and parser support. A
source's equipment failure labels cannot be renamed as human failures. Preserve
native units until an authoritative conversion is available. Keep unsupported
objects explicit and retain invalid observations rather than filling them healthy.

For a new receiving project, document the source pin and field meanings. Test the
actual object when available. Distinguish a payload schema from a fully exercised
runtime. Never send a live command or call a remote service in a unit test.

## Numerical review

Specify the estimand before coding: conditional probability, joint probability,
rate, ordinal category or response-time distribution. List conditioning events,
exposure units, dependence, censoring, missingness and uncertainty assumptions.
An annual rate can exceed one; a probability cannot. Distinct FTA occurrences of
the same event must share identity. Conditional ETA sibling branches must close.

Use an analytical limiting case or independent implementation for substantive
numerical changes. Include a counterexample for a discovered failure mode.
Avoid tests that merely repeat the same expression as the implementation. Check
invalid input handling when it could create a plausible but wrong risk result.

## Local development sequence

```console
python -m pip install -e ".[data,learning,survival,thermo,sensitivity,bdd,dynamics,dev]"
python -m ruff format src scripts tests examples
python scripts/run_verification.py
python scripts/inventory_environment.py
python scripts/build_release.py
```

Use `--integrations` after installing the pinned external targets when changing
adapter behavior. Data research changes additionally require the relevant audit
and frozen study rerun. Keep any failed experiment and explain the protocol change.
CI runs the public software checks without downloading participant datasets or
external source projects.

`scripts/verification_inputs.py` defines the shared verification/release input
set: Python, packaged JSON, case specifications, primary Markdown documentation,
package metadata and CI/build configuration. Release preparation rejects changed,
added or removed inputs until checks run again. Metadata and documentation still
require semantic review and archive inspection; a matching hash is not semantic
review. The release audit rejects raw-data extensions, cache/environment folders,
workstation paths, unexpectedly large files and common credential-like literals.

## Evidence catalog maintenance

Use `docs/HUMAN_ERROR_DATA.md` for the catalog schema, source acquisition and
curation commands. Add rights and attribution before numeric records. Review the
observational unit, failure definition, missing values, duplicates and original
table boundaries. Keep observed counts separate from expert case estimates and
method coefficients. A method multiplier or source placeholder is not a complete
HEP. A count without its opportunity denominator is not a HEP.

Pin acquired files in `research/human_evidence_assets.json`, retain the review
decision in `research/human_evidence_review.json`, and update the independent
curation code and audit. Run curation before software verification. Keep raw
publications and source spreadsheets in ignored raw storage. Preserve attribution
and conditions in `DATA_LICENSES.md`; the software MIT license does not replace
source-specific terms. Never infer annual exposure from simulator trial counts.

## Research change record

Update `CHANGELOG.md` for externally visible behavior. Add important design
decisions and discovered errors to `docs/DEVELOPMENT_LOG.md`. Update method scope,
the capability matrix and API examples when a component changes. Do not turn an
unqualified or censored result into zero to simplify downstream code.

Preserve the frozen split and protocol digest for the current study. A new model
selected after seeing test results requires a new independent evaluation before
a stronger claim. Production integration needs task/domain qualification beyond
the software checks in this project.
