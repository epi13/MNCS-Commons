"""Fabric record-family adapters: preserve execution evidence without authority."""

from __future__ import annotations

from typing import Any, Mapping

from ..models import Diagnostic, ResultStatus
from ._common import observation_from_external
from .contracts import AdapterResult

FABRIC_SCHEMA_VERSIONS = frozenset(
    {
        "0.1",  # provisional Commons fixture retained for backward compatibility
        "mncs-fabric.execution-record.v0.1",
    }
)
ARTIFACT_SCHEMA = "mncs-fabric.artifact-manifest.v0.1"
JOB_SCHEMA = "mncs-fabric.job-plan.v0.1"
NODE_SCHEMA = "mncs-fabric.node-capabilities.v0.1"
COHORT_SCHEMA = "mncs-fabric.cohort-result.v0.1"
BUNDLE_BINDING_SCHEMA = "0.1"


def _source_version(value: Mapping[str, Any]) -> str | None:
    raw = value.get("schema_version")
    return str(raw) if raw else None


def _status(value: object, path: str, diagnostics: list[Diagnostic]) -> str:
    status = str(value or "UNKNOWN")
    if status not in {item.value for item in ResultStatus}:
        diagnostics.append(
            Diagnostic("UNKNOWN_SOURCE_STATUS", path, "source status preserved as UNKNOWN")
        )
        return ResultStatus.UNKNOWN.value
    return status


def _fabric_observation(
    value: Mapping[str, Any],
    *,
    source_identity: str | None,
    subject_type: str,
    subject_identity: str,
    summary: str,
    created_at: str | None,
    source_version: str | None,
    diagnostics: list[Diagnostic],
    details: Mapping[str, Any],
    scope_context: Mapping[str, Any],
    evidence_ids: list[str] | None = None,
    unresolved_fields: list[str] | None = None,
) -> AdapterResult:
    return observation_from_external(
        producer_type="fabric",
        producer_id="mncs-fabric",
        source_identity=source_identity,
        subject_type=subject_type,
        subject_identity=subject_identity,
        summary=summary,
        evidence_ids=evidence_ids or [],
        scope_context=scope_context,
        created_at=created_at,
        source_version=source_version,
        diagnostics=diagnostics,
        unresolved_fields=unresolved_fields,
        details={
            "outcome": ResultStatus.UNKNOWN.value,
            "claimVerificationStatus": ResultStatus.UNKNOWN.value,
            "conformanceStatus": ResultStatus.UNKNOWN.value,
            "protectedCustodyStatus": ResultStatus.UNKNOWN.value,
            **dict(details),
        },
    )


def from_fabric_execution(
    execution: Mapping[str, Any], *, subject_identity: str, created_at: str | None = None
) -> AdapterResult:
    """Translate Fabric execution records; execution outcome is not verification."""

    source_version = _source_version(execution)
    if source_version not in FABRIC_SCHEMA_VERSIONS:
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
    required = (
        "schema_version",
        "record_id",
        "job_identity",
        "candidate_identity",
        "artifact_manifest_identity",
        "node",
        "outcome",
        "termination_reason",
        "stdout",
        "stderr",
        "results",
        "limitations",
    )
    diagnostics: list[Diagnostic] = []
    missing = [field for field in required if field not in execution]
    if missing:
        diagnostics.append(
            Diagnostic(
                "INCOMPLETE_SOURCE_RECORD", "record", "Fabric execution fields are incomplete"
            )
        )
    identity = execution.get("record_id")
    source_identity = identity if isinstance(identity, str) and identity else None
    if source_identity is None:
        diagnostics.append(
            Diagnostic(
                "MISSING_SOURCE_IDENTITY",
                "record_id",
                "Fabric record identity is unresolved",
                severity="warning",
            )
        )
    node = execution.get("node")
    environment_identity = node.get("environment_identity") if isinstance(node, Mapping) else None
    outcome = _status(execution.get("outcome"), "outcome", diagnostics)
    return _fabric_observation(
        execution,
        source_identity=source_identity,
        subject_type="artifact",
        subject_identity=subject_identity,
        summary="Fabric execution record referenced without transport or verification authority",
        created_at=created_at or str(execution.get("created_at") or "") or None,
        source_version=source_version,
        diagnostics=diagnostics,
        evidence_ids=[source_identity] if source_identity else [],
        unresolved_fields=missing,
        scope_context={
            "environmentIdentity": environment_identity,
            "node": node,
            "artifactManifestIdentity": execution.get("artifact_manifest_identity"),
            "candidateIdentity": execution.get("candidate_identity"),
            "jobIdentity": execution.get("job_identity"),
        },
        details={"outcome": outcome, "sourceOutcome": outcome, "fabricExecution": dict(execution)},
    )


def from_fabric_artifact_manifest(
    manifest: Mapping[str, Any], *, subject_identity: str, created_at: str | None = None
) -> AdapterResult:
    source_version = _source_version(manifest)
    diagnostics: list[Diagnostic] = []
    if source_version != ARTIFACT_SCHEMA:
        return AdapterResult(
            None,
            (
                Diagnostic(
                    "UNSUPPORTED_SOURCE_VERSION",
                    "schema_version",
                    "Fabric artifact-manifest schema is not supported",
                ),
            ),
            source_version,
            recognized=False,
            unresolved_fields=("schema_version",),
        )
    identity = manifest.get("manifest_identity")
    source_identity = identity if isinstance(identity, str) and identity else None
    if source_identity is None:
        diagnostics.append(
            Diagnostic(
                "MISSING_SOURCE_IDENTITY",
                "manifest_identity",
                "Fabric manifest identity is unresolved",
                severity="warning",
            )
        )
    return _fabric_observation(
        manifest,
        source_identity=source_identity,
        subject_type="artifact-manifest",
        subject_identity=subject_identity,
        summary="Fabric artifact manifest referenced without custody or execution authority",
        created_at=created_at,
        source_version=source_version,
        diagnostics=diagnostics,
        evidence_ids=[source_identity] if source_identity else [],
        unresolved_fields=["source_identity"] if source_identity is None else [],
        scope_context={
            "artifactManifestIdentity": source_identity,
            "fileCount": len(manifest.get("files", []))
            if isinstance(manifest.get("files"), list)
            else None,
        },
        details={
            "fabricArtifactManifest": dict(manifest),
            "manifestIntegrityStatus": ResultStatus.UNKNOWN.value,
        },
    )


def from_fabric_job_plan(
    plan: Mapping[str, Any], *, subject_identity: str, created_at: str | None = None
) -> AdapterResult:
    source_version = _source_version(plan)
    if source_version != JOB_SCHEMA:
        return AdapterResult(
            None,
            (
                Diagnostic(
                    "UNSUPPORTED_SOURCE_VERSION",
                    "schema_version",
                    "Fabric job-plan schema is not supported",
                ),
            ),
            source_version,
            recognized=False,
            unresolved_fields=("schema_version",),
        )
    identity = plan.get("job_identity") or plan.get("job_id")
    diagnostics: list[Diagnostic] = []
    if plan.get("job_identity") is None:
        diagnostics.append(
            Diagnostic(
                "MISSING_SOURCE_IDENTITY",
                "job_identity",
                "job plan has no content identity; job_id is retained as a source reference",
                severity="warning",
            )
        )
    source_identity = str(identity) if identity else None
    return _fabric_observation(
        plan,
        source_identity=source_identity,
        subject_type="job-plan",
        subject_identity=subject_identity,
        summary="Fabric job plan referenced as an inert request description",
        created_at=created_at,
        source_version=source_version,
        diagnostics=diagnostics,
        evidence_ids=[],
        scope_context={
            "candidateIdentity": plan.get("candidate_identity"),
            "artifactManifestIdentity": plan.get("artifact_manifest_identity"),
            "requiredCapabilities": plan.get("required_capabilities"),
            "networkPolicy": plan.get("network_policy"),
        },
        details={
            "fabricJobPlan": dict(plan),
            "authorityBoundary": "independent authorization required",
        },
    )


def from_fabric_node_capabilities(
    capabilities: Mapping[str, Any], *, subject_identity: str, created_at: str | None = None
) -> AdapterResult:
    source_version = _source_version(capabilities)
    if source_version != NODE_SCHEMA:
        return AdapterResult(
            None,
            (
                Diagnostic(
                    "UNSUPPORTED_SOURCE_VERSION",
                    "schema_version",
                    "Fabric node-capabilities schema is not supported",
                ),
            ),
            source_version,
            recognized=False,
            unresolved_fields=("schema_version",),
        )
    identity = capabilities.get("record_id")
    source_identity = identity if isinstance(identity, str) and identity else None
    diagnostics = (
        []
        if source_identity
        else [
            Diagnostic(
                "MISSING_SOURCE_IDENTITY",
                "record_id",
                "node capability record identity is unresolved",
                severity="warning",
            )
        ]
    )
    return _fabric_observation(
        capabilities,
        source_identity=source_identity,
        subject_type="execution-node",
        subject_identity=subject_identity,
        summary="Fabric node capability observation; availability does not prove use",
        created_at=created_at or str(capabilities.get("captured_at") or "") or None,
        source_version=source_version,
        diagnostics=diagnostics,
        evidence_ids=[source_identity] if source_identity else [],
        unresolved_fields=["source_identity"] if source_identity is None else [],
        scope_context={
            "machineLabel": capabilities.get("machine_label"),
            "os": capabilities.get("os"),
            "architecture": capabilities.get("architecture"),
            "pythonVersion": capabilities.get("python_version"),
            "nodeFingerprint": capabilities.get("node_fingerprint"),
        },
        details={
            "fabricNodeCapabilities": dict(capabilities),
            "capabilityUseStatus": ResultStatus.UNKNOWN.value,
        },
    )


def from_fabric_cohort_result(
    cohort: Mapping[str, Any], *, subject_identity: str, created_at: str | None = None
) -> AdapterResult:
    source_version = _source_version(cohort)
    if source_version != COHORT_SCHEMA:
        return AdapterResult(
            None,
            (
                Diagnostic(
                    "UNSUPPORTED_SOURCE_VERSION",
                    "schema_version",
                    "Fabric cohort-result schema is not supported",
                ),
            ),
            source_version,
            recognized=False,
            unresolved_fields=("schema_version",),
        )
    identity = cohort.get("cohort_id")
    source_identity = identity if isinstance(identity, str) and identity else None
    diagnostics: list[Diagnostic] = []
    if source_identity is None:
        diagnostics.append(
            Diagnostic(
                "MISSING_SOURCE_IDENTITY",
                "cohort_id",
                "cohort identity is unresolved",
                severity="warning",
            )
        )
    outcome = _status(cohort.get("outcome"), "outcome", diagnostics)
    return _fabric_observation(
        cohort,
        source_identity=source_identity,
        subject_type="execution-cohort",
        subject_identity=subject_identity,
        summary=(
            "Fabric cohort result preserves bounded reproduction evidence "
            "without independence promotion"
        ),
        created_at=created_at,
        source_version=source_version,
        diagnostics=diagnostics,
        evidence_ids=[str(item) for item in cohort.get("record_identities", []) if item]
        if isinstance(cohort.get("record_identities"), list)
        else [],
        unresolved_fields=["source_identity", "independence"]
        if source_identity is None
        else ["independence"],
        scope_context={
            "candidateIdentity": cohort.get("candidate_identity"),
            "artifactManifestIdentity": cohort.get("artifact_manifest_identity"),
            "machineLabels": cohort.get("machine_labels"),
            "evidenceClass": cohort.get("evidence_class"),
        },
        details={
            "outcome": outcome,
            "sourceOutcome": outcome,
            "fabricCohortResult": dict(cohort),
            "independentEvaluation": "UNKNOWN",
            "protectedCustody": "UNKNOWN",
        },
    )


def from_fabric_bundle_binding(
    binding: Mapping[str, Any], *, subject_identity: str, created_at: str | None = None
) -> AdapterResult:
    """Preserve Fabric's package/receipt identity linkage without assurance."""

    source_version = _source_version(binding)
    if (
        source_version != BUNDLE_BINDING_SCHEMA
        or binding.get("record_type") != "mncs-fabric.execution-bundle-binding"
    ):
        return AdapterResult(
            None,
            (
                Diagnostic(
                    "UNSUPPORTED_SOURCE_VERSION",
                    "schema_version",
                    "Fabric bundle-binding schema is not supported",
                ),
            ),
            source_version,
            recognized=False,
            unresolved_fields=("schema_version",),
        )
    identity = binding.get("binding_identity")
    source_identity = identity if isinstance(identity, str) and identity else None
    return _fabric_observation(
        binding,
        source_identity=source_identity,
        subject_type="execution-bundle-binding",
        subject_identity=subject_identity,
        summary=(
            "Fabric bundle binding preserves package and receipt identities "
            "without assurance or correctness authority"
        ),
        created_at=created_at,
        source_version=source_version,
        diagnostics=[],
        evidence_ids=[
            str(item)
            for item in (
                binding.get("bundle_identity"),
                binding.get("archive_identity"),
                binding.get("receipt_identity"),
            )
            if item
        ],
        unresolved_fields=["source_identity"] if source_identity is None else [],
        scope_context={
            "jobIdentity": binding.get("job_identity"),
            "candidateIdentity": binding.get("candidate_identity"),
            "bundleIdentity": binding.get("bundle_identity"),
            "archiveIdentity": binding.get("archive_identity"),
            "receiptIdentity": binding.get("receipt_identity"),
        },
        details={
            "fabricBundleBinding": dict(binding),
            "bindingIntegrityStatus": ResultStatus.UNKNOWN.value,
            "claimBoundary": binding.get("claim_boundary"),
        },
    )
