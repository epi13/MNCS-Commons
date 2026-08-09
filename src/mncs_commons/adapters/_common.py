from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from ..models import Diagnostic
from .contracts import AdapterResult


def observation_from_external(
    *,
    producer_type: str,
    producer_id: str,
    source_identity: str | None,
    subject_type: str,
    subject_identity: str,
    summary: str,
    evidence_ids: list[str],
    scope_context: Mapping[str, Any],
    created_at: str | None,
    source_version: str | None = None,
    details: Mapping[str, Any] | None = None,
    relationships: list[Mapping[str, Any]] | None = None,
    diagnostics: list[Diagnostic] | None = None,
    unresolved_fields: list[str] | None = None,
) -> AdapterResult:
    """Build an inert Observation without importing or invoking the source system."""

    result_diagnostics = list(diagnostics or [])
    unresolved = list(unresolved_fields or [])
    if not source_identity:
        result_diagnostics.append(
            Diagnostic(
                "MISSING_SOURCE_IDENTITY",
                "provenance.sourceRecords",
                "source identity was not supplied; no fabricated identity was created",
                severity="warning",
            )
        )
        unresolved.append("source_identity")
    if not created_at:
        result_diagnostics.append(
            Diagnostic(
                "MISSING_SOURCE_TIMESTAMP",
                "metadata.createdAt",
                "source observation timestamp must be supplied by the caller",
            )
        )
        unresolved.append("created_at")
        return AdapterResult(
            None,
            tuple(result_diagnostics),
            source_version,
            recognized=True,
            unresolved_fields=tuple(sorted(set(unresolved))),
        )
    try:
        parsed = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("timezone required")
    except ValueError:
        result_diagnostics.append(
            Diagnostic(
                "INVALID_SOURCE_TIMESTAMP",
                "metadata.createdAt",
                "timestamp must include timezone",
            )
        )
        return AdapterResult(
            None,
            tuple(result_diagnostics),
            source_version,
            recognized=True,
            unresolved_fields=tuple(sorted(set(unresolved))),
        )
    record = {
        "apiVersion": "commons.mncs.dev/v0alpha1",
        "kind": "Observation",
        "metadata": {
            "createdAt": created_at,
            "author": {"type": producer_type, "id": producer_id},
        },
        "subject": {"type": subject_type, "identity": subject_identity},
        "scope": {
            "context": dict(scope_context),
            "limitations": [
                "external adapter preserves source data without interpreting authority"
            ],
        },
        "statement": {"summary": summary},
        "evidence": [{"id": item, "relation": "supports"} for item in evidence_ids],
        "dependencies": [],
        "affectedContracts": [],
        "provenance": {
            "producer": {"type": producer_type, "id": producer_id},
            "sourceRecords": [source_identity] if source_identity else [],
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
    return AdapterResult(
        record,
        tuple(result_diagnostics),
        source_version,
        recognized=True,
        unresolved_fields=tuple(sorted(set(unresolved))),
    )
