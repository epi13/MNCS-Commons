"""RAVEL boundary: expose scoped knowledge without deciding what is learned."""

from typing import Any, Mapping

from ..models import Diagnostic, ResultStatus
from ._common import observation_from_external
from .contracts import AdapterResult


def knowledge_view(
    record: Mapping[str, Any], *, lifecycle_state: str, domain: str | None = None
) -> dict[str, Any]:
    """Expose a governed candidate view without deciding what RAVEL learns."""

    return {
        "recordDigest": record.get("contentDigest"),
        "kind": record.get("kind"),
        "subject": record.get("subject"),
        "statement": record.get("statement"),
        "outcome": record.get("details", {}).get("outcome")
        if isinstance(record.get("details"), Mapping)
        else None,
        "lifecycleState": lifecycle_state,
        "acceptanceDomain": domain,
        "evidence": record.get("evidence", []),
        "scope": record.get("scope", {}),
        "negativeOrDisputed": lifecycle_state in {"disputed", "rejected"}
        or (record.get("details", {}).get("outcome") == "FAIL"),
        "promotionAuthority": "external-ravel-policy-required",
    }


def from_development_record(
    record: Mapping[str, Any], *, subject_identity: str, created_at: str | None = None
) -> AdapterResult:
    """Translate a frozen RAVEL development record without promoting it."""

    schema = record.get("schema") or record.get("record_type") or record.get("kind")
    if not isinstance(schema, str) or not schema:
        if "candidate_training_evaluations" in record:
            schema = "ravel-matched-compute/0.1"
        elif "committed" in record and "rollback_byte_identical" in record:
            schema = "ravel-transaction/0.1"
    version = str(record.get("schema_version")) if record.get("schema_version") else None
    if not isinstance(schema, str) or not schema:
        return AdapterResult(
            None,
            (
                Diagnostic(
                    "MISSING_SOURCE_RECORD_TYPE",
                    "schema",
                    "RAVEL record family is required for compatibility resolution",
                ),
            ),
            version,
            recognized=True,
            unresolved_fields=("record_type",),
        )
    identity = next(
        (
            record.get(key)
            for key in (
                "record_identity",
                "transaction_identity",
                "candidate_identity",
                "preregistration_identity",
                "identity",
            )
            if isinstance(record.get(key), str) and record.get(key)
        ),
        None,
    )
    source_identity = str(identity) if identity else None
    raw_status = str(record.get("status", record.get("formal_status", {}).get("mncs", "UNKNOWN")))
    status = (
        raw_status.upper()
        if raw_status.upper() in {item.value for item in ResultStatus}
        else ResultStatus.UNKNOWN.value
    )
    unresolved = [] if source_identity else ["source_identity"]
    return observation_from_external(
        producer_type="ravel",
        producer_id="ravel",
        source_identity=source_identity,
        subject_type="ravel-development-record",
        subject_identity=subject_identity,
        summary=(
            "RAVEL development evidence preserved without promotion or final-evaluation authority"
        ),
        evidence_ids=[source_identity] if source_identity else [],
        scope_context={
            "schema": schema,
            "schemaVersion": version,
            "thresholdIdentity": record.get("threshold_identity"),
            "providerIdentity": record.get("provider_identity"),
            "comparatorIdentity": record.get("comparator_identity"),
        },
        created_at=created_at,
        source_version=version,
        details={
            "outcome": status,
            "sourceStatus": status,
            "ravelDevelopmentRecord": dict(record),
            "promotionAuthority": "external-ravel-policy-required",
            "finalEvaluationStatus": ResultStatus.UNKNOWN.value,
        },
        unresolved_fields=unresolved,
    )
