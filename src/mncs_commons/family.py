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
REPLICATION_SCHEMA = "commons.mncs.dev/replication/v0alpha1"
DEVELOPMENT_RECORD_SCHEMA = "commons.mncs.dev/development-record/v0alpha1"
CHANGESET_SCHEMA = "commons.mncs.dev/changeset/v0alpha1"

CHANGESET_EDGE_TYPES = {
    "supports": "supports",
    "pressure": "pressure/supports-pressure",
    "contradicts": "contradicts",
    "promotes": "promotion/promotes",
}

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
            artifact_value["digest"] = _text(artifact.get("digest"), "artifact.digest", maximum=256)
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
        relationships.append({"type": "depends_on", "target": actor["reference"]["stableId"]})
    for relation, target in (("rerun_of", rerun_of), ("predecessor", predecessor)):
        if target is not None:
            relationships.append({"type": relation, "target": _text(target, relation, maximum=256)})
    relationship_pairs = sorted(
        {
            (
                item["type"],
                item["target"],
            )
            for item in relationships
        }
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
        "protectedProperties": _text_list(list(protected_properties), "protected_properties"),
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
            "sourceRecords": [item["reference"]["stableId"] for item in reference_entries],
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
            {"type": relation, "target": target} for relation, target in relationship_pairs
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


def make_replication_record(
    *,
    replication_id: str,
    created_at: str,
    target_record: str,
    outcome: str,
    independence: Mapping[str, Any],
    references: Iterable[Mapping[str, Any]],
    summary: str,
    producer_id: str = "mncs-control-mcp",
) -> dict[str, Any]:
    """Build one Replication record bound to producer-owned evidence references.

    The record describes what a replication attempt did and which exact
    producer records prove it.  It never reinterprets producer-native
    outcomes: ``outcome`` is a coordination-level tri-state, and acceptance
    remains a separate domain-scoped lifecycle decision.
    """

    replication_id = _text(replication_id, "replication_id", maximum=256)
    target = _text(target_record, "target_record", maximum=256)
    created_at = _timestamp(_text(created_at, "created_at", maximum=128))
    if outcome not in {"PASS", "FAIL", "UNKNOWN"}:
        raise FamilyRecordError("replication outcome must be PASS, FAIL, or UNKNOWN")
    if not isinstance(independence, Mapping):
        raise FamilyRecordError("independence must be an object")
    reference_entries, reference_relationships = _reference_entries(references)
    # ``attempts`` is the neutral link every replication carries.  Only PASS
    # additionally asserts ``replicates``; only FAIL asserts
    # ``failed_to_replicate``.  UNKNOWN asserts nothing beyond the attempt so
    # an undetermined outcome never collapses into demonstrated failure.
    relationships: list[dict[str, str]] = [
        {"type": "attempts", "target": target},
        *({"type": "replicates", "target": target} for _ in ("",) if outcome == "PASS"),
        *(
            {"type": "failed_to_replicate", "target": target}
            for _ in ("",)
            if outcome == "FAIL"
        ),
        *reference_relationships,
    ]
    relationships.sort(key=lambda item: (item["type"], item["target"]))
    return {
        "apiVersion": "commons.mncs.dev/v0alpha1",
        "kind": "Replication",
        "metadata": {
            "recordId": replication_id,
            "createdAt": created_at,
            "author": {"type": "producer", "id": producer_id},
            "labels": ["replication", "family-record-spine"],
        },
        "subject": {"type": "experiment", "identity": target},
        "scope": {
            "context": {"targetRecord": target},
            "limitations": [
                (
                    "coordination status only; producer references retain native semantics "
                    "and no assurance or conformance verdict is inferred"
                )
            ],
        },
        "statement": {"summary": _text(summary, "summary", maximum=20_000)},
        "evidence": [],
        "dependencies": [],
        "affectedContracts": [],
        "provenance": {
            "producer": {"type": "producer", "id": producer_id},
            "sourceRecords": [item["reference"]["stableId"] for item in reference_entries],
        },
        "confidence": {
            "level": "unreported",
            "rationale": "replication envelope does not infer confidence",
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
            "schema": REPLICATION_SCHEMA,
            "targetRecord": target,
            "outcome": outcome,
            "independence": dict(independence),
            "references": reference_entries,
            "authorityBoundary": (
                "describes the replication attempt and its exact evidence references; "
                "publication is not verification and no subsystem becomes an authority "
                "over language semantics, Fabric execution, Forge evaluation, or MNCS "
                "conformance"
            ),
        },
    }


def make_development_record_record(
    *,
    development_record_id: str,
    created_at: str,
    mncds_version: str,
    record_digest: str,
    profile: str,
    epoch_id: str,
    computed_status: str,
    summary: str,
    references: Iterable[Mapping[str, Any]],
    selected_candidate_id: str | None = None,
    supersedes_record_id: str | None = None,
    concept_experiment_ids: Iterable[str] = (),
    producer_id: str = "mncds",
) -> dict[str, Any]:
    """Project one validated MNCDS development record into the family graph.

    The projection carries the exact MNCDS record identity (id plus content
    digest), its tri-state computed status, and typed producer references.  It
    never reinterprets development-process semantics: Commons preserves the
    record, relates it to the experiments and candidates it cites, and leaves
    selection, release, and assurance authority with their owners.
    """

    development_record_id = _text(
        development_record_id, "development_record_id", maximum=256
    )
    created_at = _timestamp(_text(created_at, "created_at", maximum=128))
    mncds_version = _text(mncds_version, "mncds_version", maximum=64)
    if not record_digest.startswith("sha256:") or len(record_digest) != 71:
        raise FamilyRecordError("record_digest must be a sha256: identity")
    if any(character not in "0123456789abcdef" for character in record_digest[7:]):
        raise FamilyRecordError("record_digest must be lowercase hexadecimal")
    profile = _text(profile, "profile", maximum=64)
    epoch_id = _text(epoch_id, "epoch_id", maximum=256)
    if computed_status not in {"PASS", "FAIL", "UNKNOWN"}:
        raise FamilyRecordError("computed_status must be PASS, FAIL, or UNKNOWN")
    reference_entries, reference_relationships = _reference_entries(references)
    relationships: list[dict[str, str]] = list(reference_relationships)
    for experiment_id in concept_experiment_ids:
        target = _text(experiment_id, "concept_experiment_ids[]", maximum=256)
        relationships.append({"type": "derived_from", "target": target})
    if supersedes_record_id is not None:
        predecessor = _text(supersedes_record_id, "supersedes_record_id", maximum=256)
        relationships.append({"type": "supersedes", "target": predecessor})
    relationships.sort(key=lambda item: (item["type"], item["target"]))
    details: dict[str, Any] = {
        "schema": DEVELOPMENT_RECORD_SCHEMA,
        "mncdsVersion": mncds_version,
        "recordId": development_record_id,
        "recordDigest": record_digest,
        "profile": profile,
        "epochId": epoch_id,
        "computedStatus": computed_status,
        "references": reference_entries,
        "authorityBoundary": (
            "projection of a validated MNCDS development record; development-process "
            "semantics stay in MNCDS and no assurance or conformance verdict is inferred"
        ),
    }
    if selected_candidate_id is not None:
        details["selectedCandidateId"] = _text(
            selected_candidate_id, "selected_candidate_id", maximum=256
        )
    return {
        "apiVersion": "commons.mncs.dev/v0alpha1",
        "kind": "DevelopmentRecord",
        "metadata": {
            "recordId": f"development-record:{development_record_id}",
            "createdAt": created_at,
            "author": {"type": "producer", "id": producer_id},
            "labels": ["development-record", "family-record-spine"],
        },
        "subject": {"type": "experiment", "identity": development_record_id},
        "scope": {
            "context": {
                "mncdsVersion": mncds_version,
                "profile": profile,
                "epochId": epoch_id,
                "computedStatus": computed_status,
            },
            "limitations": [
                (
                    "coordination status only; the referenced MNCDS record retains "
                    "native development-process semantics"
                )
            ],
        },
        "statement": {"summary": _text(summary, "summary", maximum=20_000)},
        "evidence": [],
        "dependencies": [],
        "affectedContracts": [],
        "provenance": {
            "producer": {"type": "producer", "id": producer_id},
            "sourceRecords": [item["reference"]["stableId"] for item in reference_entries],
        },
        "confidence": {
            "level": "unreported",
            "rationale": "the projected MNCDS record carries its own computed status",
        },
        "security": {
            "sensitivity": "public",
            "executableAttachments": False,
            "instructionsAreUntrusted": True,
            "requiredExternalAuthority": False,
        },
        "lifecycle": {"initialState": "proposed", "reviewWhen": []},
        "relationships": relationships,
        "details": details,
    }


def make_changeset_record(
    *,
    changeset_id: str,
    created_at: str,
    base_revisions: Iterable[Mapping[str, str]],
    supports: Iterable[Mapping[str, Any]] = (),
    pressure: Iterable[Mapping[str, Any]] = (),
    contradicts: Iterable[Mapping[str, Any]] = (),
    promotes: Iterable[Mapping[str, Any]] = (),
    summary: str,
    producer_id: str = "MNCS-Commons",
) -> dict[str, Any]:
    """Coordinate one cross-repository ChangeSet through the family graph.

    The record carries exact base revisions plus digest-bound references to
    the claims produced elsewhere: supporting development records, lineage,
    and per-repository evidence (``supports``); open development-pressure
    obligations (``pressure``); blocking obligations or negative evidence
    (``contradicts``); and at most one MNCS promotion-boundary evaluation
    result (``promotes``).  Commons owns these relationships, never the
    promotion semantics: a ``promotes`` edge only ever points at an
    owner-native MNCS promotion result, and system-level PASS is never
    inferred from component records.
    """
    changeset_id = _text(changeset_id, "changeset_id", maximum=256)
    created_at = _timestamp(_text(created_at, "created_at", maximum=128))
    pinned: list[dict[str, str]] = []
    for index, revision in enumerate(base_revisions):
        field = f"base_revisions[{index}]"
        if not isinstance(revision, Mapping):
            raise FamilyRecordError(f"{field} must be an object")
        repository = _text(revision.get("repository"), f"{field}.repository", maximum=256)
        commit = _text(revision.get("commit"), f"{field}.commit", maximum=64)
        if len(commit) != 40 or any(
            character not in "0123456789abcdef" for character in commit
        ):
            raise FamilyRecordError(f"{field}.commit must be an exact 40-hex revision")
        pinned.append({"repository": repository, "commit": commit})
    if not pinned:
        raise FamilyRecordError("base_revisions must name at least one revision")

    grouped: dict[str, list[Mapping[str, Any]]] = {
        "supports": list(supports),
        "pressure": list(pressure),
        "contradicts": list(contradicts),
        "promotes": list(promotes),
    }
    if len(grouped["promotes"]) > 1:
        raise FamilyRecordError("a ChangeSet carries at most one promotion result")
    entries: list[dict[str, Any]] = []
    relationships: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for group, values in grouped.items():
        for value in values:
            if not isinstance(value, Mapping):
                raise FamilyRecordError(f"{group} references must be objects")
            reference = normalize_producer_reference(value)
            key = (group, reference["stableId"])
            if key in seen:
                continue
            seen.add(key)
            entries.append({"group": group, "relation": group, "reference": reference})
            relationships.append(
                {"type": CHANGESET_EDGE_TYPES[group], "target": reference["stableId"]}
            )
    entries.sort(key=lambda item: (item["group"], item["reference"]["stableId"]))
    relationships.sort(key=lambda item: (item["type"], item["target"]))

    details: dict[str, Any] = {
        "schema": CHANGESET_SCHEMA,
        "changesetId": changeset_id,
        "baseRevisions": pinned,
        "references": entries,
        "authorityBoundary": (
            "coordination relationships only; development-process semantics stay "
            "in MNCDS, promotion semantics stay in MNCS, and no conformance "
            "verdict is inferred from component records"
        ),
    }
    return {
        "apiVersion": "commons.mncs.dev/v0alpha1",
        "kind": "ChangeSet",
        "metadata": {
            "recordId": f"changeset:{changeset_id}",
            "createdAt": created_at,
            "author": {"type": "producer", "id": producer_id},
            "labels": ["changeset", "family-record-spine"],
        },
        "subject": {"type": "changeset", "identity": changeset_id},
        "scope": {
            "context": {
                "changesetId": changeset_id,
                "baseRevisionCount": len(pinned),
            },
            "limitations": [
                "coordination status only; carried claims retain native owner semantics"
            ],
        },
        "statement": {"summary": _text(summary, "summary", maximum=20_000)},
        "evidence": [],
        "dependencies": [],
        "affectedContracts": [],
        "provenance": {
            "producer": {"type": "producer", "id": producer_id},
            "sourceRecords": [item["reference"]["stableId"] for item in entries],
        },
        "confidence": {
            "level": "unreported",
            "rationale": "coordination only; carried claims carry their own verdicts",
        },
        "security": {
            "sensitivity": "public",
            "executableAttachments": False,
            "instructionsAreUntrusted": True,
            "requiredExternalAuthority": False,
        },
        "lifecycle": {"initialState": "proposed", "reviewWhen": []},
        "relationships": relationships,
        "details": details,
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
