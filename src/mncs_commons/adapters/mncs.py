"""MNCS/MNCDS result boundary: preserve validator status without granting conformance."""

from typing import Any, Mapping, cast

from ..models import Diagnostic, ResultStatus
from ._common import observation_from_external
from .contracts import AdapterResult

SUPPORTED_SCHEMA_VERSIONS = frozenset({"0.1", "0.2"})
EXECUTION_RECEIPT_SCHEMA = "0.1-experimental"
EXECUTION_BUNDLE_SCHEMA = "0.1-experimental"
EXECUTION_PLACEMENT_SCHEMA = "0.1-experimental"


def _mncs_external(
    value: Mapping[str, Any],
    *,
    source_identity: str | None,
    subject_type: str,
    subject_identity: str,
    summary: str,
    created_at: str | None,
    source_version: str,
    details: Mapping[str, Any],
    scope_context: Mapping[str, Any],
    evidence_ids: list[str] | None = None,
    unresolved_fields: list[str] | None = None,
) -> AdapterResult:
    return observation_from_external(
        producer_type="mncs",
        producer_id="machine-native-complexity-standard",
        source_identity=source_identity,
        subject_type=subject_type,
        subject_identity=subject_identity,
        summary=summary,
        evidence_ids=evidence_ids or [],
        scope_context=scope_context,
        created_at=created_at,
        source_version=source_version,
        unresolved_fields=unresolved_fields,
        details={
            "outcome": "UNKNOWN",
            "commonsVerificationStatus": "UNKNOWN",
            "conformanceStatus": "UNKNOWN",
            **dict(details),
        },
    )


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


def from_mncs_execution_receipt(
    receipt: Mapping[str, Any], *, subject_identity: str, created_at: str | None = None
) -> AdapterResult:
    version = str(receipt.get("schema_version")) if receipt.get("schema_version") else None
    if (
        version != EXECUTION_RECEIPT_SCHEMA
        or receipt.get("record_type") != "mncs-execution-receipt"
    ):
        return AdapterResult(
            None,
            (
                Diagnostic(
                    "UNSUPPORTED_SOURCE_VERSION",
                    "schema_version",
                    "MNCS execution receipt schema is not supported",
                ),
            ),
            version,
            recognized=False,
            unresolved_fields=("schema_version",),
        )
    identity = receipt.get("receipt_identity") or receipt.get("record_id")
    source_identity = identity if isinstance(identity, str) and identity else None
    lifecycle = receipt.get("lifecycle")
    timestamp = created_at
    if timestamp is None and isinstance(lifecycle, Mapping):
        timestamp = str(lifecycle.get("started_at") or "") or None
    process: Mapping[str, Any] = (
        cast(Mapping[str, Any], receipt.get("process"))
        if isinstance(receipt.get("process"), Mapping)
        else {}
    )
    source_status = str(process.get("harness_status") or "UNKNOWN")
    if source_status not in {item.value for item in ResultStatus}:
        source_status = ResultStatus.UNKNOWN.value
    bundle: Mapping[str, Any] = (
        cast(Mapping[str, Any], receipt.get("bundle"))
        if isinstance(receipt.get("bundle"), Mapping)
        else {}
    )
    return _mncs_external(
        receipt,
        source_identity=source_identity,
        subject_type="execution-receipt",
        subject_identity=subject_identity,
        summary=(
            "MNCS execution receipt preserved as observation; execution is not "
            "correctness or assurance"
        ),
        created_at=timestamp,
        source_version=version,
        evidence_ids=[
            str(item)
            for item in (receipt.get("artifacts") or [])
            if isinstance(item, Mapping) and item.get("identity")
        ],
        scope_context={
            "bundleIdentity": bundle.get("test_bundle_identity"),
            "environment": receipt.get("environment"),
            "runner": receipt.get("runner"),
            "placement": receipt.get("placement"),
        },
        details={
            "outcome": "UNKNOWN",
            "sourceExecutionStatus": source_status,
            "executionReceipt": dict(receipt),
            "executionAssuranceStatus": "UNKNOWN",
            "claimBoundary": receipt.get("claim_boundary"),
        },
        unresolved_fields=[] if source_identity else ["source_identity"],
    )


def from_mncs_execution_bundle(
    bundle: Mapping[str, Any], *, subject_identity: str, created_at: str | None = None
) -> AdapterResult:
    version = str(bundle.get("schema_version")) if bundle.get("schema_version") else None
    if version != EXECUTION_BUNDLE_SCHEMA or bundle.get("record_type") != "mncs-execution-bundle":
        return AdapterResult(
            None,
            (
                Diagnostic(
                    "UNSUPPORTED_SOURCE_VERSION",
                    "schema_version",
                    "MNCS execution bundle schema is not supported",
                ),
            ),
            version,
            recognized=False,
            unresolved_fields=("schema_version",),
        )
    identity = bundle.get("bundle_identity") or bundle.get("bundle_id")
    source_identity = identity if isinstance(identity, str) and identity else None
    return _mncs_external(
        bundle,
        source_identity=source_identity,
        subject_type="execution-bundle",
        subject_identity=subject_identity,
        summary=(
            "MNCS execution bundle referenced as package-integrity evidence, "
            "not execution authority"
        ),
        created_at=created_at,
        source_version=version,
        evidence_ids=[],
        scope_context={
            "bundleFormat": bundle.get("bundle_format"),
            "harnessIdentity": bundle.get("harness_identity"),
            "inputSnapshotIdentity": bundle.get("input_snapshot_identity"),
            "policyIdentity": bundle.get("policy_identity"),
        },
        details={
            "executionBundle": dict(bundle),
            "bundleIntegrityStatus": "UNKNOWN",
            "executionStatus": "UNKNOWN",
        },
        unresolved_fields=[] if source_identity else ["source_identity"],
    )


def from_mncs_execution_placement(
    placement: Mapping[str, Any], *, subject_identity: str, created_at: str | None = None
) -> AdapterResult:
    version = str(placement.get("schema_version")) if placement.get("schema_version") else None
    if (
        version != EXECUTION_PLACEMENT_SCHEMA
        or placement.get("profile") != "execution-placement-evidence"
    ):
        return AdapterResult(
            None,
            (
                Diagnostic(
                    "UNSUPPORTED_SOURCE_VERSION",
                    "schema_version",
                    "MNCS execution-placement schema is not supported",
                ),
            ),
            version,
            recognized=False,
            unresolved_fields=("schema_version",),
        )
    identity = placement.get("record_id")
    source_identity = identity if isinstance(identity, str) and identity else None
    results: Mapping[str, Any] = (
        cast(Mapping[str, Any], placement.get("results"))
        if isinstance(placement.get("results"), Mapping)
        else {}
    )
    raw_status = results.get("status", "UNKNOWN")
    status = (
        str(raw_status) if str(raw_status) in {item.value for item in ResultStatus} else "UNKNOWN"
    )
    identities: Mapping[str, Any] = (
        cast(Mapping[str, Any], placement.get("identities"))
        if isinstance(placement.get("identities"), Mapping)
        else {}
    )
    return _mncs_external(
        placement,
        source_identity=source_identity,
        subject_type="execution-placement",
        subject_identity=subject_identity,
        summary=(
            "MNCS execution-placement evidence preserved as bounded "
            "environment-scoped observation"
        ),
        created_at=created_at,
        source_version=version,
        evidence_ids=[
            str(item.get("evidence_id"))
            for item in placement.get("placement_evidence", [])
            if isinstance(item, Mapping) and item.get("evidence_id")
        ],
        scope_context={
            "environmentIdentity": identities.get("environment_id"),
            "providerIdentity": identities.get("provider_id"),
            "runtimeIdentity": identities.get("runtime_id"),
            "requestedPolicy": placement.get("requested_policy"),
        },
        details={
            "outcome": "UNKNOWN",
            "sourcePlacementStatus": status,
            "executionPlacement": dict(placement),
            "claimBoundary": placement.get("claim_boundary"),
        },
        unresolved_fields=[] if source_identity else ["source_identity"],
    )
