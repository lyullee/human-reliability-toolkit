# Architecture and model boundaries

## Measured-data boundary in version 0.4

`field_data` separates physical measurements, investigator-coded incidents and
human task-opportunity observations. Original timestamps and raw malformed cells
remain available; numeric views carry an audit and unknowns. Measured state/context
bindings exclude evaluation labels. Assumed clocks have a separate identity.

`field_validation` owns metric arithmetic and causal sample-alarm replay.
`field_studies` owns an explicit prediction design and keeps fitted values labeled
as model estimates. Source conditions and rights travel with the field metadata.
These components do not insert a process anomaly or accident-case proportion into
a human failure event. See [Field validation](FIELD_VALIDATION.md).

## Operational composition in version 0.3

The existing typed assessment and numerical modules remain the foundation. The
new execution layer binds a command to a capability/state update. The causal
layer references existing estimates and compiles explicit logic into the shared-
event FTA engine. `RiskEngine` resolves an assessment, causal graphs, exposure,
conditional branches and registered consequence metrics into one ledger.

`ProcessBackend.snapshot()` belongs to analyst/physical evaluation;
`observe(role, time)` belongs to the decision policy. The scheduler advances
physics before decisions and completed commands, preserves remaining work after
preemption, and supplies role-visible history. Retry rules are explicit rather
than driven by hidden success. Interventions preserve original evidence and
construct an assumed alternative. Operational observations preserve missingness
and recovery before any count update.

Finite progress/deadline verification, declared diagnostic models, finite-grid
statistical inference and assurance lifecycle checks consume the same IDs and
provenance. None automatically validates the physical or cognitive meaning of a
user-supplied model. See [Operational extensions](OPERATIONAL_EXTENSIONS.md).

Version 0.2.0 adds typed source/rights records, numeric records linked by source ID
and a SACADA categorical codebook. Bundled JSON uses core dependencies; optional
source readers do not execute during ordinary catalog queries. Numeric profiles
retain the distinction between observations, complete probabilities, components,
modifiers and placeholders.

Binding evidence requires domain/scope review and preserves source and target
definitions separately. Exposure conversion checks the target demand definition
and labels its output as derived. The engine can receive a custom catalog and
uses its existing evidence/result guard for catalog estimates.

The library separates task meaning, evidence, probability calculation, temporal
behavior, physical consequences and risk aggregation. Each layer has a different
observation unit. A monitoring alarm, a task demand, a wrong command, a failed
actuator and a harmful consequence must not share one undifferentiated label.

## Data flow

```mermaid
flowchart LR
    A[Procedure and observed work] --> B[Task graph and deviations]
    C[Context and evidence] --> B
    B --> D[Defined human failure events]
    D --> E[Estimator registry]
    E --> F[Recovery dependency and timing]
    F --> G[FTA ETA and barrier screening]
    F --> H[Action and completion timelines]
    H --> I[External process and release providers]
    I --> J[External consequences]
    G --> K[Frequency and risk ledger]
    J --> K
    B --> L[Explanation and evidence service]
    E --> L
```

`contracts` defines strict Pydantic records and canonical JSON hashing. Frozen
models prevent field reassignment but nested dictionaries are not deeply immutable;
applications should construct a new case for a changed assessment and recompute its
digest. JSON versions are checked before evaluation. Python constructors use strict
container types; JSON readers use `model_validate_json`.

## Calculation ownership

The core owns probability arithmetic and checks. A method adapter owns the mapping
from assessed context to coefficients. The caller owns data eligibility and the
failure/opportunity definition. External process models own mass, energy, inventory,
release geometry and actuator dynamics. Consequence models own exposure and harm.
PRISM or another risk application owns initiating-frequency assembly and facility
aggregation. SAGA owns retrieval and prose generation; it is not a numeric oracle.

The supplied cognitive chain is a sequence of first-failure probabilities conditioned
on preceding stages succeeding. Its product of conditional successes does not
assert marginal independence. A scenario mixture requires exclusive contextual
weights summing to one. A Bayesian network can model shared causes explicitly.

## Timing and simulation

`simulate_task` schedules a task DAG with role capacities. Failure callbacks receive
only outcomes completed before the current start time. Callback consequence replay
is ordered by completion after the episode has been scheduled. It is an open-loop
event generator, not a synchronized closed-loop cognitive/plant co-simulator.
For feedback that changes later human decisions, use the separate
`dynamics.run_coupled_episode` runtime with an explicit process backend and
role-visible policy inputs. The two schedulers retain their distinct semantics.

Deadlines are absolute episode seconds. Completion-time distributions apply only
under their declared failure conditioning. A terminal wrong action cannot be made
into an ordinary right-censored success time. Unidentified survival tails remain
unavailable in the nonparametric model.

## Boolean and temporal logic

Fault-tree event identity is preserved by exact state enumeration or the optional
`dd.autoref` BDD backend. These evaluate a static Boolean expression over distinct
events. Chronology is represented by task/timeline and workflow models. No ordered
dynamic gate is silently approximated by a static AND.

`WorkflowNet` explores token markings under explicit transitions and capacities.
An exhaustive finite search can pass a specified property. A reached state limit
produces an incomplete result. Neither result proves omitted real-world transitions
safe. `SafetyCase` records support dependencies and propagates changed evidence
through claims; it does not automatically certify those claims.

## Extension points

- Add `DeviationRule` records or replace the JSON case's rule tuple.
- Register an `Estimator` accepting `MethodInput` and returning `Estimate`.
- Supply any `TimeModel` with `cdf` and `sample` under consistent semantics.
- Supply conditional probability tables or an external inference implementation.
- Consume action outcomes through a consequence replay callback.
- Use object factories in adapters to validate against an external project's types.
- Keep source licenses and units in the application-owned evidence registry.

Imported models and schemas are pinned in integration checks. No external source
is shipped inside the package. Optional services retain separate dependency
environments when their numerical/native requirements conflict.
