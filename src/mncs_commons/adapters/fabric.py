"""Fabric boundary: preserve execution/environment references as evidence."""

from typing import Any, Mapping

from ..models import Diagnostic, ResultStatus
from ._common import observation_from_external
from .contracts import AdapterResult


def from_fabric_execution(
    execution: Mapping[str, Any], *, subject_identity: str, created_at: str | None = None
) -> AdapterResult:
    identity = execution.get("execution_identity")
    status = str(execution.get("status", execution.get("result", "UNKNOWN")))
    diagnostics: list[Diagnostic] = []
    if status not in {item.value for item in ResultStatus}:
        diagnostics.append(
            Diagnostic("UNKNOWN_SOURCE_STATUS", "status", "status preserved as UNKNOWN")
        )
        status = ResultStatus.UNKNOWN.value
    if not execution.get("environment_identity"):
        diagnostics.append(
            Diagnostic(
                "MISSING_ENVIRONMENT_IDENTITY",
                "environment_identity",
                "Fabric environment identity is unresolved",
                severity="warning",
            )
        )
    return observation_from_external(
        producer_type="fabric",
        producer_id="mncs-fabric",
        source_identity=str(identity) if identity else None,
        subject_type="artifact",
        subject_identity=subject_identity,
        summary="Fabric execution record referenced without granting transport authority",
        evidence_ids=[str(identity)] if identity else [],
        scope_context={"environmentIdentity": execution.get("environment_identity")},
        created_at=created_at,
        source_version=(
            str(execution.get("schema_version"))
            if execution.get("schema_version")
            else None
        ),
        diagnostics=diagnostics,
        details={"outcome": status, "execution": dict(execution)},
    )
