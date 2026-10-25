"""Optional SI thermodynamic state and accounting helpers via CoolProp."""

from __future__ import annotations

import math

import numpy as np


class CoolPropState:
    """No property backend is silently substituted when state evaluation fails."""

    def __init__(self, fluid="Hydrogen", backend="HEOS"):
        if not fluid.strip() or not backend.strip() or backend.upper() == "REFPROP":
            raise ValueError("explicit available open backend required; REFPROP is not bundled")
        from CoolProp.CoolProp import PropsSI

        self.fluid, self.backend, self._props = fluid, backend, PropsSI

    def evaluate(self, key_a: str, value_a: float, key_b: str, value_b: float):
        if key_a == key_b or not all(math.isfinite(value) for value in (value_a, value_b)):
            raise ValueError("two distinct finite state coordinates required")
        allowed = {"P", "T", "Dmass", "Hmass", "Smass", "Q", "Umass"}
        if {key_a, key_b} - allowed:
            raise ValueError("unsupported SI state coordinate")
        for key, value in ((key_a, value_a), (key_b, value_b)):
            if key in {"P", "T", "Dmass"} and value <= 0:
                raise ValueError("positive absolute P, T or density required")
            if key == "Q" and not 0 <= value <= 1:
                raise ValueError("quality must lie in [0,1]")
        source = f"{self.backend}::{self.fluid}"
        keys = {
            "pressure_pa_abs": "P",
            "temperature_k": "T",
            "density_kg_m3": "Dmass",
            "enthalpy_j_kg": "Hmass",
            "internal_energy_j_kg": "Umass",
        }
        values = {
            name: float(self._props(code, key_a, value_a, key_b, value_b, source))
            for name, code in keys.items()
        }
        if not all(math.isfinite(value) for value in values.values()):
            raise ValueError("property backend returned nonfinite state")
        import CoolProp

        return values | {
            "fluid": self.fluid,
            "backend": self.backend,
            "backend_version": CoolProp.__version__,
        }


def inventory_mass_residual(time_s, mass_kg, inflow_kg_s, outflow_kg_s):
    """Measured inventory change minus trapezoidal net boundary inflow."""
    time, mass, incoming, outgoing = (
        np.asarray(value, float) for value in (time_s, mass_kg, inflow_kg_s, outflow_kg_s)
    )
    if (
        time.ndim != 1
        or len(time) < 2
        or any(array.shape != time.shape for array in (mass, incoming, outgoing))
    ):
        raise ValueError("matched histories with at least two times required")
    if (
        np.any(np.diff(time) <= 0)
        or not all(np.all(np.isfinite(value)) for value in (time, mass, incoming, outgoing))
        or np.any(mass < 0)
    ):
        raise ValueError("finite increasing clock and nonnegative inventory required")
    net = incoming - outgoing
    interval = (net[1:] + net[:-1]) / 2 * np.diff(time)
    expected = np.r_[0.0, np.cumsum(interval)]
    return mass - mass[0] - expected


def energy_residual(
    initial_energy_j: float,
    final_energy_j: float,
    *,
    heat_in_j: float,
    work_out_j: float,
    inflow_enthalpy_j: float,
    outflow_enthalpy_j: float,
):
    """Signed first-law balance for a caller-declared control volume."""
    values = (initial_energy_j, final_energy_j, heat_in_j, work_out_j, inflow_enthalpy_j, outflow_enthalpy_j)
    if not all(math.isfinite(value) for value in values):
        raise ValueError("finite energy terms required")
    return (
        final_energy_j - initial_energy_j - (heat_in_j - work_out_j + inflow_enthalpy_j - outflow_enthalpy_j)
    )
