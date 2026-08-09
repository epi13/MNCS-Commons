from __future__ import annotations

from typing import Any, Mapping


def observation_from_external(
    *,
    producer_type: str,
    producer_id: str,
    source_identity: str,
    subject_type: str,
    subject_identity: str,
    summary: str,
    evidence_ids: list[str],
    scope_context: Mapping[str, Any],
    details: Mapping[str, Any] | None = None,
    relationships: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build an inert Observation without importing or invoking the source system."""

    return {
        "apiVersion": "commons.mncs.dev/v0alpha1",
        "kind": "Observation",
        "metadata": {
            "createdAt": "1970-01-01T00:00:00Z",
            "author": {"type": producer_type, "id": producer_id},
        },
        "subject": {"type": subject_type, "identity": subject_identity},
        "scope": {
            "context": dict(scope_context),
            "limitations": ["timestamp and local review must be supplied by caller"],
        },
        "statement": {"summary": summary},
        "evidence": [{"id": item, "relation": "supports"} for item in evidence_ids],
        "dependencies": [],
        "affectedContracts": [],
        "provenance": {
            "producer": {"type": producer_type, "id": producer_id},
            "sourceRecords": [source_identity],
        },
        "confidence": {
            "level": "unreported",
            "rationale": "external adapter does not infer confidence",
        },
        "security": {
            "sensitivity": "public",
            "executableAttachments": False,
            "instructionsAreUntrusted": True,
        },
        "lifecycle": {"initialState": "proposed", "reviewWhen": []},
        "relationships": relationships or [],
        "details": {"outcome": "UNKNOWN", **dict(details or {})},
    }
