"""Versioned claims, evidence and changes keep assessments open to revision."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Claim:
    id: str
    statement: str
    support_ids: tuple[str, ...]


class SafetyCase:
    """A lightweight traceability graph, not an automated proof of plant safety."""

    def __init__(self, claims: tuple[Claim, ...], evidence_versions: dict[str, str]):
        if len({claim.id for claim in claims}) != len(claims):
            raise ValueError("duplicate claim ID")
        self.claims = {claim.id: claim for claim in claims}
        self.evidence_versions = dict(evidence_versions)
        if set(self.claims) & set(evidence_versions):
            raise ValueError("claim and evidence identities overlap")
        available = set(self.claims) | set(evidence_versions)
        for claim in claims:
            if not claim.id.strip() or not claim.statement.strip() or not claim.support_ids:
                raise ValueError("claim requires identity, statement and support")
            if set(claim.support_ids) - available:
                raise ValueError("claim references missing support")
        pending, done = dict(self.claims), set(evidence_versions)
        while pending:
            ready = [key for key, claim in pending.items() if set(claim.support_ids) <= done]
            if not ready:
                raise ValueError("claim graph contains a cycle")
            for key in ready:
                done.add(key)
                del pending[key]

    def affected_by(self, changed_ids):
        changed = set(changed_ids)
        if changed - (set(self.claims) | set(self.evidence_versions)):
            raise ValueError("unknown change identity")
        affected = set()
        while True:
            extra = {
                key for key, claim in self.claims.items() if set(claim.support_ids) & (changed | affected)
            }
            if extra <= affected:
                return tuple(sorted(affected))
            affected |= extra

    def changed_evidence(self, current_versions: dict[str, str]):
        return tuple(
            key for key, version in self.evidence_versions.items() if current_versions.get(key) != version
        )
