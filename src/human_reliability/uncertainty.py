"""Reproducible input distributions, dependent sampling and optional sensitivity."""

from __future__ import annotations

from dataclasses import dataclass
import math
from collections.abc import Callable

import numpy as np
from scipy import stats


@dataclass(frozen=True)
class Distribution:
    kind: str
    parameters: tuple[float, ...]

    def scipy_distribution(self):
        p = self.parameters
        if not all(math.isfinite(value) for value in p):
            raise ValueError("finite distribution parameters required")
        if self.kind == "uniform" and len(p) == 2 and p[0] < p[1]:
            return stats.uniform(loc=p[0], scale=p[1] - p[0])
        if self.kind == "beta" and len(p) == 2 and min(p) > 0:
            return stats.beta(*p)
        if self.kind == "lognormal" and len(p) == 2 and min(p) > 0:
            return stats.lognorm(s=p[1], scale=p[0])
        if self.kind == "triangular" and len(p) == 3 and p[0] <= p[1] <= p[2] and p[0] < p[2]:
            return stats.triang((p[1] - p[0]) / (p[2] - p[0]), loc=p[0], scale=p[2] - p[0])
        raise ValueError("unsupported distribution or invalid parameterization")


def sample_inputs(distributions: dict[str, Distribution], size: int, *, seed: int, latent_correlation=None):
    if not distributions or type(size) is not int or size < 1:
        raise ValueError("nonempty distributions and positive sample count required")
    rng = np.random.default_rng(seed)
    names = tuple(distributions)
    if latent_correlation is None:
        uniform = rng.random((size, len(names)))
    else:
        correlation = np.asarray(latent_correlation, float)
        if (
            correlation.shape != (len(names), len(names))
            or not np.all(np.isfinite(correlation))
            or not np.allclose(correlation, correlation.T)
            or not np.allclose(np.diag(correlation), 1)
            or np.min(np.linalg.eigvalsh(correlation)) < -1e-10
        ):
            raise ValueError("symmetric positive-semidefinite latent correlation with unit diagonal required")
        uniform = stats.norm.cdf(rng.multivariate_normal(np.zeros(len(names)), correlation, size))
    # Keep inverse CDFs away from infinite endpoints without changing the
    # declared distribution to an arbitrary truncated engineering range.
    uniform = np.clip(uniform, np.finfo(float).eps, 1 - np.finfo(float).eps)
    return {
        name: distributions[name].scipy_distribution().ppf(uniform[:, index])
        for index, name in enumerate(names)
    }


def propagate(model: Callable, samples: dict[str, np.ndarray]):
    if not samples:
        raise ValueError("input samples required")
    lengths = {len(value) for value in samples.values()}
    if len(lengths) != 1 or min(lengths) == 0:
        raise ValueError("matched nonempty sample vectors required")
    output = np.asarray(
        [
            model(**{key: float(value[index]) for key, value in samples.items()})
            for index in range(next(iter(lengths)))
        ],
        float,
    )
    if not np.all(np.isfinite(output)):
        raise ValueError("model returned nonfinite uncertainty outputs")
    return {
        "mean": float(output.mean()),
        "p05_p50_p95": np.quantile(output, [0.05, 0.5, 0.95]).tolist(),
        "outputs": output,
        "samples": len(output),
    }


def sobol_sensitivity(
    model: Callable,
    bounds: dict[str, tuple[float, float]],
    *,
    base_size=512,
    seed=7,
    independent_inputs=False,
):
    """SALib first/total-order indices only for explicitly independent uniform inputs."""
    from SALib.sample import sobol as sampler
    from SALib.analyze import sobol as analyzer

    if not independent_inputs:
        raise ValueError("Sobol design requires an explicit independence assumption")
    if type(base_size) is not int or base_size < 16 or base_size & (base_size - 1):
        raise ValueError("power-of-two Sobol base size >=16 required")
    if not bounds or any(not math.isfinite(a) or not math.isfinite(b) or a >= b for a, b in bounds.values()):
        raise ValueError("finite increasing bounds required")
    names = list(bounds)
    problem = {"num_vars": len(names), "names": names, "bounds": list(bounds.values())}
    design = sampler.sample(problem, base_size, calc_second_order=False, seed=seed)
    outputs = np.asarray([model(**dict(zip(names, values))) for values in design], float)
    if not np.all(np.isfinite(outputs)) or np.var(outputs) == 0:
        raise ValueError("finite varying outputs required for sensitivity")
    result = analyzer.analyze(problem, outputs, calc_second_order=False, seed=seed)
    return {
        "names": names,
        "S1": result["S1"].tolist(),
        "ST": result["ST"].tolist(),
        "S1_conf": result["S1_conf"].tolist(),
        "ST_conf": result["ST_conf"].tolist(),
        "evaluations": len(outputs),
        "base_size": base_size,
        "independent_uniform_inputs": True,
        "convergence_qualified": False,
    }
