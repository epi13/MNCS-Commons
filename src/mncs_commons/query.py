"""Deterministic filtering and scope compatibility checks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Iterable, Mapping


class ScopeAssessment(StrEnum):
    COMPATIBLE = "compatible"
    INCOMPATIBLE = "incompatible"
    REVIEW_REQUIRED = "review-required"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class QueryFilter:
    kind: str | None = None
    state: str | None = None
    subject: str | None = None
    contract: str | None = None
    artifact: str | None = None
    related: str | None = None
    open_work_requests: bool = False
    needs_review: bool = False


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def assess_scope(
    record: Mapping[str, Any], current_context: Mapping[str, Any], *, now: datetime | None = None
) -> ScopeAssessment:
    """Compare declared material context exactly; version similarity is not equivalence."""

    scope = record.get("scope")
    if not isinstance(scope, Mapping):
        return ScopeAssessment.UNKNOWN
    review_at = scope.get("reviewAt")
    if review_at:
        try:
            moment = _parse_timestamp(str(review_at))
            current_time = now or datetime.now(timezone.utc)
            if moment <= current_time:
                return ScopeAssessment.REVIEW_REQUIRED
        except ValueError:
            return ScopeAssessment.UNKNOWN
    declared = scope.get("context")
    if not isinstance(declared, Mapping) or not declared:
        return ScopeAssessment.UNKNOWN
    compared = False
    for key, expected in declared.items():
        if key not in current_context:
            return ScopeAssessment.UNKNOWN
        compared = True
        if current_context[key] != expected:
            return ScopeAssessment.INCOMPATIBLE
    return ScopeAssessment.COMPATIBLE if compared else ScopeAssessment.UNKNOWN


def record_matches(record: Mapping[str, Any], query: QueryFilter, state: str | None = None) -> bool:
    if query.kind and record.get("kind") != query.kind:
        return False
    if query.state and state != query.state:
        return False
    subject = record.get("subject", {})
    if query.subject and not (
        isinstance(subject, Mapping)
        and query.subject in {subject.get("identity"), subject.get("type")}
    ):
        return False
    if query.contract:
        contracts = record.get("affectedContracts", [])
        subject_contracts = subject.get("contracts", []) if isinstance(subject, Mapping) else []
        if query.contract not in contracts and query.contract not in subject_contracts:
            return False
    if query.artifact:
        artifacts = {
            item.get("id") for item in record.get("evidence", []) if isinstance(item, Mapping)
        }
        if (
            query.artifact not in artifacts
            and record.get("subject", {}).get("identity") != query.artifact
        ):
            return False
    if query.related:
        relationships = record.get("relationships", [])
        if not any(
            isinstance(item, Mapping) and item.get("target") == query.related
            for item in relationships
        ):
            return False
    if query.open_work_requests:
        return record.get("kind") == "WorkRequest" and state in {
            "proposed",
            "reproduced",
            "disputed",
        }
    return True


def records_for(
    records: Iterable[Mapping[str, Any]], query: QueryFilter, states: Mapping[str, str]
) -> list[Mapping[str, Any]]:
    result = [
        record
        for record in records
        if record_matches(record, query, states.get(str(record.get("contentDigest"))))
    ]
    return sorted(
        result,
        key=lambda item: (
            str(item.get("metadata", {}).get("createdAt", "")),
            str(item.get("contentDigest", "")),
        ),
    )


def unresolved_relationships(
    record: Mapping[str, Any], known_references: set[str]
) -> list[Mapping[str, Any]]:
    """Return unresolved typed edges without treating them as validation failures."""

    return [
        relationship
        for relationship in record.get("relationships", [])
        if isinstance(relationship, Mapping) and relationship.get("target") not in known_references
    ]
