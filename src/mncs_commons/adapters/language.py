"""MNCS Language boundary: preserve stable semantic identities opaquely."""

from typing import Any, Mapping

from ..models import Diagnostic
from ._common import observation_from_external
from .contracts import AdapterResult


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
    return observation_from_external(
        producer_type="mncs-language",
        producer_id="mncs-language",
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
            "outcome": "UNKNOWN",
            "semanticGraphIdentity": graph_identity,
            "nodeIdentity": value.get("node_identity"),
            "machineIntent": value.get("machine_intent"),
            "loweringObligation": value.get("lowering_obligation"),
            "semanticPatch": value.get("semantic_patch"),
        },
    )
