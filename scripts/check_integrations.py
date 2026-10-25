"""Check pinned public object contracts and run a bounded DynaSense consequence example."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import types
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
EXTERNAL = ROOT / "artifacts/external_source"

PINS = {
    "prism-dynasense": (
        "bd46cc46a6791131e414221135a1092f540b87d6",
        [
            "src/prism_dynasense/__init__.py",
            "src/prism_dynasense/contracts.py",
            "src/prism_dynasense/simulation.py",
            "src/prism_dynasense/prism_backend.py",
            "src/prism_dynasense/sensitivity.py",
        ],
    ),
    "saga-py": ("6eb94e00b146e18392e535d227f0c3e5ce1aca10", ["python/saga/schemas.py"]),
    "process-monitoring-toolkit": (
        "79b4cf52a0acd0d0cbd3addbe82c3d98d6385e5a",
        ["src/process_monitoring/contracts.py"],
    ),
    "qsafety-qae": ("3e7b3e78f3881a87f99d67554c6ad748fd0737e8", ["src/qsafety/core.py"]),
    "hydrogen-station-sim": (
        "9f8fa941c611abc092a10516a09e31ec2908c1d6",
        [
            "src/h2station/safety_runtime.py",
            "src/h2station/protocol.py",
            "src/h2station/tabulated.py",
            "src/h2station/thermo_types.py",
        ],
    ),
}


def fetch_sources():
    records = []
    for repo, (revision, paths) in PINS.items():
        for path in paths:
            url = f"https://raw.githubusercontent.com/lyullee/{repo}/{revision}/{path}"
            target = EXTERNAL / repo / path
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                urllib.request.urlretrieve(url, target)
            records.append(
                {
                    "repository": repo,
                    "commit": revision,
                    "path": path,
                    "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                    "url": url,
                }
            )
    return records


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main():
    sources = fetch_sources()
    sys.path.insert(0, str(ROOT / "artifacts/integration_packages"))
    sys.path.insert(0, str(EXTERNAL / "prism-dynasense/src"))
    import numpy as np
    from lh2_tno.frequency import DemandFailure, EventBranch
    from lh2dt.data_pipeline import ObservationTable
    from prism_dynasense.contracts import Scenario
    from prism_dynasense.simulation import simulate
    from human_reliability import Estimate, canonical_digest
    from human_reliability.adapters import (
        dynasense_scenario,
        monitoring_context,
        prism_branches,
        prism_demand,
        qsafety_frequency_mixture,
        saga_context,
        observation_series,
        station_stop_requested,
    )

    saga = load_module("checked_saga_schemas", EXTERNAL / "saga-py/python/saga/schemas.py")
    monitoring = load_module(
        "checked_monitoring_contracts",
        EXTERNAL / "process-monitoring-toolkit/src/process_monitoring/contracts.py",
    )
    qsafety = load_module("checked_qsafety_core", EXTERNAL / "qsafety-qae/src/qsafety/core.py")
    estimate = Estimate(
        event_id="demo_manual_failure",
        method="declared",
        probability=0.05,
        conditioning="given presented alarm and failed automatic protection",
        evidence_ids=("illustrative_assumption",),
        status="assumed",
    )
    demand = prism_demand(estimate, 20.0, factory=DemandFailure)
    assert demand.annual_failure_rate()["annual_frequency_per_year"] == 1.0
    branches = prism_branches({"success": 0.95, "failure": 0.05}, evidence="assumed", factory=EventBranch)
    assert sum(branch.probability_given_initiation for branch in branches) == 1.0
    request = saga_context(
        {"estimate": estimate.model_dump(mode="json")},
        station_id="example",
        scenario_id="declared",
        factory=saga.DigitalTwinHazopRequest,
    )
    assert request.station_id == "example"
    detection = monitoring.DetectionResult(
        time_s=np.array([0.0]),
        scores=np.array([2.0]),
        alarms=np.array([True]),
        valid=np.array([True]),
        threshold=1.0,
        detector="declared_rule",
    )
    assert monitoring_context(detection, 0)["hep_inferred"] is False
    from datetime import datetime, timezone, timedelta

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    observation = ObservationTable(
        time_s=np.array([0.0, 1.0]),
        timestamps=(now, now + timedelta(seconds=1)),
        original_timestamp_strings=("0", "1"),
        values={"PT": np.array([2e5, np.nan])},
        valid_masks={"PT": np.array([True, False])},
        quality_flags={"PT": ("GOOD", "MISSING")},
        source_path="authored-contract-fixture",
    )
    series = observation_series(observation, "PT", unit="Pa", clock_id="fixture", origin="authored_fixture")
    assert series.valid == (True, False) and series.values[1] is None
    # Load the actual safety submodules without starting the station package's
    # physical-model facade or its native optional consequence dependencies.
    station_package = types.ModuleType("checked_station")
    station_package.__path__ = [str(EXTERNAL / "hydrogen-station-sim/src/h2station")]
    sys.modules["checked_station"] = station_package
    import importlib

    station = importlib.import_module("checked_station.safety_runtime")
    limits = station.SafetyLimits(
        maximum_vehicle_pressure_pa=90e6,
        maximum_vehicle_temperature_k=400.0,
        maximum_precooler_outlet_temperature_k=350.0,
        maximum_flow_imbalance_kg_s=1.0,
        detector_alarm_volume_fraction=0.004,
        detector_trip_volume_fraction=0.01,
        trip_persistence_s=0.5,
    )
    measurement = station.StationMeasurements(
        time_s=0.0,
        fueling_phase=station.FuelingPhase.IDLE,
        vehicle_pressure_pa=5e6,
        vehicle_temperature_k=290.0,
        hose_pressure_pa=5e6,
        hose_temperature_k=290.0,
        pcv_mass_flow_kg_s=0.0,
        nozzle_mass_flow_kg_s=0.0,
        precooler_outlet_temperature_k=290.0,
        hydrogen_concentration_by_detector={"fixture": 0.0},
    )
    plc = station.SafetyPLC(limits)
    assert not plc.update(measurement, 0.2).esd_latched
    timeline = {"status": "completed", "command_time_s": 3.0}
    assert not plc.update(
        measurement, 0.2, emergency_stop_requested=station_stop_requested(2.0, timeline)
    ).esd_latched
    assert plc.update(
        measurement, 0.2, emergency_stop_requested=station_stop_requested(3.0, timeline)
    ).esd_latched
    mixture = qsafety_frequency_mixture([0.01, 0.02], [0.1, 0.3], factory=qsafety.RiskDistribution)
    assert np.isclose(
        mixture["weighted_event_rate_per_year"], 0.03 * mixture["conditional_model"].probability
    )
    baseline = Scenario()
    rows = []
    for completion in [5.0, 10.0, 20.0, None]:
        scenario = dynasense_scenario(baseline, completion)
        result = simulate(scenario)
        rows.append(
            {
                "human_physical_completion_s": completion,
                "isolation_input_s": scenario.isolation_time_s,
                "outputs": result.outputs,
            }
        )
    masses = [row["outputs"]["released_mass_kg"] for row in rows]
    assert masses == sorted(masses)
    report = {
        "schema_version": "1",
        "sources": sources,
        "input_estimate_digest": canonical_digest(estimate),
        "checked_objects": [
            "PRISM DemandFailure",
            "PRISM EventBranch",
            "DynaSense Scenario and simulation",
            "SAGA DigitalTwinHazopRequest",
            "Monitoring DetectionResult",
            "QSafety RiskDistribution",
            "lh2dt ObservationTable",
            "hydrogen-station-sim SafetyPLC isolated module",
        ],
        "dynasense_response_cases": rows,
        "source_only_protocols": [
            "PSA cycle trace",
        ],
        "live_service_exchange": False,
        "operator_effectiveness_verified": False,
        "limitations": [
            "synthetic bounded gas example",
            "no annual facility QRA",
            "conditional harm not an initiating probability",
            "source pins and package versions must be rechecked after external changes",
        ],
    }
    (ROOT / "research/integration_checks.json").write_text(
        json.dumps(report, indent=2, allow_nan=False), encoding="utf-8"
    )
    print(
        json.dumps(
            {"checked_objects": report["checked_objects"], "release_mass_kg_by_case": masses}, indent=2
        )
    )


if __name__ == "__main__":
    main()
