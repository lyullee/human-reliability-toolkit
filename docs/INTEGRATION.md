# Integration with existing engineering projects

## Risk and process interfaces in version 0.3

`RiskEngine` registers local consequence providers with version/evidence metadata.
`adapters.dynasense_consequence_provider` wraps the actual DynaSense simulator,
checks the declared baseline fingerprint and separates conditional harm from
annual frequency and occupancy. `adapters.risk_scenario_branches` constructs the
existing PRISM `EventBranch` objects from a complete scenario partition. The
integration script exercises both new paths with the pinned real objects.

A continuous process can implement `dynamics.ProcessBackend`: advance to a common
clock, expose observations by role, provide an analyst snapshot and apply completed
commands. Keep the receiving solver's domain and physical invariants. The included
held/linear-state JSON backend is an authored contract example. It is not a
replacement for the station solver or a newly qualified high-pressure/LH2 model.
The older receiving PRISM task-initiator schema limitation still applies.

Adapters produce payloads or application-owned Python objects. They perform no
HTTP requests and do not execute equipment commands. External model code is not
copied into the distribution.

## PRISM

`prism_demand(estimate, demands_per_year, factory=DemandFailure)` validates against
PRISM's existing demand contract. `prism_branches` can construct `EventBranch`
objects for a complete exclusive partition. Those interfaces were exercised using
`prism-risk==0.6.8`.

`human_initiator` exports a separate `human_reliability.initiator.v1` contract with
task, component, release binding, rate and provenance. Its
`requires_prism_initiator_extension` is true. PRISM's literature-only
`FrequencyEvent` must not be filled with a false literature basis or equipment-year
unit to admit an empirical task event. Implement an explicit receiving extension.

Initiating errors and response barriers have different positions in the event
model. Check whether generic equipment frequencies already include operational or
maintenance causes before adding an independent human initiating rate.

## PRISM DynaSense

`dynasense_scenario` updates only `isolation_time_s`, validating through the supplied
Scenario class. A missing completion uses an explicit time beyond the assessment
horizon. The human evidence remains outside the strict physical input object.

The actual pinned Scenario and simulator were run at 5, 10, 20 seconds and no
isolation during the horizon. Source histories were recomputed, not rescaled.
The bounded example released approximately 0.09757, 0.15246, 0.25275 and 0.39694 kg.
This is an ideal isothermal hydrogen screening example within DynaSense's declared
domain. Conditional thermal harm is not annual accident probability. Check the
external project's current pressure, temperature and geometry boundaries.

## Hydrogen station simulator

`station_stop_requested(time_s, timeline)` maps the command time of a correct manual
response to `SafetyPLC.update(..., emergency_stop_requested=...)`. A wrong action
does not create a stop request. Physical valve completion remains the station
model's responsibility; do not impose the same actuator delay in two places.

The actual SafetyPLC submodule was loaded under an isolated package namespace,
with its actual protocol and property-wrapper submodules. A manual request was
checked to latch shutdown at the declared command time. The full station physical
loop, native consequence backend and an actual operator were not exercised.

The existing automatic safety path remains independent in software. Model common
sensors, power and actuators before assigning probabilistic independence to manual
and automatic protection. A good automatic trip must not be removed merely to make
human lateness affect a demonstration.

## Monitoring and LH2 observations

`monitoring_context` accepts a DetectionResult-like object and preserves validity,
score, threshold and alarm meaning. It does not map an anomaly score to HEP. The
actual public monitoring data class was checked.

`observation_series` accepts LH2DT's `ObservationTable` protocol and an explicit
channel, unit, clock and origin. The actual source-pinned 0.1.2 object was checked,
including an invalid observation. Keep measurements, process-model predictions,
virtual detector proxies and injected fault truth separate.

## SAGA

`saga_context` attaches a structured assessment to the current
`DigitalTwinHazopRequest.context_text` field. A factory can validate the request
against SAGA's actual class. This targets the HAZOP evaluation boundary, not a
numeric HEP generation endpoint. SAGA may explain assessment evidence or propose
analysis candidates; it does not own the deterministic probability calculation.

The source review records a legacy station path `/api/digital-twin/hazop/direct`
that differs from the current `/api/digital-twin/hazop/evaluate` route. Resolve this
in the connecting application before a service exchange. Contract checks do not
establish endpoint availability or operator-effectiveness benefits.

## QSafety and other projects

`qsafety_frequency_mixture` preserves the total annual frequency while normalizing
scenario weights for QSafety's probability model. Its exact weighted rate was
checked against the actual `RiskDistribution` class. Quantum estimation operates on
an already defined probability model and does not supply missing human evidence.

`psa_trace` selects a declared process channel and cumulative seconds from a cycle
trace. Repeated cycle-relative clocks are rejected. PSA traces remain process
simulation, not measured human behavior. Ammonia studies can consume the same ETA
ledger and mutually exclusive path probabilities; material screening multipliers
are not human-error multipliers.

## Reproduce the external checks

```powershell
python -m pip install --no-deps --target artifacts/integration_packages "prism-risk==0.6.8"
python -m pip install --no-deps --target artifacts/integration_packages "lh2dt_models @ https://github.com/lyullee/lh2dt_models/archive/b2f276333c1b1793c39f25763703d196d36742ec.zip"
python scripts/check_integrations.py
```

The script retrieves the pinned public Python modules into ignored artifacts and
records their digests in `research/integration_checks.json`. Inspect external source
before changing pins. These imports execute Python modules from the user's public
projects; use the same care as installing any dependency.

The full installed environment is not a common environment guarantee. The reviewed
station consequence dependency caps SciPy below 1.16, while this recorded research
environment uses a newer SciPy. The isolated safety contract does not exercise that
native path. Use separate compatible processes/services or resolve the full version
intersection for a complete station integration.
