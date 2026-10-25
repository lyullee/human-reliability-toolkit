"""Small, fully authored example using the same API as data-driven applications."""

from importlib.resources import files
import json

from human_reliability.assessment import AssessmentCase, AssessmentEngine
from human_reliability.contracts import Estimate
from human_reliability.dependency import apply_recovery
from human_reliability.event_tree import event_tree, protection_partition
from human_reliability.timing import LognormalTime, apply_deadline


def main():
    case = AssessmentCase.model_validate_json(
        files("human_reliability.data").joinpath("example_case.json").read_text()
    )
    result = AssessmentEngine().assess(case)
    initial = Estimate.model_validate_json(json.dumps(result["estimates"][0]))
    timed = apply_deadline(initial, LognormalTime(10.0, 0.4), 20.0, evidence_id="assumed_time_distribution")
    recovered = apply_recovery(timed, 0.5, evidence_id="assumed_recovery")
    ledger = event_tree(
        0.01,
        protection_partition(
            0.9, recovered.probability, auto_evidence="assumed_auto", human_evidence="authored_example"
        ),
    )
    print(
        json.dumps(
            {
                "initial_hep": initial.probability,
                "deadline_hep": timed.probability,
                "unrecovered_hep": recovered.probability,
                "ledger": ledger,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
