"""Fabric compatibility boundary: preserve execution evidence without execution authority."""

from typing import Any, Mapping

from ..models import Diagnostic, ResultStatus
from ._common import observation_from_external
from .contracts import AdapterResult

SUPPORTED_FABRIC_SCHEMA_VERSIONS = frozenset({"0.1"})
REQUIRED_FIELDS = (
    "schema_version",
    "record_id",
    "job_identity",
    "candidate_identity",
    "evaluator_identity",
    "artifact_manifest_identity",
    "node",
    "outcome",
    "termination_reason",
    "results",
    "limitations",
)


def from_fabric_execution(
    execution: Mapping[str, Any], *, subject_identity: str, created_at: str | None = None
) -> AdapterResult:
    """Translate the current Fabric execution envelope as inert Commons evidence.

    The local workspace does not contain the Fabric repository, so the field contract is explicit
    but remains marked UNKNOWN by the compatibility registry until a checked-in Fabric source
    fingerprint and fixture are available.
    """

    source_version = (
        str(execution.get("schema_version")) if execution.get("schema_version") else None
    )
    if source_version not in SUPPORTED_FABRIC_SCHEMA_VERSIONS:
        return AdapterResult(
            None,
            (
                Diagnostic(
                    "UNSUPPORTED_SOURCE_VERSION",
                    "schema_version",
                    "Fabric execution schema version is not supported",
                ),
            ),
            source_version,
            recognized=False,
            unresolved_fields=("schema_version",),
        )
    diagnostics: list[Diagnostic] = []
    missing = [field for field in REQUIRED_FIELDS if field not in execution]
    if missing:
        diagnostics.append(
            Diagnostic(
                "INCOMPLETE_SOURCE_RECORD",
                "record",
                "current Fabric execution fields are incomplete",
            )
        )
    record_identity = execution.get("record_id")
    if not isinstance(record_identity, str) or not record_identity:
        record_identity = None
        diagnostics.append(
            Diagnostic(
                "MISSING_SOURCE_IDENTITY",
                "record_id",
                "Fabric record identity is unresolved",
                severity="warning",
            )
        )
    outcome = str(execution.get("outcome", "UNKNOWN"))
    if outcome not in {item.value for item in ResultStatus}:
        diagnostics.append(
            Diagnostic("UNKNOWN_SOURCE_STATUS", "outcome", "outcome preserved as UNKNOWN")
        )
        outcome = ResultStatus.UNKNOWN.value
    node = execution.get("node")
    environment_identity = (
        node.get("environment_identity")
        if isinstance(node, Mapping)
        else None
    )
    return observation_from_external(
        producer_type="fabric",
        producer_id="mncs-fabric",
        source_identity=record_identity,
        subject_type="artifact",
        subject_identity=subject_identity,
        summary=(
            "Fabric execution record referenced without granting transport or verification "
            "authority"
        ),
        evidence_ids=[record_identity] if record_identity else [],
        scope_context={
            "environmentIdentity": environment_identity,
            "node": node,
            "artifactManifestIdentity": execution.get("artifact_manifest_identity"),
            "candidateIdentity": execution.get("candidate_identity"),
        },
        created_at=created_at or str(execution.get("created_at") or "") or None,
        source_version=source_version,
        diagnostics=diagnostics,
        unresolved_fields=missing,
        details={
            "outcome": outcome,
            "sourceOutcome": outcome,
            "claimVerificationStatus": ResultStatus.UNKNOWN.value,
            "conformanceStatus": ResultStatus.UNKNOWN.value,
            "protectedCustodyStatus": ResultStatus.UNKNOWN.value,
            "fabricExecution": dict(execution),
        },
    )


def from_fabric_artifact_manifest(
    manifest: Mapping[str, Any], *, subject_identity: str, created_at: str | None = None
) -> AdapterResult:
    """Preserve an artifact-manifest reference without interpreting its contents."""

    source_version = str(manifest.get("schema_version")) if manifest.get("schema_version") else None
    identity = manifest.get("manifest_identity") or manifest.get("record_id")
    diagnostics: list[Diagnostic] = []
    if not isinstance(identity, str) or not identity:
        diagnostics.append(
            Diagnostic(
                "MISSING_SOURCE_IDENTITY",
                "manifest_identity",
                "Fabric artifact manifest identity is unresolved",
                severity="warning",
            )
        )
        identity = None
    return observation_from_external(
        producer_type="fabric",
        producer_id="mncs-fabric",
        source_identity=identity,
        subject_type="artifact-manifest",
        subject_identity=subject_identity,
        summary="Fabric artifact manifest referenced without custody or execution authority",
        evidence_ids=[identity] if identity else [],
        scope_context={"artifactManifest": dict(manifest)},
        created_at=created_at,
        source_version=source_version,
        diagnostics=diagnostics,
        details={
            "outcome": ResultStatus.UNKNOWN.value,
            "fabricArtifactManifest": dict(manifest),
            "custodyStatus": ResultStatus.UNKNOWN.value,
        },
        unresolved_fields=["source_identity"] if identity is None else [],
    )
