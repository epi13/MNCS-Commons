"""MNCS Language boundary: preserve stable semantic identities opaquely."""

from typing import Any, Mapping

from ..models import Diagnostic, ResultStatus
from ._common import observation_from_external
from .contracts import AdapterResult


def _language_observation(
    value: Mapping[str, Any],
    *,
    source_identity: str | None,
    subject_type: str,
    subject_identity: str,
    summary: str,
    created_at: str | None,
    source_version: str | None,
    evidence_ids: list[str],
    scope_context: Mapping[str, Any],
    details: Mapping[str, Any],
    unresolved_fields: list[str] | None = None,
) -> AdapterResult:
    return observation_from_external(
        producer_type="mncs-language",
        producer_id="mncs-language",
        source_identity=source_identity,
        subject_type=subject_type,
        subject_identity=subject_identity,
        summary=summary,
        evidence_ids=evidence_ids,
        scope_context=scope_context,
        created_at=created_at,
        source_version=source_version,
        unresolved_fields=unresolved_fields,
        details={"outcome": ResultStatus.UNKNOWN.value, **dict(details)},
    )


def from_language_identity(
    value: Mapping[str, Any], *, subject_identity: str, created_at: str | None = None
) -> AdapterResult:
    graph_identity = value.get("semantic_graph_identity")
    if not isinstance(graph_identity, str) or not graph_identity:
        return AdapterResult(
            None,
            (
                Diagnostic(
                    "MISSING_SEMANTIC_GRAPH_IDENTITY",
                    "semantic_graph_identity",
                    "stable Language identity is required",
                ),
            ),
            str(value.get("schema_version")) if value.get("schema_version") else None,
            recognized=True,
            unresolved_fields=("semantic_graph_identity",),
        )
    return _language_observation(
        value,
        source_identity=graph_identity,
        subject_type="semantic-graph",
        subject_identity=subject_identity,
        summary="MNCS Language semantic identity referenced without reinterpreting the language",
        evidence_ids=[graph_identity],
        scope_context={
            "languageSchemaVersion": value.get("schema_version"),
            "sourceRepresentationIdentity": value.get("source_representation_identity"),
        },
        created_at=created_at,
        source_version=str(value.get("schema_version")) if value.get("schema_version") else None,
        details={
            "semanticGraphIdentity": graph_identity,
            "nodeIdentity": value.get("node_identity"),
            "machineIntent": value.get("machine_intent"),
            "loweringObligation": value.get("lowering_obligation"),
            "semanticPatch": value.get("semantic_patch"),
        },
    )


def from_executable_artifact(
    value: Mapping[str, Any], *, subject_identity: str, created_at: str | None = None
) -> AdapterResult:
    version = str(value.get("schema_version")) if value.get("schema_version") else None
    if version not in {"0.1", "0.2"}:
        return AdapterResult(
            None,
            (
                Diagnostic(
                    "UNSUPPORTED_SOURCE_VERSION",
                    "schema_version",
                    "MNCS Language executable artifact schema is not supported",
                ),
            ),
            version,
            recognized=False,
            unresolved_fields=("schema_version",),
        )
    identity = next(
        (
            value.get(key)
            for key in ("body_identity", "function_identity", "artifact_identity", "identity")
            if isinstance(value.get(key), str) and value.get(key)
        ),
        None,
    )
    source_identity = str(identity) if identity else None
    return _language_observation(
        value,
        source_identity=source_identity,
        subject_type="executable-body",
        subject_identity=subject_identity,
        summary="MNCS Language executable body preserved as an opaque semantic artifact",
        created_at=created_at,
        source_version=version,
        evidence_ids=[source_identity] if source_identity else [],
        scope_context={
            "module": value.get("module"),
            "functionCount": len(value.get("functions", []))
            if isinstance(value.get("functions"), list)
            else None,
        },
        details={
            "executableArtifact": dict(value),
            "artifactIntegrityStatus": ResultStatus.UNKNOWN.value,
        },
        unresolved_fields=[] if source_identity else ["source_identity"],
    )


def from_verifier_artifact(
    value: Mapping[str, Any], *, subject_identity: str, created_at: str | None = None
) -> AdapterResult:
    version = str(value.get("schema_version")) if value.get("schema_version") else None
    if version != "0.2":
        return AdapterResult(
            None,
            (
                Diagnostic(
                    "UNSUPPORTED_SOURCE_VERSION",
                    "schema_version",
                    "MNCS Language verifier artifact schema is not supported",
                ),
            ),
            version,
            recognized=False,
            unresolved_fields=("schema_version",),
        )
    identity = (
        value.get("result_identity") or value.get("request_identity") or value.get("identity")
    )
    source_identity = identity if isinstance(identity, str) and identity else None
    raw_status = str(value.get("status", "UNKNOWN")).upper()
    status = (
        raw_status
        if raw_status in {item.value for item in ResultStatus}
        else ResultStatus.UNKNOWN.value
    )
    return _language_observation(
        value,
        source_identity=source_identity,
        subject_type="verifier-artifact",
        subject_identity=subject_identity,
        summary=(
            "MNCS Language verifier artifact preserved without promoting "
            "local verification authority"
        ),
        created_at=created_at,
        source_version=version,
        evidence_ids=[source_identity] if source_identity else [],
        scope_context={
            "obligation": value.get("obligation"),
            "subject": value.get("subject"),
            "scope": value.get("scope"),
            "dependencies": value.get("dependencies"),
        },
        details={
            "outcome": status,
            "sourceStatus": status,
            "verifierArtifact": dict(value),
            "independentVerificationStatus": ResultStatus.UNKNOWN.value,
            "freshness": value.get("freshness"),
            "verifier": value.get("verifier"),
        },
        unresolved_fields=[] if source_identity else ["source_identity"],
    )
