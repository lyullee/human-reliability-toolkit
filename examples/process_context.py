"""Apply a real compressor time series to alarm context; human probabilities stay assumed."""

from pathlib import Path
import json

import numpy as np
import pandas as pd

from human_reliability import SignalSeries
from human_reliability.datasets import uci_metropt
from human_reliability.monitoring import AlarmPolicy, alarm_burden

ROOT = Path(__file__).resolve().parents[1]


def main():
    frame = uci_metropt(ROOT / "data/raw/metropt3/source.zip", stride=60)
    clock = pd.to_datetime(frame["timestamp"])
    # A descriptive demonstration threshold, calibrated only on March. It is
    # neither an engineering trip limit nor a validated failure detector.
    channel = "Motor_current"
    calibration = clock.dt.month == 3
    operation = clock.dt.month >= 4
    threshold = float(frame.loc[calibration, channel].quantile(0.95))
    values = frame.loc[operation, channel].to_numpy(float)
    times = (clock.loc[operation] - clock.loc[operation].iloc[0]).dt.total_seconds().to_numpy()
    valid = np.isfinite(values)
    signal = SignalSeries(
        time_s=tuple(map(float, times)),
        values=tuple(float(value) if ok else None for value, ok in zip(values, valid)),
        valid=tuple(map(bool, valid)),
        clock_id="metropt_elapsed",
        unit="A",
        origin="measured_process",
    )
    policy = AlarmPolicy(
        trigger=threshold, reset=0.9 * threshold, persistence_s=600.0, recovery_s=600.0, maximum_gap_s=1200.0
    )
    alarms = policy.evaluate(signal)
    burden = alarm_burden(alarms, window_s=3600.0)
    report = {
        "dataset": "metropt3",
        "source_rows": frame.attrs["source_rows"],
        "stride": 60,
        "calibration_month": 3,
        "operation_months": "April onward",
        "channel": channel,
        "unit": "A",
        "threshold": threshold,
        "monitoring_samples": len(values),
        "activation_count": len(alarms["activation_times_s"]),
        "maximum_activations_in_hour": int(burden.max()),
        "human_error_probability_inferred": False,
        "meaning": "causal alarm-context integration demonstration; not a detector-performance benchmark",
    }
    (ROOT / "research/process_example.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
