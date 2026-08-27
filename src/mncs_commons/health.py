"""Bounded intake for externally observed family health, without repository crawling."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from .canonical import canonical_digest

HEALTH_OBSERVATION_TYPE = "family-health"
HEALTH_OUTCOMES = frozenset({"PASS", "FAIL", "UNKNOWN"})
_MAX_ITEMS = 128
_MAX_TEXT = 16_384


def _text(value: object, field: str, *, maximum: int = _MAX_TEXT) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum or "\x00" in value:
        raise ValueError(f"{field} must be bounded non-empty text")
    return value.strip()


def parse_health_instant(value: str) -> datetime:
    """Parse an ISO-8601 timestamp to a timezone-aware UTC instant.

    Rejects naive timestamps (no timezone offset) unless there is an
    intentionally documented policy. Commons requires explicit timezone
    info and normalizes to UTC for chronological comparison.
    """

    text = value.strip()
    try:
        instant = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("observedAt must be an ISO-8601 timestamp") from error
    if instant.tzinfo is None:
        raise ValueError("observedAt must include timezone info (e.g. Z or +00:00)")
    return instant.astimezone(timezone.utc)


def normalize_health_instant(value: str) -> str:
    """Return a normalized UTC ISO-8601 string with Z suffix."""

    instant = parse_health_instant(value)
    return instant.isoformat().replace("+00:00", "Z")


def normalize_health_observation(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and normalize one scanner-produced, inert health observation."""

    allowed = {
        "repository",
        "outcome",
        "observedAt",
        "source",
        "sourceIdentity",
        "runIdentity",
        "findingIdentity",
        "finding",
        "categories",
        "evidence",
    }
    if set(value) - allowed:
        raise ValueError("health observation contains unexpected fields")
    repository = _text(value.get("repository"), "repository", maximum=512)
    outcome = _text(value.get("outcome"), "outcome", maximum=16).upper()
    if outcome not in HEALTH_OUTCOMES:
        raise ValueError("outcome must be PASS, FAIL, or UNKNOWN")
    observed_at_raw = _text(value.get("observedAt"), "observedAt", maximum=64)
    observed_at = normalize_health_instant(observed_at_raw)
    source = _text(value.get("source"), "source", maximum=512)
    source_identity = _text(value.get("sourceIdentity", source), "sourceIdentity", maximum=1024)
    categories = value.get("categories", [])
    if not isinstance(categories, list) or len(categories) > _MAX_ITEMS:
        raise ValueError("categories must be a bounded list")
    category_values = [_text(item, "categories[]", maximum=128) for item in categories]
    evidence = value.get("evidence", [])
    if not isinstance(evidence, list) or len(evidence) > _MAX_ITEMS:
        raise ValueError("evidence must be a bounded list")
    evidence_values = [_text(item, "evidence[]", maximum=1024) for item in evidence]
    finding = value.get("finding")
    finding_value = None if finding is None else _text(finding, "finding")
    run_identity = value.get("runIdentity")
    run_value = None if run_identity is None else _text(run_identity, "runIdentity", maximum=1024)
    finding_identity = value.get("findingIdentity")
    if finding_identity is None:
        category = category_values[0] if category_values else "general"
        finding_identity = f"health:{repository}:{category}"
    finding_value_id = _text(finding_identity, "findingIdentity", maximum=1024)
    return {
        "repository": repository,
        "outcome": outcome,
        "observedAt": observed_at,
        "source": source,
        "sourceIdentity": source_identity,
        "runIdentity": run_value,
        "findingIdentity": finding_value_id,
        "finding": finding_value,
        "categories": category_values,
        "evidence": evidence_values,
    }


def health_observation_record(value: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build a protocol Observation and return it with its normalized input."""

    observation = normalize_health_observation(value)
    identity = {
        key: observation[key]
        for key in ("repository", "outcome", "observedAt", "sourceIdentity", "findingIdentity")
    }
    record_id = (
        "observation:family-health:"
        f"{canonical_digest(identity).removeprefix('sha256:')}"
    )
    evidence = [
        {
            "id": observation["sourceIdentity"],
            "relation": "supports",
            "status": observation["outcome"],
        }
    ]
    if observation["runIdentity"]:
        evidence.append(
            {
                "id": observation["runIdentity"],
                "relation": "references",
                "status": observation["outcome"],
            }
        )
    evidence.extend(
        {"id": item, "relation": "references", "status": observation["outcome"]}
        for item in observation["evidence"]
    )
    details: dict[str, Any] = {
        "outcome": observation["outcome"],
        "observationType": HEALTH_OBSERVATION_TYPE,
        "healthRepository": observation["repository"],
        "observedAt": observation["observedAt"],
        "source": observation["source"],
        "sourceIdentity": observation["sourceIdentity"],
        "findingIdentity": observation["findingIdentity"],
        "categories": observation["categories"],
    }
    for key in ("runIdentity", "finding"):
        if observation[key] is not None:
            details[key] = observation[key]
    record = {
        "apiVersion": "commons.mncs.dev/v0alpha1",
        "kind": "Observation",
        "metadata": {
            "recordId": record_id,
            "createdAt": observation["observedAt"],
            "author": {"type": "health-scanner", "id": observation["source"]},
            "labels": ["family-health", "untrusted"],
        },
        "subject": {"type": "repository", "identity": observation["repository"]},
        "scope": {
            "context": {"repository": observation["repository"]},
            "limitations": [
                "scanner observation is not a repository authorization or execution result",
                "health is current only at the observedAt timestamp",
            ],
        },
        "statement": {
            "summary": f"Family health observation for {observation['repository']}",
            "details": observation["finding"] or "No additional finding was supplied.",
        },
        "evidence": evidence,
        "reproduction": {
            "prerequisites": ["the scanner's independently authorized source"],
            "procedure": [{"source": observation["sourceIdentity"]}],
            "expected": ["preserve PASS, FAIL, or UNKNOWN with freshness metadata"],
        },
        "dependencies": [],
        "affectedContracts": [],
        "provenance": {
            "producer": {"type": "health-scanner", "id": observation["source"]},
            "sourceRecords": [observation["sourceIdentity"]],
        },
        "confidence": {
            "level": "unreported",
            "rationale": "scanner output is an untrusted observation at a declared time",
        },
        "security": {
            "sensitivity": "restricted",
            "executableAttachments": False,
            "instructionsAreUntrusted": True,
            "requiredExternalAuthority": True,
        },
        "lifecycle": {"initialState": "proposed", "reviewWhen": ["source or revision changes"]},
        "relationships": [],
        "details": details,
    }
    return record, observation


__all__ = [
    "HEALTH_OBSERVATION_TYPE",
    "HEALTH_OUTCOMES",
    "health_observation_record",
    "normalize_health_observation",
    "normalize_health_instant",
    "parse_health_instant",
]
