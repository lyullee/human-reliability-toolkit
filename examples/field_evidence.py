"""Original offline example of measured-evidence qualification and numerical checks."""

import json

from human_reliability import field_sources
from human_reliability.field_data import audit_clock
from human_reliability.field_validation import SampleAlarmPolicy, detection_metrics, regression_metrics


def main():
    sources = field_sources()
    for source in sources.values():
        try:
            source.require_human_opportunities()
        except ValueError:
            pass
        else:
            raise AssertionError("process/incident metadata must not become HEP opportunities")
    # Authored numerical examples, not acquired measurements.
    check = regression_metrics([10.0, 12.0, 14.0], [11.0, 11.0, 14.0])
    clock = audit_clock(["23:59:30", "00:00:00", "00:00:30", "00:01:00", "00:01:30"])
    alarms = SampleAlarmPolicy(trigger=2.0, reset=1.0, persistence_samples=2).evaluate(
        [0.0, 3.0, 3.0, 3.0, 0.0]
    )
    detection = detection_metrics(
        [0, 1, 1, 1, 0], alarms, elapsed_s=clock.elapsed_s, clock_qualified=clock.qualified
    )
    assert detection["events"][0]["delay_s"] == 30.0
    print(
        json.dumps(
            {
                "sources": list(sources),
                "authored_regression_check": check,
                "authored_detection_check": detection,
                "field_hep_validated": False,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
