"""Role-visible cues, finite diagnostic beliefs and measurable monitoring policies."""

from __future__ import annotations

import heapq
import math

from pydantic import Field, model_validator

from .actions import StateValue
from .contracts import Contract, Name, Nonnegative, Positive, Probability
from .probability import nonnegative


class Cue(Contract):
    id: Name
    evidence_id: Name
    key: Name
    observation: StateValue
    measured_s: Nonnegative
    available_s: Nonnegative
    expires_s: Nonnegative
    visible_to: tuple[Name, ...] = Field(min_length=1)
    likelihoods: dict[str, Probability] = {}

    @model_validator(mode="after")
    def clock(self):
        if not self.measured_s <= self.available_s <= self.expires_s:
            raise ValueError("cue must be measured before availability and expiry")
        return self


class CueStore:
    def __init__(self, cues=()):
        self.cues = {}
        for cue in cues:
            self.add(cue)

    def add(self, cue: Cue):
        if cue.id in self.cues or cue.evidence_id in {c.evidence_id for c in self.cues.values()}:
            raise ValueError("cue and underlying observation identities cannot be duplicated")
        self.cues[cue.id] = cue

    def latest(self, key, actor, time_s):
        nonnegative(time_s)
        candidates = [
            c
            for c in self.cues.values()
            if c.key == key and actor in c.visible_to and c.available_s <= time_s <= c.expires_s
        ]
        if not candidates:
            return None
        newest = max(c.measured_s for c in candidates)
        selected = [c for c in candidates if c.measured_s == newest]
        if len(selected) > 1:
            raise ValueError("simultaneous cues require an explicit reconciliation rule")
        return selected[0]


class BeliefState:
    """Likelihood updates are a declared diagnostic model, not learned human cognition."""

    def __init__(self, probabilities, *, evidence):
        from .probability import probability

        if (
            not probabilities
            or not evidence.strip()
            or not math.isclose(
                sum(probability(v) for v in probabilities.values()), 1, abs_tol=1e-12, rel_tol=0
            )
        ):
            raise ValueError("normalized finite prior and evidence required")
        self.probabilities, self.evidence, self.used_cues = dict(probabilities), evidence, set()
        self.trace = []

    def update(self, cue: Cue, *, actor, time_s, independence_evidence):
        if (
            not independence_evidence.strip()
            or not cue.available_s <= time_s <= cue.expires_s
            or actor not in cue.visible_to
            or cue.observation.value is None
        ):
            raise ValueError("visible current cue and conditional-independence review required")
        if cue.evidence_id in self.used_cues or set(cue.likelihoods) != set(self.probabilities):
            raise ValueError("new observation with likelihood for every hypothesis required")
        weights = {h: p * cue.likelihoods[h] for h, p in self.probabilities.items()}
        total = math.fsum(weights.values())
        if not total:
            raise ValueError("cue is impossible under the supplied likelihood model")
        self.probabilities = {h: w / total for h, w in weights.items()}
        self.used_cues.add(cue.evidence_id)
        self.trace.append(
            {
                "cue_id": cue.id,
                "time_s": time_s,
                "posterior": dict(self.probabilities),
                "independence_evidence": independence_evidence,
            }
        )
        return dict(self.probabilities)

    def choose(self, actions: dict[str, str], *, minimum_posterior):
        from .probability import probability

        threshold = probability(minimum_posterior)
        if set(actions) != set(self.probabilities) or any(not a.strip() for a in actions.values()):
            raise ValueError("an action for every hypothesis required")
        best = max(self.probabilities.values())
        selected = [h for h, p in self.probabilities.items() if p == best]
        if best < threshold or len(selected) != 1:
            return {"status": "request_information", "action_id": None, "posterior": best}
        return {
            "status": "selected",
            "action_id": actions[selected[0]],
            "hypothesis": selected[0],
            "posterior": best,
            "human_behavior_validation_claim": False,
        }


class PollChannel(Contract):
    key: Name
    interval_s: Positive
    dwell_s: Nonnegative
    first_s: Nonnegative = 0.0


def monitor_cues(
    store: CueStore, actor, channels, *, horizon_s, adaptive_interval=None, maximum_polls=10_000
):
    """A single monitor has finite dwell time; delayed polls queue instead of using infinite attention."""
    horizon = nonnegative(horizon_s)
    if not actor.strip() or not channels or len({c.key for c in channels}) != len(channels):
        raise ValueError("named actor and unique nonempty channels required")
    if type(maximum_polls) is not int or maximum_polls < 1:
        raise ValueError("positive poll budget required")
    pending = [(c.first_s, i) for i, c in enumerate(channels)]
    heapq.heapify(pending)
    rows, free_at = [], 0.0
    while pending:
        desired, index = heapq.heappop(pending)
        channel = channels[index]
        start = max(desired, free_at)
        end = start + channel.dwell_s
        if end > horizon:
            continue
        if len(rows) >= maximum_polls:
            raise ValueError("monitoring poll budget exhausted")
        cue = store.latest(channel.key, actor, end)
        rows.append(
            {
                "key": channel.key,
                "scheduled_s": desired,
                "start_s": start,
                "observation_s": end,
                "cue_id": None if cue is None else cue.id,
                "observed": None if cue is None else cue.observation.model_dump(mode="json"),
            }
        )
        interval = nonnegative(
            adaptive_interval(channel, cue, end) if adaptive_interval else channel.interval_s
        )
        if interval <= 0:
            raise ValueError("adaptive sampling interval must be positive")
        heapq.heappush(pending, (end + interval, index))
        free_at = end
    return {"actor": actor, "polls": rows, "horizon_s": horizon, "behavioral_calibration_claim": False}
