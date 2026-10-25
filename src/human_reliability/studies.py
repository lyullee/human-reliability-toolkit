"""Group-aware empirical checks avoid treating repeated people as independent holdouts."""

from __future__ import annotations

import numpy as np


def group_holdout(groups, *, test_fraction=0.3, seed=20261026):
    groups = np.asarray(groups)
    unique = np.unique(groups)
    if len(unique) < 3 or not 0 < test_fraction < 1:
        raise ValueError("at least three groups and an interior test fraction required")
    shuffled = np.random.default_rng(seed).permutation(unique)
    count = max(1, min(len(unique) - 1, int(np.ceil(len(unique) * test_fraction))))
    test = np.isin(groups, shuffled[:count])
    return ~test, test


def cluster_bootstrap_rate(errors, groups, *, repeats=2000, seed=7):
    values, labels = np.asarray(errors), np.asarray(groups)
    if (
        values.shape != labels.shape
        or values.ndim != 1
        or len(values) == 0
        or not np.all(np.isin(values, [0, 1]))
    ):
        raise ValueError("matched nonempty binary outcomes and cluster identities required")
    clusters = np.unique(labels)
    counts = np.asarray(
        [(np.sum(values[labels == group]), np.count_nonzero(labels == group)) for group in clusters]
    )
    if len(clusters) < 2 or type(repeats) is not int or repeats < 100:
        raise ValueError("at least two clusters and 100 bootstrap replicates required")
    indices = np.random.default_rng(seed).integers(0, len(clusters), (repeats, len(clusters)))
    totals = counts[indices].sum(axis=1)
    rates = totals[:, 0] / totals[:, 1]
    return {
        "rate": float(values.mean()),
        "cluster_bootstrap_95_interval": np.quantile(rates, [0.025, 0.975]).tolist(),
        "clusters": len(clusters),
        "observations": len(values),
        "repeats": repeats,
        "estimand": "opportunity-weighted rate in the supplied experimental population",
    }


def probability_metrics(truth, predictions):
    from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score

    y, p = np.asarray(truth), np.asarray(predictions, float)
    if (
        y.shape != p.shape
        or y.ndim != 1
        or len(y) == 0
        or not np.all(np.isin(y, [0, 1]))
        or not np.all(np.isfinite(p))
        or np.any((p < 0) | (p > 1))
    ):
        raise ValueError("matched binary outcomes and probability predictions required")
    return {
        "brier": float(brier_score_loss(y, p)),
        "log_loss": float(log_loss(y, p, labels=[0, 1])),
        "roc_auc": float(roc_auc_score(y, p)) if len(np.unique(y)) == 2 else None,
        "observed_rate": float(y.mean()),
        "predicted_rate": float(p.mean()),
        "observations": len(y),
    }


def grouped_logistic(frame, target, groups, *, features, seed=20261026):
    """Compare a frozen categorical-context model with a training-only prevalence baseline."""
    from sklearn.compose import ColumnTransformer
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import OneHotEncoder
    from sklearn.linear_model import LogisticRegression

    if not features or set(features) & {target, groups}:
        raise ValueError("explicit predictor columns excluding label and group identity required")
    required = set(features) | {target, groups}
    if not required <= set(frame) or frame[list(required)].isna().any().any():
        raise ValueError("required classification fields missing; no silent row dropping")
    train, test = group_holdout(frame[groups], seed=seed)
    raw_y = frame[target].to_numpy()
    if not np.all(np.isin(raw_y, [0, 1])):
        raise ValueError("classification target must contain only binary outcomes")
    y = raw_y.astype(int)
    if len(np.unique(y[train])) < 2:
        raise ValueError("training split contains only one outcome class")
    transformer = ColumnTransformer([("context", OneHotEncoder(handle_unknown="ignore"), list(features))])
    model = make_pipeline(transformer, LogisticRegression(C=1.0, max_iter=2000, random_state=seed))
    model.fit(frame.loc[train, list(features)], y[train])
    probabilities = model.predict_proba(frame.loc[test, list(features)])[:, 1]
    baseline = (y[train].sum() + 1) / (np.count_nonzero(train) + 2)
    return {
        "features": list(features),
        "seed": seed,
        "train_groups": int(frame.loc[train, groups].nunique()),
        "test_groups": int(frame.loc[test, groups].nunique()),
        "train_rows": int(np.count_nonzero(train)),
        "test_rows": int(np.count_nonzero(test)),
        "logistic": probability_metrics(y[test], probabilities),
        "prevalence_baseline": probability_metrics(y[test], np.full(np.count_nonzero(test), baseline)),
        "held_out_groups_digest_input": sorted(map(str, frame.loc[test, groups].unique())),
        "causal_effect_claim": False,
    }
