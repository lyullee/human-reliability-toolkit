"""Reusable retrospective evaluation runners; dataset labels never become operator HEPs."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict
import hashlib

import numpy as np

from .contracts import canonical_digest
from .datasets import uci_gas_turbine
from .field_data import (
    continuous_distillation,
    field_sources,
    incident_code_summary,
    rail_incident_cases,
    steel_energy,
)
from .field_validation import (
    aggregate_binomial_metrics,
    calibration_width,
    detection_metrics,
    fit_robust_reference,
    interval_metrics,
    paired_block_rmse,
    regression_metrics,
    SampleAlarmPolicy,
)


def _scope(source_id):
    source = field_sources()[source_id]
    return {
        "source_id": source_id,
        "source_origin": source.origin,
        "source_doi": source.doi,
        "license": source.license,
        "conditions": list(source.conditions),
        "limitations": list(source.limitations),
        "human_field_validation": False,
        "human_failure_probability_inferred": False,
        "prospective_validation": False,
    }


def regression_holdout(
    frame,
    *,
    target,
    features,
    train,
    calibration,
    test,
    baseline_test,
    baseline_calibration,
    unit,
    model_parameters,
    seed=20261026,
    nominal_coverage=0.9,
    block_rows=24,
    bootstrap_repeats=1000,
    model_factory=None,
):
    """Evaluate one already partitioned case; fit/calibrate only on their declared rows."""
    if not features or target in features or len(set(features)) != len(features):
        raise ValueError("unique explicit features excluding the prediction target required")
    masks = [np.asarray(m) for m in (train, calibration, test)]
    if any(m.dtype != bool or m.shape != (len(frame),) or not m.any() for m in masks):
        raise ValueError("matched nonempty boolean training/calibration/test masks required")
    if np.any(sum(m.astype(int) for m in masks) > 1):
        raise ValueError("training/calibration/test rows must be disjoint")
    selected = np.logical_or.reduce(masks)
    x, y = frame[list(features)].to_numpy(float), frame[target].to_numpy(float)
    if not np.isfinite(x[selected]).all() or not np.isfinite(y[selected]).all():
        raise ValueError("nonfinite selected prediction inputs; no silent row dropping")
    if model_factory is None:
        from sklearn.ensemble import HistGradientBoostingRegressor

        model_factory = HistGradientBoostingRegressor
    model = model_factory(random_state=seed, **model_parameters)
    model.fit(x[masks[0]], y[masks[0]])
    pc, pt = model.predict(x[masks[1]]), model.predict(x[masks[2]])
    baseline = np.asarray(baseline_test, float)
    model_metrics, base_metrics = (
        regression_metrics(y[masks[2]], pt),
        regression_metrics(y[masks[2]], baseline),
    )
    width = calibration_width(y[masks[1]], pc, nominal_coverage=nominal_coverage)
    base_width = calibration_width(y[masks[1]], baseline_calibration, nominal_coverage=nominal_coverage)
    low, high = np.min(x[masks[0]], axis=0), np.max(x[masks[0]], axis=0)
    counts = {
        "train": int(masks[0].sum()),
        "calibration": int(masks[1].sum()),
        "test": int(masks[2].sum()),
        "excluded": int(np.sum(~selected)),
    }
    report = {
        "status": "retrospective_evaluation_completed",
        "unit": unit,
        "features": list(features),
        "model": type(model).__name__,
        "parameters": model_parameters,
        "seed": seed,
        "rows": counts,
        "model_metrics": model_metrics,
        "baseline_metrics": base_metrics,
        "rmse_ratio_to_baseline": model_metrics["rmse"] / base_metrics["rmse"]
        if base_metrics["rmse"]
        else None,
        "model_interval": interval_metrics(y[masks[2]], pt, half_width=width),
        "baseline_interval": interval_metrics(y[masks[2]], baseline, half_width=base_width),
        "nominal_interval_coverage": nominal_coverage,
        "calibration_half_width": width,
        "test_fraction_outside_training_feature_range": {
            f: float(np.mean((x[masks[2], i] < low[i]) | (x[masks[2], i] > high[i])))
            for i, f in enumerate(features)
        },
        "paired_block_comparison": paired_block_rmse(
            y[masks[2]], pt, baseline, block_rows=block_rows, repeats=bootstrap_repeats, seed=seed
        ),
        "test_truth_sha256": hashlib.sha256(y[masks[2]].tobytes()).hexdigest(),
        "test_predictions_sha256": hashlib.sha256(np.asarray(pt).tobytes()).hexdigest(),
        "predictions_origin": "model_estimate",
        "measurements_origin": "observed_process",
        "accuracy_improves_prespecified_baseline": model_metrics["rmse"] < base_metrics["rmse"],
        "field_human_reliability_qualification": "not_established",
    }
    return report, model


def evaluate_gas_turbine(
    archive, specification, *, seed=20261026, bootstrap_repeats=1000, model_factory=None
):
    frame = uci_gas_turbine(archive)
    years = frame.source_file.str.extract(r"gt_(\d{4})\.csv", expand=False)
    if years.isna().any():
        raise ValueError("source year identity missing; do not invent a chronology")
    frame["source_year"] = years.astype(int)
    train, calibration, test = [
        frame.source_year.isin(specification[k]).to_numpy()
        for k in ("train_years", "calibration_years", "test_years")
    ]
    mean = float(frame.loc[train, specification["target"]].mean())
    report, _ = regression_holdout(
        frame,
        target=specification["target"],
        features=specification["features"],
        train=train,
        calibration=calibration,
        test=test,
        baseline_test=np.full(test.sum(), mean),
        baseline_calibration=np.full(calibration.sum(), mean),
        unit=specification["unit"],
        model_parameters=specification["parameters"],
        seed=seed,
        bootstrap_repeats=bootstrap_repeats,
        block_rows=24,
        model_factory=model_factory,
    )
    return (
        report
        | _scope("uci_gas_turbine")
        | {
            "source_rows": len(frame),
            "partition_years": {
                k: specification[k] for k in ("train_years", "calibration_years", "test_years")
            },
            "baseline": specification["baseline"],
            "interpretation": specification["scope"],
        }
    )


def evaluate_steel_energy(
    archive, specification, *, seed=20261026, bootstrap_repeats=1000, model_factory=None
):
    import pandas as pd

    frame = steel_energy(archive, midnight_policy=specification.get("midnight_policy", "reject"))
    diffs = frame.source_time.diff().dt.total_seconds().iloc[1:]
    if not (diffs == 900).all():
        raise ValueError("lag indices require an unbroken source quarter-hour grid")
    hours = frame.source_time.dt.hour + frame.source_time.dt.minute / 60
    frame["hour_sin"], frame["hour_cos"] = np.sin(2 * np.pi * hours / 24), np.cos(2 * np.pi * hours / 24)
    frame["weekday"] = frame.source_time.dt.dayofweek
    frame["lag_1"], frame["lag_96"] = frame.Usage_kWh.shift(1), frame.Usage_kWh.shift(96)
    eligible = frame.index.to_numpy() >= 96
    train = eligible & (frame.source_time < pd.Timestamp(specification["train_before"])).to_numpy()
    calibration = (
        eligible
        & (frame.source_time >= pd.Timestamp(specification["train_before"])).to_numpy()
        & (frame.source_time < pd.Timestamp(specification["calibration_before"])).to_numpy()
    )
    test = (
        eligible
        & (frame.source_time >= pd.Timestamp(specification["calibration_before"])).to_numpy()
        & (frame.source_time < pd.Timestamp(specification["test_before"])).to_numpy()
    )
    report, _ = regression_holdout(
        frame,
        target=specification["target"],
        features=specification["features"],
        train=train,
        calibration=calibration,
        test=test,
        baseline_test=frame.loc[test, "lag_1"].to_numpy(),
        baseline_calibration=frame.loc[calibration, "lag_1"].to_numpy(),
        unit=specification["unit"],
        model_parameters=specification["parameters"],
        seed=seed,
        bootstrap_repeats=bootstrap_repeats,
        block_rows=96,
        model_factory=model_factory,
    )
    return (
        report
        | _scope("uci_steel_energy")
        | {
            "source_rows": len(frame),
            "forecast_horizon_s": 900,
            "clock_interpretation": frame.attrs["clock_interpretation"],
            "timing_results_conditional_on_declared_clock_interpretation": frame.attrs[
                "clock_interpretation"
            ]["changed_rows"]
            > 0,
            "partition_boundaries": {
                k: specification[k] for k in ("train_before", "calibration_before", "test_before")
            },
            "excluded_initial_unavailable_lags": 96,
            "baseline": specification["baseline"],
            "interpretation": specification["scope"],
            "source_timezone": "unspecified source civil time; not assumed UTC",
        }
    )


def evaluate_distillation(archive, specification):
    runs = continuous_distillation(archive)
    references = defaultdict(list)
    for run in runs:
        if run.role == "reference":
            if run.frame[specification["label"]].any():
                raise ValueError("a declared normal reference contains positive source labels")
            references[(run.scenario, run.operating_point)].append(run)
    fitted = {}
    features = specification["features"]
    for key, group in references.items():
        x = np.concatenate([r.numeric_matrix(features)[0] for r in group])
        cut = int(len(x) * specification["train_fraction_of_reference"])
        end_train = cut - specification["gap_rows"]
        if end_train < 2 or len(x) - cut < 2:
            continue
        floors = [
            specification["scale_floors"][
                "temperature_degC"
                if f.startswith("T")
                else "differential_pressure_mbar"
                if f.startswith("PDIC")
                else "pressure_mbar"
                if f.startswith("PIC")
                else "mass_flow_kg_per_h"
            ]
            for f in features
        ]
        ref = fit_robust_reference(x[:end_train], scale_floors=floors)
        score = ref.score(x[cut:])
        if not np.isfinite(score).all():
            raise ValueError("nonfinite calibration reference; no imputation")
        threshold = float(np.quantile(score, specification["calibration_quantile"], method="higher"))
        fitted[key] = (
            ref,
            threshold,
            {
                "reference_run_ids": [r.id for r in group],
                "training_rows": end_train,
                "calibration_rows": len(x) - cut,
                "gap_rows": specification["gap_rows"],
            },
        )
    evaluations = []
    for run in runs:
        if run.role != "evaluation":
            continue
        key = (run.scenario, run.operating_point)
        common = {
            "run_id": run.id,
            "scenario": run.scenario,
            "operating_point": run.operating_point,
            "source_rows": len(run.frame),
            "source_member_sha256": run.source_sha256,
            "metadata_sha256": run.metadata_sha256,
            "annotation_audit": run.annotation_audit,
            "clock": asdict(run.clock) | {"elapsed_s": None},
            "source_label_positive_samples": int(run.frame[specification["label"]].sum()),
            "anomaly_origin": "experimental_mix_not_inferred_as_natural_human_error",
        }
        if key not in fitted:
            evaluations.append(
                common | {"status": "withheld", "reason": "no matched-condition normal reference"}
            )
            continue
        ref, threshold, partition = fitted[key]
        matrix, measurement_audit = run.numeric_matrix(features)
        common["measurement_audit"] = measurement_audit
        scores = ref.score(matrix)
        alarms = SampleAlarmPolicy(
            threshold,
            threshold,
            specification["alarm_persistence_samples"],
            specification["alarm_reset_samples"],
        ).evaluate(scores)
        metrics = detection_metrics(
            run.frame[specification["label"]],
            alarms,
            elapsed_s=run.clock.elapsed_s,
            clock_qualified=run.clock.qualified,
        )
        evaluations.append(
            common
            | {
                "status": "evaluated",
                "threshold": threshold,
                "reference_partition": partition,
                "metrics": metrics,
            }
        )
    return _scope("tum_continuous_distillation") | {
        "status": "retrospective_evaluation_completed",
        "features": features,
        "source_experiments": len(runs),
        "source_rows": sum(len(r.frame) for r in runs),
        "reference_experiments": sum(r.role == "reference" for r in runs),
        "evaluated_runs": sum(r["status"] == "evaluated" for r in evaluations),
        "withheld_runs": sum(r["status"] == "withheld" for r in evaluations),
        "source_total_qualified_clock_runs": sum(r.clock.qualified for r in runs),
        "interpretation": specification["scope"],
        "evaluations": evaluations,
        "source_member_digests": {r.id: r.source_sha256 for r in runs},
        "advanced_annotation_issues": {r.id: r.annotation_audit for r in runs if r.annotation_audit},
    }


def evaluate_water_properties(archive):
    from CoolProp.CoolProp import PropsSI
    import CoolProp

    rows, observed, predicted = [], [], []
    for run in continuous_distillation(archive):
        if not run.scenario.startswith("ScenarioA") or run.role != "reference":
            continue
        pressure = run.frame.PIC101.to_numpy(float) * 100
        temperature = run.frame.T102.to_numpy(float)
        if not np.isfinite(pressure).all() or not np.isfinite(temperature).all() or np.any(pressure <= 0):
            raise ValueError("invalid pressure/temperature measurements; no implicit correction")
        prediction = np.asarray(PropsSI("T", "P", pressure, "Q", 0.0, "HEOS::Water")) - 273.15
        rows.append({"run_id": run.id, "metrics": regression_metrics(temperature, prediction)})
        observed.extend(temperature)
        predicted.extend(prediction)
    return _scope("tum_continuous_distillation") | {
        "status": "unfitted_property_consistency_evaluated",
        "backend": "CoolProp HEOS::Water",
        "backend_version": CoolProp.__version__,
        "unit": "degC",
        "metrics": regression_metrics(observed, predicted),
        "runs": rows,
        "calibrated_offsets": False,
        "interpretation": "Measured T102 versus water saturation at measured head pressure. Local pressure gradients, immersion, thermal losses and sensor uncertainties are not fully characterized. This is not full simulator validation.",
    }


def evaluate_rail_incidents(path):
    result = incident_code_summary(rail_incident_cases(path))
    return result | _scope("korea_rail_incidents") | {"status": "descriptive_case_evaluation_completed"}


def evaluate_sacada_contexts(*, catalog=None, seed=20261026):
    from .evidence_catalog import builtin_evidence_catalog
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler

    catalog = catalog or builtin_evidence_catalog()
    groups = defaultdict(list)
    for row in catalog.search(kind="observed_count", source_id="sacada_2019"):
        groups[row.function].append(row)
    results = {}
    for function, records in sorted(groups.items()):
        records = sorted(records, key=lambda r: r.id)
        feature_names = sorted(records[0].conditions)
        if any(set(r.conditions) != set(feature_names) for r in records):
            raise ValueError("inconsistent within-function released context schema")
        x = np.asarray([[r.conditions[k] for k in feature_names] for r in records], float)
        k, n = np.asarray([r.failures for r in records]), np.asarray([r.opportunities for r in records])
        order = np.random.default_rng(seed).permutation(len(records))
        count = int(np.ceil(0.3 * len(order)))
        train, test = order[:-count], order[-count:]
        base = float((k[train].sum() + 0.5) / (n[train].sum() + 1))
        row = {
            "feature_names": feature_names,
            "training_contexts": len(train),
            "test_contexts": len(test),
            "training_opportunities": int(n[train].sum()),
            "training_failures": int(k[train].sum()),
            "prior_alpha": 0.5,
            "prior_beta": 0.5,
            "training_context_ids": [records[i].id for i in train],
            "test_context_ids": [records[i].id for i in test],
            "pooled_baseline": aggregate_binomial_metrics(k[test], n[test], np.full(len(test), base)),
        }
        if not k[train].sum() or k[train].sum() == n[train].sum():
            row["context_model"] = {"status": "withheld", "reason": "training contains one outcome class"}
        else:
            scaler = StandardScaler().fit(x[train], sample_weight=n[train])
            xtrain = scaler.transform(x[train])
            expanded = np.repeat(xtrain, 2, axis=0)
            y, weights = np.tile([1, 0], len(train)), np.column_stack([k[train], n[train] - k[train]]).ravel()
            keep = weights > 0
            model = LogisticRegression(C=1.0, max_iter=2000, random_state=seed)
            model.fit(expanded[keep], y[keep], sample_weight=weights[keep])
            probabilities = model.predict_proba(scaler.transform(x[test]))[:, 1]
            row["context_model"] = aggregate_binomial_metrics(k[test], n[test], probabilities) | {
                "status": "research_model_estimate",
                "regularization_C": 1.0,
                "context_codes_treated_as_numeric": True,
                "brier_improves_baseline": aggregate_binomial_metrics(k[test], n[test], probabilities)[
                    "brier"
                ]
                < row["pooled_baseline"]["brier"],
            }
        results[function] = row
    return {
        "status": "retrospective_simulator_context_evaluation_completed",
        "source_id": "sacada_2019",
        "source_origin": "observed_simulator_counts",
        "predictions_origin": "model_estimate",
        "seed": seed,
        "functions": results,
        "human_field_validation": False,
        "independent_crew_validation": False,
        "recovery_or_timing_separately_validated": False,
        "interpretation": "Context-level holdout only; crew overlap and repeated trials are not identifiable. No chemical-process field transfer or causal coefficient claim.",
        "catalog_input_digest": canonical_digest(
            [r.model_dump(mode="json") for rows in groups.values() for r in rows]
        ),
    }
