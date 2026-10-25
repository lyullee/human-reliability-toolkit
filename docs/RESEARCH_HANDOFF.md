# Research handoff

This repository is the complete public-source research boundary for version 0.2.0.
It contains implementation, tests, examples, provenance and development records.
External data, downloaded external source, environments and build logs are ignored.
No private session history is needed to reproduce the documented steps.

## Orientation

Start with `README.md`, `docs/USER_GUIDE.md` and `docs/HUMAN_ERROR_DATA.md`.
The Korean documents retain the initial implementation walkthrough. Follow `docs/API.md` for
composition and estimator registration, `docs/ARCHITECTURE.md` for contracts and
`research/capabilities.json` for exact scope. `docs/PLAN.md` defines milestones;
`research/progress.json` records their implementation status and evidence.

The test environment versions are in `requirements-validated.txt` and
`research/environment.json`. These describe one Windows Python 3.12 environment,
not a universal lockfile. Install from `pyproject.toml` on another platform and
record a new environment rather than silently replacing the validation record.

## Reproduce from a fresh checkout

```console
python -m venv .venv
# Activate .venv with your platform's shell command.
python -m pip install -e ".[data,curation,learning,survival,thermo,sensitivity,bdd,dev]"
human-reliability doctor
python examples/python_api.py
python examples/evidence_to_risk.py
python scripts/acquire_human_evidence.py
python scripts/curate_human_evidence.py
python scripts/acquire_data.py
python scripts/audit_data.py
python scripts/run_studies.py
python examples/process_context.py
python scripts/inventory_environment.py
python scripts/run_verification.py
python scripts/build_release.py
```

The bundled evidence catalog works offline; reacquisition and curation are
optional reproducibility steps. The 13 pinned evidence assets include SACADA
training aggregates and method publications. Some primary sites may require
ordinary browser downloads; see `docs/HUMAN_ERROR_DATA.md` for the checksum-checked
import path. Do not bypass access controls or replace a failed download with an
unverified mirror.

Process-data acquisition may take substantial network time. Those selected assets
total about 1.705 GB. COG downloads only selected behavior members using validated HTTP range
requests; the approximately 31.7 GB source archives are not acquired in full.
Member CRC/SHA and local subset hashes are distinct from full archive checksums.
Use `--only` for a named data family when iterating. Never assume a synthetic
process fault or equipment failure is a human error label.

`run_verification.py --integrations` additionally requires the pinned external
targets described in `docs/INTEGRATION.md`. Inspect that file for its isolated
module loading and full-station limitations. Integration failure caused by an
upstream change calls for a new pin/contract review; do not bypass the check by
dropping fields or inventing a compatible event type.

Build output is under `dist/`. `research/release_audit.json` inspects the built
archives. `research/install_smoke.json` records an independent core-wheel install.
Those reports are generated after the build and are retained in the checkout;
they do not recursively include hashes of themselves in the source archive.

## Reproduce a configurable case

```console
human-reliability template case.json
human-reliability schema
human-reliability run case.json --out result.json
```

Replace assumed values with justified parameters and evidence. The stable handoff
is task + event definition + conditioning + evidence + method parameters. Context
can carry workload, procedure, automation, communication and process conditions;
their numerical effect comes from a declared estimator. Do not add a generic
multiplier merely because a context field exists.

## Retained results and failed assumptions

`research/protocol.json` freezes split rules and metrics after schema inspection
and before fitting. `research/study_results.json` retains HITL held-out performance
and monitoring-response quantile coverage. Rejected PVT diagnostics remain in
`research/retained_experiments/`, with the exclusion decision recorded in
`research/protocol_deviations.json`. Preserve these even if a later analysis is
more favorable. Never tune repeatedly on this holdout and call it independent.

## Next research gates

1. Obtain task-level opportunities, completed/wrong/missed responses, participant
   identities, cue onset and time-unit definitions under appropriate data rights.
2. Resolve COG flag semantics and response denominators with authoritative source
   information before considering HEP calibration. Do not reinterpret trial 8.
3. Create a new untouched holdout or prospective study before comparing new
   predictors, hierarchical models or alternative survival assumptions.
4. Calibrate recovery and dependency with paired observations. Preserve common
   cues, operators, actuators and power in coupled plant scenarios.
5. Extend PRISM's receiving contract for task-origin initiators. Keep equipment
   and task exposure units distinct and audit cause overlap.
6. Build a closed-loop cognitive/process co-simulation if feedback changes human
   decisions. The current task episode model is an open-loop scheduler.
7. Qualify physical consequence backends separately in compatible environments.
   The station SafetyPLC check does not validate the complete native plant loop.

These gates concern future calibration and application research. Existing software
checks establish the documented implementation properties, not plant protection
credit. Required sources, attribution and dependency notices remain in the repo.
