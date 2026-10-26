# Development record

## Version 0.4.0 public-data evaluation

Three additional reusable source families were acquired: measured continuous
chemical distillation, measured steel energy, and released coded rail accident
cases. The earlier turbine archive and simulator count catalog support additional
held-out evaluations. New files remain outside the source publication boundary;
original source metadata, checksums and aggregate results are retained.

The protocol fixed predictors, splits, estimators and metrics before fitting.
Strict ingestion exposed day-ending midnight labels, a fractional phase label and
boolean text in a mass-flow field. The explicit clock interpretation, numerical
missingness view and annotation audit preserve original values. Repairs and partial
runs are retained, including a warnings-as-errors constructor correction.

The steel forecast improves on persistence, while the ambient-only turbine model
is worse than its mean baseline. Monitoring performance and four of five context
models also fail to support an accuracy improvement. Parameters were not tuned on
these outcomes. None of the process/incident datasets establishes chemical-plant
HEP accuracy or an annual human-error frequency. The English field manual records
the full scope and reproduction steps.

## Version 0.3.0 operational extension

Twelve composable modeling areas were implemented with parameterized contracts,
Python APIs, JSON runners, original scenarios and explicit computational scopes.
The numerical catalog was retained rather than expanded with unreviewed field
values. A reported-observation schema preserves evidence whose exact denominator
is unavailable. The only new optional runtime dependency is MIT-licensed SimPy.
Finite-hyperprior inference uses the existing NumPy/SciPy backend.

Execution review retained the distinction between nominal task structure and
actual command effects. False/unknown enabled permissives block execution, while
a reviewed unsafe attempt remains distinct. Causal graph conditioning and shared
failure scopes are checked. Missing exposure cannot become zero annual frequency.
Missing consequence providers do not erase otherwise identified frequency.

Dynamic review separated analyst truth from observable state. Public task views
exclude injected error parameters. Perceived command history is stored separately
from actual deviations. Bounded repetitions and observed retry policies replace
retries based on hidden success. Preempted work retains its remaining duration.

Intervention review corrected retention of an empirical label/old posterior after
an assumed probability override. Calibration tests preserve different review text
when comparing identical numerical results. Formal checks distinguish possible
completion from all-path progress and reject zero-time-cycle deadline proofs.
Assurance snapshots preserve claim/evidence structure for later sessions.

The detailed acceptance record and execution history are in
[Extension validation](EXTENSION_VALIDATION.md) and generated research reports.

## Version 0.2.0: evidence catalog and English handoff

Eighteen additional human-reliability evidence candidates were reviewed. Seven
sources were selected for numeric curation. The earlier deferred SACADA entry
was superseded after the public April 2019 spreadsheet release was acquired and
checked. Its 578 records are function/context training aggregates with explicit
UNSAT and opportunity counts. They are not chemical-plant field failure rates;
overlapping functions cannot be pooled as independent trials.

The 1,334-record catalog separates observed counts, method probabilities, ranges,
base components, multipliers and rules. Binding requires an application review;
observed counts additionally require an explicit prior. Incomplete method
components and placeholders cannot be bound directly as HEPs. Annual conversion
requires a matching target opportunity definition and exposure evidence.

Numeric source review retained exceptions instead of repairing them silently:
the published HEART task E interval is reversed and was withheld; IDHEAS-ECA
1.1/1.2 entries remain placeholders, and WP3 retains its expert-elicitation
qualification. Review corrected the ECA communication-complexity extraction to
all four levels. Noncommercial/no-derivatives material was excluded from the
adapted numeric catalog. NRC contractor material is treated as numeric facts
with attribution rather than assigned a blanket government-work license.

Reference-profile helpers were added for SPAR-H, HEART and a single-function
IDHEAS-ECA arithmetic kernel. None reproduces an entire official analysis system.
An exact-filter ordering defect was corrected so a valid unmatched condition
does not cause another valid filter to be rejected. The evidence example now
derives manual-demand exposure from the same initiator and automatic-layer
probability used by its event tree.

The README, user guide, evidence manual and mixed-data notices were written in
English. Curation, verification, clean-wheel installation and release inspection
are reproducible scripts. The release gate now hashes packaged JSON and primary
documentation/configuration as well as Python. Changes to these inputs require a
new verification record before release preparation.

## 2026 10 26

The package was organized around tasks, evidence and defined human failure events.
The initial design separated error form, potential cause, latent condition, recovery,
timing and consequence. Parameterized qualitative reviews cover organizational and
design issues without inventing universal probability multipliers.

Fifteen data families were considered and nine acquired. Existing verified public
archives were reused where hashes matched; additional complete simulated-process
assets and human experimental data were acquired from primary repositories.
COG-BCI behavioral members were fetched by validated ranges to avoid downloading
unneeded electrophysiological signals. The first pass encountered source throttling;
server backoff and lower concurrency completed the remaining cached subsets.

Data inspection found a mismatch between the control-room study overview and the
released participant/log coverage. It also found scenario-level rather than
task-opportunity records, unresolved time units and a non-probability Accuracy field.
Those semantics were preserved in the catalog and audit rather than normalized into
an invented HEP dataset.

The COG record has nested duplicate subject wrappers in most archives. A first
fixed-position path interpretation obscured session identities. The parser was
changed to identify explicit subject/session components, and a nested-wrapper
regression test was added. The actual PVT flag vectors are identical across all 87
sessions, with the only positive value at ordinal 8. A candidate flag-rate analysis
was rejected for HEP calibration. The initial output is retained with a rejection
status and re-entry condition.

A pure-Python MIT RData reader was selected for the distributable data extra,
replacing an investigated AGPL reader. External data and code remain outside
source releases; the library uses optional dependencies rather than copying them.

Probability, dependence, recovery, timing, FTA, ETA, Bayesian inference, task
scheduling, Petri-net checking, attention allocation and barrier screening were
implemented as separate components. A registry accepts application methods and
per-case parameters. Builtin methods and plugins obey the same event, conditioning,
evidence and scope checks.

The first 27-test run exposed BDD shutdown warnings. Recursive closures and memo
keys kept decision-diagram nodes alive through a reference cycle. References are
now released before manager cleanup; tests run with warnings treated as errors.
The expanded suite covers additional adapters, survival models, source parsing,
barrier dependence and end-to-end JSON behavior.

The task simulator originally exposed outcomes of already scheduled but not yet
completed tasks to a conditional failure callback. It now passes only completed
history and replays consequences in completion order. A regression test checks both
causality and ordering. The simulator is documented as an open-loop episode
generator rather than a full feedback co-simulator.

Source-pinned integration checks exercised existing engineering objects. Initial
DynaSense import failed because its facade also imports sensitivity code; the
source set was completed rather than bypassing the original package facade.
Physical examples recompute source histories for different completion times.
The isolated station safety-module test does not invoke the native consequence
runtime or claim a compatible full station dependency environment.

User, API, method, data, integration, verification, licensing and handoff documents
were written alongside the implementation. Source-only build and distribution
inspection scripts prevent raw external data, source caches, workstation paths and
credential-like literals from entering the inspected packages.
