"""MNEL boundary: learned-provider findings remain diagnostic observations."""

from typing import Any, Mapping

from ..models import Diagnostic, ResultStatus
from ._common import observation_from_external
from .contracts import AdapterResult

SUPPORTED_MNEL_SCHEMAS = frozenset({"mnel-ledger-record/0.1", "0.1"})


def from_mnel_observation(
    observation: Mapping[str, Any], *, subject_identity: str, created_at: str | None = None
) -> AdapterResult:
    """Translate both the current ledger envelope and the earlier observation shape."""

    source_schema = observation.get("schema", observation.get("schema_version"))
    legacy_shape = source_schema is None and "observation_identity" in observation
    source_version = str(source_schema) if source_schema else ("0.1" if legacy_shape else None)
    if source_version not in SUPPORTED_MNEL_SCHEMAS:
        return AdapterResult(
            None,
            (
                Diagnostic(
                    "UNSUPPORTED_SOURCE_VERSION",
                    "schema",
                    "MNEL record schema is not supported",
                ),
            ),
            source_version,
            recognized=False,
            unresolved_fields=("schema",),
        )
    payload = observation.get("payload")
    payload_map = payload if isinstance(payload, Mapping) else observation
    identity = observation.get("record_digest") or observation.get("observation_identity")
    provider = payload_map.get("provider_identity") or observation.get("provider_id")
    diagnostics: list[Diagnostic] = []
    if legacy_shape:
        diagnostics.append(
            Diagnostic(
                "LEGACY_SOURCE_SHAPE",
                "schema",
                "legacy MNEL observation shape accepted for compatibility",
                severity="warning",
            )
        )
    if not isinstance(provider, str) or not provider:
        diagnostics.append(
            Diagnostic(
                "MISSING_PROVIDER_IDENTITY",
                "payload.provider_identity",
                "MNEL provider identity is unresolved",
                severity="warning",
            )
        )
        provider = None
    if not isinstance(identity, str) or not identity:
        diagnostics.append(
            Diagnostic(
                "MISSING_SOURCE_IDENTITY",
                "record_digest",
                "MNEL record identity is unresolved",
                severity="warning",
            )
        )
        identity = None
    source_outcome = payload_map.get("outcome_class")
    raw_status = observation.get("status", observation.get("verdict"))
    status = str(raw_status).upper() if raw_status is not None else ResultStatus.UNKNOWN.value
    if status not in {item.value for item in ResultStatus}:
        diagnostics.append(
            Diagnostic("UNKNOWN_SOURCE_STATUS", "status", "status preserved as UNKNOWN")
        )
        status = ResultStatus.UNKNOWN.value
    source_timestamp = created_at or str(observation.get("timestamp") or "") or None
    return observation_from_external(
        producer_type="mnel",
        producer_id="machine-native-experimental-learning",
        source_identity=identity,
        subject_type="experiment",
        subject_identity=str(payload_map.get("experiment_id") or subject_identity),
        summary="MNEL learned-provider observation preserved as diagnostic evidence",
        evidence_ids=[identity] if identity else [],
        scope_context={
            "provider": provider,
            "providerVersion": observation.get("provider_version"),
            "experimentIdentity": payload_map.get("experiment_id"),
        },
        created_at=source_timestamp,
        source_version=source_version,
        diagnostics=diagnostics,
        unresolved_fields=["source_identity"] if identity is None else [],
        details={
            "outcome": status,
            "sourceOutcomeClass": source_outcome,
            "diagnosticOnly": True,
            "mnelRecord": dict(observation),
        },
    )
