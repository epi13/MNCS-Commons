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


def from_provider_study_record(
    record: Mapping[str, Any], *, subject_identity: str, created_at: str | None = None
) -> AdapterResult:
    """Translate MNEL 0.4 portfolio records as diagnostic-only observations."""

    schema = record.get("schema")
    if not isinstance(schema, str) or not schema.startswith("mnel-") or not schema.endswith("/0.4"):
        return AdapterResult(
            None,
            (
                Diagnostic(
                    "UNSUPPORTED_SOURCE_VERSION",
                    "schema",
                    "MNEL provider-study schema is not supported",
                ),
            ),
            str(schema) if schema else None,
            recognized=False,
            unresolved_fields=("schema",),
        )
    identity_keys = (
        "metadata_identity",
        "case_identity",
        "policy_identity",
        "selection_identity",
        "study_identity",
        "run_identity",
        "metric_identity",
        "comparison_identity",
        "transition_identity",
        "measurement_identity",
        "rollback_identity",
        "study_identity",
    )
    source_identity = next(
        (
            str(record[key])
            for key in identity_keys
            if isinstance(record.get(key), str) and record[key]
        ),
        None,
    )
    unresolved: list[str] = []
    diagnostics: list[Diagnostic] = []
    if source_identity is None:
        diagnostics.append(
            Diagnostic(
                "MISSING_SOURCE_IDENTITY",
                "identity",
                "MNEL provider record identity is unresolved",
                severity="warning",
            )
        )
        unresolved.append("source_identity")
    return observation_from_external(
        producer_type="mnel",
        producer_id="Machine-Native-Experimental-Learning",
        source_identity=source_identity,
        subject_type="learned-provider-study",
        subject_identity=subject_identity,
        summary="MNEL provider-portfolio record preserved as diagnostic evidence; not a verdict",
        evidence_ids=[str(item) for item in record.get("evidence_identities", []) if item]
        if isinstance(record.get("evidence_identities"), list)
        else [],
        scope_context={
            "providerId": record.get("provider_id"),
            "providerFamily": record.get("provider_family"),
            "architectureFamily": record.get("architecture_family"),
            "objectiveFamily": record.get("objective_family"),
            "modelIdentity": record.get("model_identity"),
            "artifactIdentity": record.get("artifact_identity"),
            "trainingDatasetIdentity": record.get("training_dataset_identity"),
            "calibrationDatasetIdentity": record.get("calibration_dataset_identity"),
        },
        created_at=created_at,
        source_version=schema,
        diagnostics=diagnostics,
        unresolved_fields=unresolved,
        details={
            "outcome": "UNKNOWN",
            "diagnosticOnly": True,
            "mnelSchema": schema,
            "mnelProviderRecord": dict(record),
            "sourceStatus": record.get("status"),
            "abstained": record.get("abstained"),
            "outOfDistribution": record.get("out_of_distribution"),
            "confirmedUseful": record.get("confirmed_useful"),
        },
    )
