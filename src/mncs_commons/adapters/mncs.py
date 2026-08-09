"""MNCS/MNCDS result boundary: preserve validator status without granting conformance."""

from typing import Any, Mapping

from ..models import Diagnostic, ResultStatus
from ._common import observation_from_external
from .contracts import AdapterResult

SUPPORTED_SCHEMA_VERSIONS = frozenset({"0.1", "0.2"})


def from_mncs_result(
    result: Mapping[str, Any], *, subject_identity: str, created_at: str | None = None
) -> AdapterResult:
    source_version = str(result.get("schema_version")) if result.get("schema_version") else None
    if source_version not in SUPPORTED_SCHEMA_VERSIONS:
        return AdapterResult(
            None,
            (
                Diagnostic(
                    "UNSUPPORTED_SOURCE_VERSION",
                    "schema_version",
                    "MNCS result schema version is not supported",
                ),
            ),
            source_version,
            recognized=False,
            unresolved_fields=("schema_version",),
        )
    result_identity = result.get("result_id") or result.get("invariant_id")
    if not isinstance(result_identity, str) or not result_identity:
        result_identity = None
    raw_status = result.get("status", "UNKNOWN")
    status = str(raw_status)
    diagnostics: list[Diagnostic] = []
    if status not in {item.value for item in ResultStatus}:
        status = ResultStatus.UNKNOWN.value
        diagnostics.append(
            Diagnostic(
                "UNKNOWN_SOURCE_STATUS",
                "status",
                "unrecognized validator status preserved as UNKNOWN",
            )
        )
    raw_evidence_references = result.get("evidence_references", [])
    evidence_ids: list[str] = []
    unresolved_fields: list[str] = []
    if isinstance(raw_evidence_references, list):
        evidence_ids = [str(item) for item in raw_evidence_references if item]
    else:
        unresolved_fields.append("evidence_references")
        diagnostics.append(
            Diagnostic(
                "INVALID_SOURCE_EVIDENCE_REFERENCES",
                "evidence_references",
                "non-list evidence references are preserved as unresolved metadata",
                severity="warning",
            )
        )
    if result_identity is None:
        unresolved_fields.append("source_identity")
    return observation_from_external(
        producer_type="mncs-validator",
        producer_id="mncs/mncds",
        source_identity=result_identity,
        subject_type="contract-result",
        subject_identity=subject_identity,
        summary="MNCS validator result imported as inert evidence; conformance remains external",
        evidence_ids=evidence_ids,
        scope_context={
            "mncsVersion": result.get("mncs_version"),
            "contractId": result.get("contract_id"),
            "componentIdentity": result.get("component_identity"),
            "environment": result.get("environment"),
        },
        created_at=created_at or str(result.get("completed_at") or "") or None,
        source_version=source_version,
        diagnostics=diagnostics,
        unresolved_fields=unresolved_fields,
        details={
            "outcome": status,
            "sourceStatus": status,
            "mncsResult": dict(result),
            "commonsVerificationStatus": ResultStatus.UNKNOWN.value,
            "conformanceStatus": ResultStatus.UNKNOWN.value,
        },
    )
