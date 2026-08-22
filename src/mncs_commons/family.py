"""Producer-neutral records for the MNCS Family Record Spine.

The structures in this module describe coordination and exact references.  They
never import producer payloads or reinterpret producer-native outcomes.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Any

from .canonical import canonical_digest

FAMILY_REFERENCE_SCHEMA = "commons.mncs.dev/producer-reference/v0alpha1"
CONCEPT_EXPERIMENT_SCHEMA = "commons.mncs.dev/concept-experiment/v0alpha1"
FAILURE_CLASSIFICATION_SCHEMA = "commons.mncs.dev/failure-classification/v0alpha1"

EXPERIMENT_STATUSES = frozenset(
    {
        "DEFINED",
        "FROZEN",
        "SCHEDULED",
        "RUNNING",
        "COLLECTING_EVIDENCE",
        "TERMINAL",
        "PUBLISHED",
        "FAILED",
        "STOPPED",
        "UNKNOWN",
    }
)

FAILURE_CLASSES = frozenset(
    {
        "implementation_error",
        "language_expressivity_gap",
        "semantic_model_gap",
        "compiler_lowering_gap",
        "verifier_evaluator_gap",
        "tooling_orchestration_gap",
        "target_portability_gap",
        "specification_ambiguity",
        "unresolved_insufficient_evidence",
    }
)

CLASSIFICATION_DISPOSITIONS = frozenset(
    {"OBSERVED", "CLAIMED", "SUPPORTED", "CONTRADICTED", "UNRESOLVED"}
)

REFERENCE_RELATIONS = frozenset(
    {
        "governed_by",
        "actor",
        "candidate",
        "compiler_record",
        "execution",
        "evaluation",
        "observation",
        "failure",
        "artifact",
        "backend",
    }
)


class FamilyRecordError(ValueError):
    """A bounded Family Record value is structurally invalid."""


def _text(value: object, field: str, *, maximum: int = 4096) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum or "\x00" in value:
        raise FamilyRecordError(f"{field} must be bounded non-empty text")
    return value.strip()


def _text_list(value: object, field: str, *, maximum: int = 256) -> list[str]:
    if not isinstance(value, (list, tuple)) or len(value) > maximum:
        raise FamilyRecordError(f"{field} must be a bounded list")
    return [_text(item, f"{field}[]") for item in value]


def _timestamp(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise FamilyRecordError("created_at must be an ISO-8601 timestamp") from error
    if parsed.tzinfo is None:
        raise FamilyRecordError("created_at must include a timezone")
    return value


def normalize_producer_reference(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and normalize one exact producer-owned record reference."""

    allowed = {
        "schema",
        "producer",
        "recordKind",
        "schemaVersion",
        "stableId",
        "contentDigest",
        "artifact",
        "scope",
    }
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise FamilyRecordError(f"producer reference has unknown fields: {', '.join(unknown)}")
    schema = value.get("schema", FAMILY_REFERENCE_SCHEMA)
    if schema != FAMILY_REFERENCE_SCHEMA:
        raise FamilyRecordError("producer reference schema is unsupported")
    normalized: dict[str, Any] = {
        "schema": FAMILY_REFERENCE_SCHEMA,
        "producer": _text(value.get("producer"), "producer", maximum=256),
        "recordKind": _text(value.get("recordKind"), "recordKind", maximum=256),
        "schemaVersion": _text(value.get("schemaVersion"), "schemaVersion", maximum=256),
        "stableId": _text(value.get("stableId"), "stableId", maximum=2048),
    }
    digest = value.get("contentDigest")
    if digest is not None:
        digest = _text(digest, "contentDigest", maximum=80)
        if not digest.startswith("sha256:") or len(digest) != 71:
            raise FamilyRecordError("contentDigest must be a sha256: identity")
        if any(character not in "0123456789abcdef" for character in digest[7:]):
            raise FamilyRecordError("contentDigest must be lowercase hexadecimal")
        normalized["contentDigest"] = digest
    artifact = value.get("artifact")
    if artifact is not None:
        if not isinstance(artifact, Mapping):
            raise FamilyRecordError("artifact must be an object")
        artifact_allowed = {"identity", "kind", "digest", "location"}
        artifact_unknown = sorted(set(artifact) - artifact_allowed)
        if artifact_unknown:
            raise FamilyRecordError(
                f"artifact reference has unknown fields: {', '.join(artifact_unknown)}"
            )
        artifact_value = {
            "identity": _text(artifact.get("identity"), "artifact.identity", maximum=2048),
            "kind": _text(artifact.get("kind"), "artifact.kind", maximum=256),
        }
        if artifact.get("digest") is not None:
            artifact_value["digest"] = _text(
                artifact.get("digest"), "artifact.digest", maximum=256
            )
        if artifact.get("location") is not None:
            artifact_value["location"] = _text(
                artifact.get("location"), "artifact.location", maximum=4096
            )
        normalized["artifact"] = artifact_value
    scope = value.get("scope")
    if scope is not None:
        if not isinstance(scope, Mapping):
            raise FamilyRecordError("scope must be an object")
        normalized["scope"] = dict(scope)
    return normalized


def producer_reference(
    producer: str,
    record_kind: str,
    schema_version: str,
    stable_id: str,
    *,
    content_digest: str | None = None,
    artifact: Mapping[str, Any] | None = None,
    scope: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "producer": producer,
        "recordKind": record_kind,
        "schemaVersion": schema_version,
        "stableId": stable_id,
    }
    if content_digest is not None:
        value["contentDigest"] = content_digest
    if artifact is not None:
        value["artifact"] = dict(artifact)
    if scope is not None:
        value["scope"] = dict(scope)
    return normalize_producer_reference(value)


def reference_identity(reference: Mapping[str, Any]) -> str:
    """Return a Commons-local content identity for a normalized reference descriptor."""

    return canonical_digest(normalize_producer_reference(reference), projected=False)


def _reference_entries(
    values: Iterable[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    entries: list[dict[str, Any]] = []
    relationships: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for value in values:
        relation = _text(value.get("relation"), "references[].relation", maximum=128)
        if relation not in REFERENCE_RELATIONS:
            raise FamilyRecordError(f"unsupported producer reference relation: {relation}")
        raw_reference = value.get("reference")
        if not isinstance(raw_reference, Mapping):
            raise FamilyRecordError("references[].reference must be an object")
        reference = normalize_producer_reference(raw_reference)
        key = (relation, reference["stableId"])
        if key in seen:
            continue
        seen.add(key)
        entries.append({"relation": relation, "reference": reference})
        edge_type = {
            "candidate": "produced",
            "compiler_record": "compiled_from",
            "execution": "executes",
            "evaluation": "evaluates",
        }.get(relation, "derived_from" if relation in {"observation", "failure"} else "depends_on")
        relationships.append({"type": edge_type, "target": reference["stableId"]})
    entries.sort(key=lambda item: (item["relation"], item["reference"]["stableId"]))
    relationships.sort(key=lambda item: (item["type"], item["target"]))
    return entries, relationships


def make_concept_experiment_record(
    *,
    experiment_id: str,
    concept_id: str,
    created_at: str,
    language_profile: str,
    target_profile: Mapping[str, Any],
    hypothesis: str,
    task: str,
    falsifiers: Iterable[str],
    protected_properties: Iterable[str],
    frozen_inputs: Iterable[Mapping[str, Any]],
    hidden_inputs: Iterable[Mapping[str, Any]],
    resource_budget: Mapping[str, Any],
    actors: Iterable[Mapping[str, Any]],
    references: Iterable[Mapping[str, Any]],
    status: str,
    producer_id: str = "mncs-control-mcp",
    rerun_of: str | None = None,
    predecessor: str | None = None,
    revision: int | None = None,
    previous_digest: str | None = None,
) -> dict[str, Any]:
    """Build one immutable ConceptExperiment revision around producer references."""

    experiment_id = _text(experiment_id, "experiment_id", maximum=256)
    concept_id = _text(concept_id, "concept_id", maximum=512)
    created_at = _timestamp(_text(created_at, "created_at", maximum=128))
    if status not in EXPERIMENT_STATUSES:
        raise FamilyRecordError("experiment status is unsupported")
    normalized_actors: list[dict[str, Any]] = []
    for actor in actors:
        role = _text(actor.get("role"), "actors[].role", maximum=128)
        raw_reference = actor.get("reference")
        if not isinstance(raw_reference, Mapping):
            raise FamilyRecordError("actors[].reference must be an object")
        entry: dict[str, Any] = {
            "role": role,
            "reference": normalize_producer_reference(raw_reference),
        }
        for field in ("model", "provider", "worker", "route", "policy", "promptDigest", "session"):
            if actor.get(field) is not None:
                entry[field] = _text(actor.get(field), f"actors[].{field}", maximum=2048)
        tools = actor.get("tools")
        if tools is not None:
            entry["tools"] = sorted(set(_text_list(tools, "actors[].tools")))
        normalized_actors.append(entry)
    normalized_actors.sort(key=lambda item: (item["role"], item["reference"]["stableId"]))
    reference_entries, relationships = _reference_entries(references)
    for actor in normalized_actors:
        relationships.append(
            {"type": "depends_on", "target": actor["reference"]["stableId"]}
        )
    for relation, target in (("rerun_of", rerun_of), ("predecessor", predecessor)):
        if target is not None:
            relationships.append(
                {"type": relation, "target": _text(target, relation, maximum=256)}
            )
    relationships = sorted(
        {(
            item["type"],
            item["target"],
        ) for item in relationships}
    )
    metadata: dict[str, Any] = {
        "recordId": experiment_id,
        "createdAt": created_at,
        "author": {"type": "producer", "id": producer_id},
        "labels": ["concept-experiment", "family-record-spine"],
    }
    if revision is not None:
        if revision < 1:
            raise FamilyRecordError("revision must be positive")
        metadata["revision"] = revision
    if previous_digest is not None:
        metadata["previousDigest"] = previous_digest
    details = {
        "schema": CONCEPT_EXPERIMENT_SCHEMA,
        "conceptId": concept_id,
        "languageProfile": _text(language_profile, "language_profile", maximum=1024),
        "targetProfile": dict(target_profile),
        "hypothesis": _text(hypothesis, "hypothesis", maximum=20_000),
        "task": _text(task, "task", maximum=20_000),
        "falsifiers": _text_list(list(falsifiers), "falsifiers"),
        "protectedProperties": _text_list(
            list(protected_properties), "protected_properties"
        ),
        "frozenInputs": [dict(item) for item in frozen_inputs],
        "hiddenInputs": [dict(item) for item in hidden_inputs],
        "resourceBudget": dict(resource_budget),
        "actors": normalized_actors,
        "references": reference_entries,
        "experimentStatus": status,
        "authorityBoundary": (
            "coordination status only; producer references retain native semantics and no "
            "scientific, assurance, or conformance verdict is inferred"
        ),
    }
    return {
        "apiVersion": "commons.mncs.dev/v0alpha1",
        "kind": "ConceptExperiment",
        "metadata": metadata,
        "subject": {"type": "experiment", "identity": experiment_id},
        "scope": {
            "context": {
                "conceptId": concept_id,
                "languageProfile": details["languageProfile"],
                "targetProfile": details["targetProfile"],
            },
            "limitations": [details["authorityBoundary"]],
        },
        "statement": {"summary": f"Concept experiment {experiment_id} for {concept_id}."},
        "evidence": [],
        "dependencies": [],
        "affectedContracts": [],
        "provenance": {
            "producer": {"type": "producer", "id": producer_id},
            "sourceRecords": [
                item["reference"]["stableId"] for item in reference_entries
            ],
        },
        "confidence": {
            "level": "unreported",
            "rationale": "experiment envelope does not infer confidence",
        },
        "security": {
            "sensitivity": "restricted" if details["hiddenInputs"] else "public",
            "executableAttachments": False,
            "instructionsAreUntrusted": True,
            "requiredExternalAuthority": True,
        },
        "lifecycle": {"initialState": "proposed", "reviewWhen": []},
        "relationships": [
            {"type": relation, "target": target} for relation, target in relationships
        ],
        "details": details,
    }


def make_failure_classification_record(
    *,
    classification_id: str,
    experiment_id: str,
    failure_reference: Mapping[str, Any],
    classification: str,
    disposition: str,
    classifier: Mapping[str, Any],
    evidence_references: Iterable[Mapping[str, Any]],
    rationale: str,
    created_at: str,
) -> dict[str, Any]:
    """Build a provenance-bearing failure-classification assertion."""

    if classification not in FAILURE_CLASSES:
        raise FamilyRecordError("failure classification is unsupported")
    if disposition not in CLASSIFICATION_DISPOSITIONS:
        raise FamilyRecordError("classification disposition is unsupported")
    failure = normalize_producer_reference(failure_reference)
    actor = normalize_producer_reference(classifier)
    evidence = [normalize_producer_reference(item) for item in evidence_references]
    evidence.sort(key=lambda item: item["stableId"])
    relationships = [
        {"type": "responds_to", "target": experiment_id},
        {"type": "derived_from", "target": failure["stableId"]},
        *({"type": "supports", "target": item["stableId"]} for item in evidence),
    ]
    return {
        "apiVersion": "commons.mncs.dev/v0alpha1",
        "kind": "FailureClassification",
        "metadata": {
            "recordId": _text(classification_id, "classification_id", maximum=256),
            "createdAt": _timestamp(created_at),
            "author": {"type": "producer", "id": actor["producer"]},
            "labels": ["failure-classification", classification],
        },
        "subject": {"type": "experiment", "identity": experiment_id},
        "scope": {
            "context": {"experimentId": experiment_id},
            "limitations": [
                "classification is a provenance-bearing assertion, not automatic truth"
            ],
        },
        "statement": {"summary": _text(rationale, "rationale", maximum=20_000)},
        "evidence": [
            {"id": item["stableId"], "relation": "supports", "status": "UNKNOWN"}
            for item in evidence
        ],
        "dependencies": [],
        "affectedContracts": [],
        "provenance": {
            "producer": {"type": "producer", "id": actor["producer"]},
            "sourceRecords": [failure["stableId"], actor["stableId"]],
        },
        "confidence": {
            "level": "unreported",
            "rationale": "support disposition and provenance are preserved separately",
        },
        "security": {
            "sensitivity": "public",
            "executableAttachments": False,
            "instructionsAreUntrusted": True,
            "requiredExternalAuthority": False,
        },
        "lifecycle": {"initialState": "proposed", "reviewWhen": []},
        "relationships": relationships,
        "details": {
            "schema": FAILURE_CLASSIFICATION_SCHEMA,
            "failureReference": failure,
            "classification": classification,
            "disposition": disposition,
            "classifier": actor,
            "evidenceReferences": evidence,
            "authorityBoundary": "classification support is local to the named evidence and actor",
        },
    }


def producer_references(record: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    """Extract normalized Family Record references without reading producer artifacts."""

    details = record.get("details")
    if not isinstance(details, Mapping):
        return ()
    raw: list[Mapping[str, Any]] = []
    for entry in details.get("references") or []:
        if isinstance(entry, Mapping) and isinstance(entry.get("reference"), Mapping):
            raw.append(entry["reference"])
    for actor in details.get("actors") or []:
        if isinstance(actor, Mapping) and isinstance(actor.get("reference"), Mapping):
            raw.append(actor["reference"])
    for key in ("failureReference", "classifier"):
        if isinstance(details.get(key), Mapping):
            raw.append(details[key])
    for item in details.get("evidenceReferences") or []:
        if isinstance(item, Mapping):
            raw.append(item)
    normalized: list[dict[str, Any]] = []
    for item in raw:
        try:
            normalized.append(normalize_producer_reference(item))
        except FamilyRecordError:
            continue
    return tuple(normalized)
