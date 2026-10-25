# Methods and applicability

The library implements reusable mathematical components. A method name does not
establish that its coefficients describe a particular process, workforce or site.

## Estimation and evidence

Declared estimates preserve the supplied probability and evidence. Empirical
estimates use a Beta prior with Bernoulli error/opportunity counts. The posterior
parameters are `alpha + failures` and `beta + opportunities - failures`. Intervals
are equal-tail credible intervals for that model. Repeated operators, missing
errors, selective reporting and changing tasks require additional analysis.

Context-conditioned cognitive stages can include detection, understanding,
decision, action and coordination. Each failure probability is conditional on the
earlier stages having succeeded. The returned first-failure contributions partition
the overall failure. This is a configurable cognition-informed chain, not the
official IDHEAS-ECA data and quantification system.

## Legacy method adapters

Version 0.2.0 adds attributed numeric profiles and case references through
`reference_methods` and `evidence_catalog`. The low-level arithmetic functions
remain usable with caller-owned parameters. See [Human-error evidence](HUMAN_ERROR_DATA.md)
for source scope, quantities and licensing.

The SPAR-H arithmetic adapter uses the publicly documented diagnosis/action nominal
values, requires all eight factor names, and uses bounded normalization when at
least three factors are adverse. The caller supplies reviewed factor values. An
explicit insufficient-time condition gives failure probability one after validating
the inputs. Dependency is applied separately under the correct conditioning.

The HEART arithmetic adapter accepts a nominal probability and maximum-effect /
assessed-proportion pairs. It evaluates the supplied effect combination and exposes
the uncapped value. No commercial task catalogue, descriptive table or application
qualification is distributed. The generic multiplier function also supports a
bounded-odds model, which must not be described as the same method for every input.

THERP/SPAR-H conditional dependency formulas are available for zero, low, moderate,
high and complete levels. Selecting a level requires analysis of shared personnel,
time, location, cues and procedures. A level is not a numerical correlation.

## Recovery and time

Recovery retains initial errors that are not corrected. Time evaluation retains
initial failures and otherwise-correct responses that do not complete by the
deadline. The result records which effects are already included, preventing a
second application of the same recovery or timing operation.

Response models include lognormal, Weibull and Kaplan-Meier. Optional lifelines
models support censored Weibull fitting, Weibull accelerated failure time regression
and Cox proportional hazards regression. Censoring must be correctly distinguished
from terminal failure and from missing data. Parametric tails and proportional
hazards require evidence; the library does not validate these assumptions itself.

## Dependencies and risk

Static FTA evaluates AND, OR, NOT and voting gates without duplicating a shared
event. Exact inference under joint states supports dependent events. The small
Bayesian network implementation validates complete conditional tables and enforces
a state-space budget. It provides conditional inference, not causal identification.

ETA multiplies probabilities along a conditional path and conserves initiating
frequency. LOPA screening withholds independent layer multiplication when common
dependencies or response feasibility are unresolved. Risk matrices remain ordinal.
Annual rates are distinct from interval event probabilities; Poisson conversion
requires its stationary rate and declared horizon.

## Workflows and resources

Task graphs support prerequisites, roles, deadlines and latent hazards. Petri-net
reachability can expose unsafe task variants and deadlocks within a specified
model. Attention allocation minimizes caller-supplied cost functions under an
effort budget using constrained optimization. It provides no universal fatigue,
training or workload-to-HEP coefficient and makes no global-optimality claim.

## Uncertainty and sensitivity

Uniform, triangular, beta and lognormal marginals can be sampled with a fixed seed.
An optional Gaussian copula uses a latent correlation matrix; this is not generally
the Pearson correlation of the transformed marginals. Shared uncertain causes
should reuse a joint draw rather than be sampled independently for each branch.

SALib provides Sobol first/total-order indices for explicitly independent uniform
inputs. The wrapper rejects unqualified independence, constant outputs and invalid
design sizes. Bootstrap index intervals do not by themselves establish numerical
convergence. Correlated inputs require a different sensitivity formulation or
explicit scenario comparisons.

## Current method review

The `idheas_cfm_probability` kernel implements equations 3.4/3.5 for one cognitive
function, with explicit base inputs and additive excess modification weights.
It does not implement the entire IDHEAS-ECA workflow, PIF selection, HFE
aggregation or timing. Packaged 1.1/1.2 placeholders remain labeled. The older
conditional cognitive chain remains a different model and must not be identified
as the official IDHEAS-ECA calculation.

[NRC NUREG-2256](https://www.nrc.gov/regulations-legislation/nureg-series-publications/publications-prepared-by-nrc-staff/sr2256)
documents cognition-based IDHEAS-ECA. The 2021 general methodology and the 2022 ECA
method motivate explicit event/context structure rather than a single context-free
probability. Their complete data/model system is not claimed here.

[INL's HRA programme](https://lwrs.inl.gov/risa-reports/) and its
[2025 Rancor-HUNTER report record](https://inl.elsevierpure.com/en/publications/rancor-hunter-using-a-simulator-engine-for-realistic-human-perfor/)
show the value of coupling human events with plant dynamics. This project supplies
interoperable event/timeline boundaries; it does not claim to reproduce HUNTER.

[SPAR-H NUREG/CR-6883](https://www.nrc.gov/regulations-legislation/nureg-series-publications/publications-prepared-by-nrc-contractors/cr6883)
is retained as a transparent comparison adapter. Newer methods are prioritized
when they add usable evidence and verified capability. Novelty alone does not
justify a more accurate HEP claim in another industrial domain.
