"""Causal alarm episodes describe the information available to an operator."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .contracts import SignalSeries
from .probability import nonnegative


@dataclass(frozen=True)
class AlarmPolicy:
    trigger: float
    reset: float
    persistence_s: float = 0.0
    recovery_s: float = 0.0
    maximum_gap_s: float = 2.0
    latch: bool = False

    def __post_init__(self):
        if not np.isfinite(self.trigger) or not np.isfinite(self.reset) or self.reset > self.trigger:
            raise ValueError("finite high-alarm thresholds with reset <= trigger required")
        for value in (self.persistence_s, self.recovery_s, self.maximum_gap_s):
            nonnegative(value)
        if self.maximum_gap_s == 0:
            raise ValueError("positive gap limit required")

    def evaluate(self, series: SignalSeries):
        """Assume sample-and-hold only across valid, sufficiently close samples.

        The returned validity masks unknown observation intervals. A latched
        state survives missing information, while persistence timers do not.
        """
        active = False
        high_since = low_since = None
        previous_t = None
        flags, valid, starts = [], [], []
        previous_valid = False
        for t, value, usable in zip(series.time_s, series.values, series.valid):
            gap = previous_t is not None and t - previous_t > self.maximum_gap_s
            if gap or not previous_valid:
                high_since = low_since = None
            if not usable:
                high_since = low_since = None
                flags.append(active)
                valid.append(False)
            else:
                previous = active
                if value >= self.trigger:
                    high_since = t if high_since is None else high_since
                else:
                    high_since = None
                if value <= self.reset:
                    low_since = t if low_since is None else low_since
                else:
                    low_since = None
                if not active and high_since is not None and t - high_since >= self.persistence_s:
                    active = True
                elif active and not self.latch and low_since is not None and t - low_since >= self.recovery_s:
                    active = False
                if active and not previous:
                    starts.append(t)
                flags.append(active)
                valid.append(True)
            previous_t, previous_valid = t, usable
        return {
            "time_s": list(series.time_s),
            "alarms": flags,
            "valid": valid,
            "activation_times_s": starts,
            "clock_id": series.clock_id,
            "origin": series.origin,
            "meaning": "monitoring information, not human error probability",
        }


def alarm_burden(result, *, window_s: float):
    window = nonnegative(window_s)
    if window == 0:
        raise ValueError("positive burden window required")
    times = np.asarray(result["time_s"], float)
    starts = np.asarray(result["activation_times_s"], float)
    return np.asarray([np.count_nonzero((starts > time - window) & (starts <= time)) for time in times])
