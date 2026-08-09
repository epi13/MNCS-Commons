"""Forge boundary: references typed Forge evidence; never dispatches Forge work."""

from typing import Any, Mapping

from ..models import Diagnostic, ResultStatus
from ._common import observation_from_external
from .contracts import AdapterResult

SUPPORTED_FORGE_SCHEMA_VERSIONS = frozenset({"0.1", "1"})


def from_forge_result(
    result: Mapping[str, Any],
    *,
    subject_identity: str,
    scope_context: Mapping[str, Any],
    created_at: str | None = None,
) -> AdapterResult:
    source_version = str(result.get("schema_version")) if result.get("schema_version") else None
    diagnostics: list[Diagnostic] = []
    if source_version not in SUPPORTED_FORGE_SCHEMA_VERSIONS:
        return AdapterResult(
            None,
            (
                Diagnostic(
                    "UNSUPPORTED_SOURCE_VERSION",
                    "schema_version",
                    "Forge record schema version is not supported",
                ),
            ),
            source_version,
            recognized=False,
            unresolved_fields=("schema_version",),
        )
    record_type = result.get("record_type")
    if not isinstance(record_type, str) or not record_type:
        diagnostics.append(
            Diagnostic(
                "MISSING_SOURCE_RECORD_TYPE",
                "record_type",
                "Forge record_type is required to identify the producer schema",
            )
        )
    identity = next(
        (
            result.get(key)
            for key in ("output_identity", "record_identity", "result_identity")
            if isinstance(result.get(key), str) and result.get(key)
        ),
        None,
    )
    execution = result.get("execution")
    source_time = created_at
    if source_time is None and isinstance(execution, Mapping):
        value = execution.get("started_at")
        source_time = str(value) if value else None
    raw_status = result.get("result", result.get("status", "UNKNOWN"))
    status = str(raw_status)
    if status not in {item.value for item in ResultStatus}:
        diagnostics.append(
            Diagnostic(
                "UNKNOWN_SOURCE_STATUS",
                "result",
                "unrecognized Forge status preserved as UNKNOWN",
            )
        )
        status = ResultStatus.UNKNOWN.value
    return observation_from_external(
        producer_type="forge",
        producer_id="mncs-forge-mcp",
        source_identity=str(identity) if identity else None,
        subject_type="artifact",
        subject_identity=subject_identity,
        summary="Forge typed result imported as inert evidence reference",
        evidence_ids=[str(identity)] if identity else [],
        scope_context=scope_context,
        created_at=source_time,
        source_version=source_version,
        diagnostics=diagnostics,
        unresolved_fields=["source_identity"] if not identity else [],
        details={
            "outcome": status,
            "forgeRecordType": record_type,
            "forgeResult": dict(result),
        },
    )


def from_forge_work_request(
    request: Mapping[str, Any],
    *,
    subject_identity: str,
    scope_context: Mapping[str, Any],
    created_at: str | None = None,
) -> AdapterResult:
    identity = request.get("request_identity") or request.get("request_id")
    return observation_from_external(
        producer_type="forge",
        producer_id="mncs-forge-mcp",
        source_identity=str(identity) if identity else None,
        subject_type="artifact",
        subject_identity=subject_identity,
        summary="Forge work request preserved as inert information for authorized review",
        evidence_ids=[],
        scope_context=scope_context,
        created_at=created_at,
        source_version=(
            str(request.get("schema_version")) if request.get("schema_version") else None
        ),
        details={"outcome": "UNKNOWN", "request": dict(request)},
    )
