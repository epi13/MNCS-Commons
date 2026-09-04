"""Knowledge Capsules: small exchange envelopes over canonical records.

A capsule is a composition around an existing canonical record, not a new
record type.  It gathers everything a receiving machine needs for the nine
deterministic triage questions into one bounded mapping:

.. code-block:: text

    Do I understand this?      (kind + relationship vocabulary known)
    Do I already have it?      (identity in the local frontier)
    Is it relevant?            (matches the local interest projection)
    Is its structure valid?    (required capsule fields present)
    What provenance is asserted? (producer + source records, verbatim)
    Do I possess its evidence? (local CAS vs referenced evidence ids)
    Where may evidence exist?  (availability knowledge per evidence id)
    Can I reproduce it?        (explicit reproduction reference present?)
    Should I retain it?        (relevant + new + within budget -> candidate)

No LLM is required for any of these mechanics.  Capsules are inert data:
they never carry commands, URLs to fetch automatically, or authority.
"""

from __future__ import annotations

from typing import Any, Mapping

from .availability import EvidenceAvailability, EvidenceReference
from .errors import MeshError
from .interest import InterestFilter, matches

CAPSULE_VERSION = "commons.mncs.dev/capsule/v0alpha1"

MAX_CAPSULE_BYTES = 256 * 1024
MAX_LIST_ENTRIES = 256

_REPRODUCTION_KEYS = ("reproduction", "reproductionProcedure", "reproductionReference")


def _bounded_list(value: Any, name: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise MeshError("INVALID_CAPSULE", f"{name} must be a list")
    if len(value) > MAX_LIST_ENTRIES:
        raise MeshError("INVALID_CAPSULE", f"{name} exceeds {MAX_LIST_ENTRIES} entries")
    items = []
    for item in value:
        if not isinstance(item, str) or not item or len(item) > 1024:
            raise MeshError("INVALID_CAPSULE", f"{name} entries must be bounded strings")
        items.append(item)
    return items


def compose_capsule(
    record: Mapping[str, Any],
    *,
    lifecycle: Mapping[str, str] | None = None,
    availability: Mapping[str, EvidenceReference | Mapping[str, Any]] | None = None,
    producer: Mapping[str, Any] | None = None,
    protocol_version: str | None = None,
) -> dict[str, Any]:
    """Project a canonical record plus local knowledge into a capsule."""

    if not isinstance(record, Mapping):
        raise MeshError("INVALID_CAPSULE", "capsule requires a record mapping")
    identity = record.get("contentDigest")
    kind = record.get("kind")
    if not isinstance(identity, str) or not identity:
        raise MeshError("INVALID_CAPSULE", "record has no contentDigest")
    if not isinstance(kind, str) or not kind:
        raise MeshError("INVALID_CAPSULE", "record has no kind")
    subject = record.get("subject")
    scope = record.get("scope")
    if not isinstance(subject, Mapping) or not isinstance(scope, Mapping):
        raise MeshError("INVALID_CAPSULE", "record needs subject and scope objects")

    evidence_ids: list[str] = []
    evidence = record.get("evidence")
    if isinstance(evidence, list):
        for entry in evidence:
            if isinstance(entry, Mapping) and isinstance(entry.get("id"), str):
                evidence_ids.append(entry["id"])
    evidence_ids = sorted(set(evidence_ids))[:MAX_LIST_ENTRIES]

    relationships: list[dict[str, str]] = []
    raw_relationships = record.get("relationships")
    if isinstance(raw_relationships, list):
        for item in raw_relationships[:MAX_LIST_ENTRIES]:
            if (
                isinstance(item, Mapping)
                and isinstance(item.get("type"), str)
                and isinstance(item.get("target"), str)
            ):
                relationships.append({"type": item["type"], "target": item["target"]})

    provenance = record.get("provenance")
    provenance_root: list[str] = []
    if isinstance(provenance, Mapping):
        sources = provenance.get("sourceRecords")
        if isinstance(sources, list):
            provenance_root = sorted({str(item) for item in sources if item})[:MAX_LIST_ENTRIES]

    record_producer: Mapping[str, Any] | None = None
    if isinstance(provenance, Mapping) and isinstance(provenance.get("producer"), Mapping):
        record_producer = provenance["producer"]
    if producer is not None:
        if not isinstance(producer, Mapping):
            raise MeshError("INVALID_CAPSULE", "producer must be an object")
        record_producer = dict(producer)

    availability_view: dict[str, dict[str, object]] = {}
    for evidence_id in evidence_ids:
        reference = (availability or {}).get(evidence_id)
        if isinstance(reference, EvidenceReference):
            availability_view[evidence_id] = dict(reference.as_dict())
        elif isinstance(reference, Mapping):
            availability_view[evidence_id] = {
                "digest": evidence_id,
                "availability": str(
                    reference.get("availability", EvidenceAvailability.UNAVAILABLE.value)
                ),
            }
        else:
            availability_view[evidence_id] = {
                "digest": evidence_id,
                "availability": EvidenceAvailability.UNAVAILABLE.value,
            }

    reproduction_reference: Any = None
    details = record.get("details")
    if isinstance(details, Mapping):
        for key in _REPRODUCTION_KEYS:
            candidate = details.get(key)
            if isinstance(candidate, str) and candidate:
                reproduction_reference = candidate[:1024]
                break
            if isinstance(candidate, Mapping):
                reproduction_reference = {
                    str(key): str(value)[:256] for key, value in list(candidate.items())[:16]
                }
                break
    if reproduction_reference is None:
        # Top-level reproduction procedures are inert untrusted data: the
        # capsule records only that a recipe exists and what it expects,
        # never the procedure commands themselves.
        reproduction = record.get("reproduction")
        if isinstance(reproduction, Mapping):
            expected = reproduction.get("expected")
            prerequisites = reproduction.get("prerequisites")
            reproduction_reference = {
                "hasProcedure": bool(reproduction.get("procedure")),
                "expected": [str(item)[:256] for item in expected[:8]]
                if isinstance(expected, list)
                else [],
                "prerequisites": len(prerequisites) if isinstance(prerequisites, list) else 0,
            }

    confidence = record.get("confidence")
    security = record.get("security")
    capsule = {
        "capsuleVersion": CAPSULE_VERSION,
        "identity": identity,
        "recordKind": kind,
        "subject": {"type": subject.get("type"), "identity": subject.get("identity")},
        "scope": {
            "context": dict(scope.get("context", {}))
            if isinstance(scope.get("context"), Mapping)
            else {},
            "limitations": list(scope.get("limitations", []))
            if isinstance(scope.get("limitations"), list)
            else [],
        },
        "provenanceRoot": provenance_root,
        "evidenceRoot": evidence_ids,
        "relationships": relationships,
        "lifecycle": dict(lifecycle or {}),
        "confidence": dict(confidence) if isinstance(confidence, Mapping) else {},
        "availability": availability_view,
        "producer": dict(record_producer) if record_producer is not None else {},
        "protocolVersion": protocol_version or str(record.get("apiVersion", "unknown")),
        "security": {
            "sensitivity": security.get("sensitivity") if isinstance(security, Mapping) else None,
            "instructionsAreUntrusted": security.get("instructionsAreUntrusted", True)
            if isinstance(security, Mapping)
            else True,
        },
        "reproductionReference": reproduction_reference,
    }
    return capsule


def assess_capsule(
    capsule: Mapping[str, Any],
    *,
    known_digests: set[str] | frozenset[str],
    retained_evidence: set[str] | frozenset[str],
    supported_kinds: set[str] | frozenset[str],
    supported_relationships: set[str] | frozenset[str],
    interest: InterestFilter | None = None,
) -> dict[str, object]:
    """Answer the nine deterministic triage questions for one capsule."""

    if not isinstance(capsule, Mapping):
        raise MeshError("INVALID_CAPSULE", "capsule must be an object")
    identity = capsule.get("identity")
    kind = capsule.get("recordKind")
    if not isinstance(identity, str) or not kind:
        raise MeshError("INVALID_CAPSULE", "capsule needs identity and recordKind")

    unknown_relationships = sorted(
        {
            str(item.get("type"))
            for item in capsule.get("relationships", [])
            if isinstance(item, Mapping) and str(item.get("type")) not in supported_relationships
        }
    )
    understood = kind in supported_kinds and not unknown_relationships
    already_have = identity in known_digests

    pseudo_record = {
        "kind": kind,
        "contentDigest": identity,
        "scope": capsule.get("scope", {}),
        "subject": capsule.get("subject", {}),
        "affectedContracts": [],
        "provenance": {"producer": capsule.get("producer", {})},
        "evidence": [],
        "relationships": capsule.get("relationships", []),
        "metadata": {"labels": []},
    }
    relevant = True if interest is None else matches(pseudo_record, interest)

    structure_valid = all(
        key in capsule
        for key in (
            "identity",
            "recordKind",
            "subject",
            "scope",
            "provenanceRoot",
            "evidenceRoot",
            "relationships",
            "lifecycle",
            "availability",
            "producer",
            "protocolVersion",
            "security",
        )
    )

    availability = capsule.get("availability")
    if not isinstance(availability, Mapping):
        availability = {}
    evidence_root = capsule.get("evidenceRoot")
    evidence_ids = [str(item) for item in evidence_root] if isinstance(evidence_root, list) else []
    possessed = sorted({item for item in evidence_ids if item in retained_evidence})
    missing = sorted({item for item in evidence_ids if item not in retained_evidence})
    locations = {}
    for evidence_id in evidence_ids:
        entry = availability.get(evidence_id)
        if isinstance(entry, Mapping) and entry.get("availability"):
            locations[evidence_id] = str(entry["availability"])
        elif evidence_id in retained_evidence:
            locations[evidence_id] = EvidenceAvailability.LOCAL.value
        else:
            locations[evidence_id] = EvidenceAvailability.UNAVAILABLE.value

    reproduction = capsule.get("reproductionReference")
    return {
        "capsuleVersion": CAPSULE_VERSION,
        "identity": identity,
        "understood": understood,
        "unknownRelationships": unknown_relationships,
        "alreadyHave": already_have,
        "relevant": relevant,
        "structureValid": structure_valid,
        "provenanceAsserted": dict(capsule.get("producer", {}))
        if isinstance(capsule.get("producer"), Mapping)
        else {},
        "evidencePossessed": possessed,
        "evidenceMissing": missing,
        "evidenceLocations": locations,
        "reproductionReference": reproduction,
        "reproducible": reproduction is not None,
        "retainCandidate": bool(relevant and not already_have and structure_valid),
        "authority": "triage-only; possession and relevance grant no correctness",
    }
