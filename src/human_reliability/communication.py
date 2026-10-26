"""Explicit message understanding, handover freshness and work-control state machines."""

from __future__ import annotations

from .actions import Command, ProcessState, StatePredicate
from .contracts import Contract, Name, Nonnegative, canonical_digest
from .probability import nonnegative
from pydantic import model_validator


class Message(Contract):
    id: Name
    sender: Name
    receiver: Name
    command: Command
    sent_s: Nonnegative
    expires_s: Nonnegative
    evidence: Name

    @model_validator(mode="after")
    def interval(self):
        if self.expires_s < self.sent_s or self.sender == self.receiver:
            raise ValueError("message needs distinct roles and a valid delivery window")
        return self


class MessageLedger:
    def __init__(self):
        self.messages, self.states, self.audit = {}, {}, []
        self._last_time = 0.0

    def _record(self, time_s, kind, identity, actor):
        t = nonnegative(time_s)
        if t < self._last_time:
            raise ValueError("communication events must be chronological")
        self._last_time = t
        self.audit.append({"time_s": t, "kind": kind, "message_id": identity, "actor": actor})

    def send(self, message: Message):
        if message.id in self.messages:
            raise ValueError("message identities cannot be reused")
        self._record(message.sent_s, "sent", message.id, message.sender)
        self.messages[message.id] = message
        self.states[message.id] = {"received": False, "understood": False, "confirmed": False}

    def receive(self, message_id, receiver, time_s):
        message = self.messages[message_id]
        self._record(
            time_s, "received" if receiver == message.receiver else "wrong_recipient", message_id, receiver
        )
        if receiver != message.receiver or time_s > message.expires_s:
            return False
        if self.states[message_id]["received"]:
            raise ValueError("duplicate receipt requires a new message identity")
        self.states[message_id]["received"] = True
        return True

    def interpret(self, message_id, receiver, understood_command: Command, time_s):
        message = self.messages[message_id]
        self._record(time_s, "interpretation", message_id, receiver)
        if (
            receiver != message.receiver
            or not self.states[message_id]["received"]
            or time_s > message.expires_s
        ):
            return False
        correct = canonical_digest(understood_command) == canonical_digest(message.command)
        self.states[message_id]["understood"] = correct
        self.states[message_id]["confirmed"] = False
        return correct

    def confirm(self, message_id, sender, readback: Command, time_s):
        message = self.messages[message_id]
        self._record(time_s, "readback_confirmation", message_id, sender)
        correct = (
            sender == message.sender
            and self.states[message_id]["understood"]
            and time_s <= message.expires_s
            and canonical_digest(readback) == canonical_digest(message.command)
        )
        self.states[message_id]["confirmed"] = correct
        return correct

    def authorized_command(self, message_id, receiver, time_s):
        nonnegative(time_s)
        message = self.messages[message_id]
        if time_s < self._last_time:
            raise ValueError("authorization cannot use future communication events")
        if (
            receiver != message.receiver
            or time_s > message.expires_s
            or not self.states[message_id]["confirmed"]
        ):
            return None
        return message.command.model_copy(deep=True)


class Handover(Contract):
    id: Name
    sender: Name
    receiver: Name
    procedure_version: Name
    state_revision: Name
    facts_digest: Name
    created_s: Nonnegative
    expires_s: Nonnegative
    evidence: Name

    @model_validator(mode="after")
    def interval(self):
        if self.expires_s < self.created_s or self.sender == self.receiver:
            raise ValueError("invalid handover interval or roles")
        return self

    def accept(self, *, receiver, time_s, state: ProcessState, procedure_version, acknowledged_digest):
        nonnegative(time_s)
        reasons = []
        if receiver != self.receiver:
            reasons.append("wrong receiver")
        if not self.created_s <= time_s <= self.expires_s:
            reasons.append("handover outside validity window")
        if (
            state.revision != self.state_revision
            or canonical_digest(state.model_dump(mode="json")["values"]) != self.facts_digest
        ):
            reasons.append("plant state changed")
        if procedure_version != self.procedure_version:
            reasons.append("procedure version changed")
        if acknowledged_digest != self.facts_digest:
            reasons.append("handover content not acknowledged")
        return {"accepted": not reasons, "reasons": reasons, "handover_id": self.id}


class WorkPermit(Contract):
    id: Name
    revision: Name
    area: Name
    activity: Name
    valid_from_s: Nonnegative
    valid_until_s: Nonnegative
    conditions: tuple[StatePredicate, ...]
    lock_owners: tuple[Name, ...]
    required_restorations: tuple[Name, ...] = ()
    evidence: Name

    @model_validator(mode="after")
    def configuration(self):
        if self.valid_until_s < self.valid_from_s:
            raise ValueError("permit interval reversed")
        for values in (self.lock_owners, self.required_restorations):
            if len(values) != len(set(values)):
                raise ValueError("permit owners and restoration requirements must be unique")
        return self


class WorkControl:
    """Records modeled authorization; it neither controls locks nor issues real permits."""

    def __init__(self, *, incompatible_activities=()):
        self.incompatible = {frozenset(pair) for pair in incompatible_activities}
        if any(len(pair) != 2 for pair in self.incompatible):
            raise ValueError("conflict rules require distinct activity pairs")
        self.permits, self.status, self.locks, self.restored, self.audit = {}, {}, {}, {}, []
        self._last_time = 0.0

    def _record(self, time_s, permit_id, operation, evidence):
        t = nonnegative(time_s)
        if t < self._last_time or not evidence.strip():
            raise ValueError("chronological work-control events with evidence required")
        self._last_time = t
        self.audit.append({"time_s": t, "permit_id": permit_id, "operation": operation, "evidence": evidence})

    def issue(self, permit: WorkPermit, *, time_s):
        if permit.id in self.permits or time_s > permit.valid_until_s:
            raise ValueError("new, unexpired permit required")
        self._record(time_s, permit.id, "issue", permit.evidence)
        self.permits[permit.id], self.status[permit.id] = permit, "issued"
        self.locks[permit.id], self.restored[permit.id] = set(), set()

    def lock(self, permit_id, owner, *, time_s, evidence):
        if owner not in self.permits[permit_id].lock_owners or self.status[permit_id] == "closed":
            raise ValueError("known lock owner on an open permit required")
        if owner in self.locks[permit_id]:
            raise ValueError("lock already held")
        self._record(time_s, permit_id, "lock:" + owner, evidence)
        self.locks[permit_id].add(owner)

    def unlock(self, permit_id, owner, *, actor, time_s, evidence):
        if actor != owner or owner not in self.locks[permit_id]:
            raise ValueError("each owner must remove their own recorded lock")
        self._record(time_s, permit_id, "unlock:" + owner, evidence)
        self.locks[permit_id].remove(owner)
        if self.status[permit_id] == "active":
            self.status[permit_id] = "suspended"

    def authorize(self, permit_id, state, *, time_s, evidence):
        permit = self.permits[permit_id]
        self._record(time_s, permit_id, "authorization_review", evidence)
        reasons = []
        if self.status[permit_id] == "closed":
            reasons.append("permit closed")
        if not permit.valid_from_s <= time_s <= permit.valid_until_s:
            reasons.append("permit outside validity window")
        if any(p.evaluate(state) is not True for p in permit.conditions):
            reasons.append("safety condition false or unknown")
        if self.locks[permit_id] != set(permit.lock_owners):
            reasons.append("required personal locks absent")
        for other_id, other in self.permits.items():
            if (
                other_id != permit_id
                and self.status[other_id] == "active"
                and other.area == permit.area
                and (frozenset((permit.activity, other.activity)) in self.incompatible)
            ):
                reasons.append("incompatible active work: " + other_id)
        if not reasons:
            self.status[permit_id] = "active"
        elif self.status[permit_id] == "active":
            self.status[permit_id] = "suspended"
        return {"authorized": not reasons, "reasons": reasons, "permit_id": permit_id}

    def suspend(self, permit_id, *, time_s, evidence):
        if self.status[permit_id] == "closed":
            raise ValueError("closed permit cannot be suspended")
        self._record(time_s, permit_id, "suspend", evidence)
        self.status[permit_id] = "suspended"

    def renew(self, permit: WorkPermit, *, time_s):
        old = self.permits[permit.id]
        if (
            self.status[permit.id] == "closed"
            or permit.revision == old.revision
            or time_s > permit.valid_until_s
        ):
            raise ValueError("renewal requires an open permit and a new revision")
        if (permit.area, permit.activity, permit.lock_owners, permit.required_restorations) != (
            old.area,
            old.activity,
            old.lock_owners,
            old.required_restorations,
        ):
            raise ValueError("changed work scope requires a separate permit")
        self._record(time_s, permit.id, "renew", permit.evidence)
        self.permits[permit.id], self.status[permit.id] = permit, "issued"

    def confirm_restoration(self, permit_id, restoration, *, time_s, evidence):
        if (
            restoration not in self.permits[permit_id].required_restorations
            or self.status[permit_id] == "closed"
        ):
            raise ValueError("known restoration on an open permit required")
        self._record(time_s, permit_id, "restored:" + restoration, evidence)
        self.restored[permit_id].add(restoration)

    def close(self, permit_id, *, time_s, evidence):
        permit = self.permits[permit_id]
        if (
            self.status[permit_id] == "closed"
            or self.locks[permit_id]
            or self.restored[permit_id] != set(permit.required_restorations)
        ):
            raise ValueError("closeout needs released personal locks and all confirmed restorations")
        self._record(time_s, permit_id, "close", evidence)
        self.status[permit_id] = "closed"
