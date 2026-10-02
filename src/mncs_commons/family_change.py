"""Family shared-workspace vocabulary: working changes, presence, generations.

This module owns the STRUCTURAL shape of family collaboration records.
All semantic decisions (lifecycle legality, consumer classification,
repair gating, adoption, transform admission, revisit) live ONLY in the
native law ``mncs.commons.family.change.v1``; nothing here reimplements
them. Without a toolchain, hosts validate structure and fail closed on
policy (unknown), never guess.

A family change is a producer WORKING change (subjects, operations,
consumer impact). It is distinct from the Record Spine ChangeSet
(``commons.mncs.dev/changeset/v0alpha1``), which coordinates EVIDENCE
for promotion; a family change may LINK to spine ChangeSets via
``evidence_refs.coordination_changesets``.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

FAMILY_CHANGE_SCHEMA = "mncs.family-change/1"
FAMILY_CONTRIBUTOR_SCHEMA = "mncs.family-contributor/1"
FAMILY_GENERATION_SCHEMA = "mncs.family-generation/1"
FAMILY_RECONCILIATION_SCHEMA = "mncs.family-reconciliation/1"
FAMILY_EVENT_SCHEMA = "mncs.family-event/1"

#: Mirror of native ChangeState codes (mncs.commons.family.change.v1).
CHANGE_STATES = {
    "draft": 0, "observed": 1, "validated": 2, "established": 3,
    "published": 4, "superseded": 5, "abandoned": 6, "conflicted": 7,
    "invalid": 8,
}

#: Mirror of native ConsumerClass codes.
CONSUMER_CLASSES = {
    "current": 0, "reconcilable": 1, "semantic_required": 2,
    "occupied": 3, "pending_verification": 4, "blocked": 5,
    "unknown": 6, "incompatible": 7,
}

#: Mirror of native Gate codes (aligned with automation).
GATES = {"proceed": 0, "defer": 1, "escalate": 2}

#: Mirror of native Adopt codes (aligned with automation).
ADOPTS = {"adopted": 0, "stale_regeneration": 1, "regression_refused": 2}

#: Mirror of native RepairState codes.
REPAIR_STATES = {
    "no_repair": 0, "applied_unknown": 1, "applied_fail": 2,
    "applied_pass": 3,
}

#: Mirror of native Verdict codes.
VERDICTS = {"failed": 0, "passed": 1, "unknown": 2}

#: Mirror of native TransformOp codes.
TRANSFORM_OPS = {"set_json_field": 0, "replace_span": 1, "run_capability": 2}

#: Mirror of native DeferReason codes.
DEFER_REASONS = {
    "replan": 0, "claim_required": 1, "occupied": 2,
    "provider_unavailable": 3, "awaiting_verdict": 4,
}

MAX_SUBJECTS = 32
MAX_SUBJECT_PATHS = 16
MAX_CONTRACTS = 16
MAX_OPERATIONS = 16
MAX_INTENT_CHARS = 280
MAX_IDENTITY_STRING = 256
MAX_PATH_STRING = 512


class FamilyChangeError(ValueError):
    """A family collaboration record is structurally invalid."""


def _text(value: Any, field: str, maximum: int = MAX_IDENTITY_STRING) -> str:
    if not isinstance(value, str) or not value:
        raise FamilyChangeError(f"{field} must be a non-empty string")
    if len(value) > maximum:
        raise FamilyChangeError(f"{field} exceeds {maximum} characters")
    return value


def _hex40(value: Any, field: str) -> str:
    text = _text(value, field, maximum=64)
    if len(text) != 40 or any(c not in "0123456789abcdef" for c in text):
        raise FamilyChangeError(f"{field} must be an exact 40-hex revision")
    return text


def _bounded_list(value: Any, field: str, maximum: int) -> list:
    if not isinstance(value, list):
        raise FamilyChangeError(f"{field} must be a list")
    if len(value) > maximum:
        raise FamilyChangeError(f"{field} exceeds {maximum} entries")
    return value


def _non_negative_int(value: Any, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise FamilyChangeError(f"{field} must be a non-negative integer")
    return value


def change_identity(core: Mapping[str, Any]) -> str:
    """Stable identity over the canonical change core (state excluded)."""
    canonical = json.dumps(core, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=True)
    return "fc:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def change_core(record: Mapping[str, Any]) -> dict[str, Any]:
    """Identity-bound core: everything except state and row metadata."""
    return {
        "producer": record["producer"],
        "base": record["base"],
        "subjects": record["subjects"],
        "contracts_changed": record["contracts_changed"],
        "operations": record["operations"],
        "evidence_refs": record["evidence_refs"],
        "intent": record["intent"],
        "supersedes": record.get("supersedes", []),
    }


def validate_operation(operation: Any, field: str = "operations[i]") -> dict:
    if not isinstance(operation, Mapping):
        raise FamilyChangeError(f"{field} must be an object")
    op = _text(operation.get("op"), f"{field}.op", maximum=64)
    if op not in TRANSFORM_OPS:
        raise FamilyChangeError(f"{field}.op is not a known transform op")
    params = operation.get("params")
    if not isinstance(params, Mapping):
        raise FamilyChangeError(f"{field}.params must be an object")
    paths = _bounded_list(operation.get("paths", []), f"{field}.paths",
                          MAX_SUBJECT_PATHS)
    for path in paths:
        _text(path, f"{field}.paths[]", maximum=MAX_PATH_STRING)
    preimage = operation.get("preimage", {})
    if not isinstance(preimage, Mapping):
        raise FamilyChangeError(f"{field}.preimage must be an object")
    return {"op": op, "params": dict(params), "paths": list(paths),
            "preimage": dict(preimage)}


def validate_family_change(record: Any) -> dict[str, Any]:
    """Validate structure and identity binding of a family change."""
    if not isinstance(record, Mapping):
        raise FamilyChangeError("family change must be an object")
    if record.get("schema_version") != FAMILY_CHANGE_SCHEMA:
        raise FamilyChangeError("family change has an invalid schema version")
    producer = record.get("producer")
    if not isinstance(producer, Mapping):
        raise FamilyChangeError("producer must be an object")
    for key in ("repository", "session", "consumer"):
        _text(producer.get(key), f"producer.{key}")
    _text(producer.get("checkout_kind", "worktree"),
          "producer.checkout_kind", maximum=32)
    base = record.get("base")
    if not isinstance(base, Mapping):
        raise FamilyChangeError("base must be an object")
    _hex40(base.get("head"), "base.head")
    _non_negative_int(base.get("generation"), "base.generation")
    state = _text(record.get("state"), "state", maximum=32)
    if state not in CHANGE_STATES:
        raise FamilyChangeError("state is not a known ChangeState")
    supersedes = _bounded_list(record.get("supersedes", []), "supersedes", 8)
    for item in supersedes:
        _text(item, "supersedes[]")
    subjects = _bounded_list(record.get("subjects", []), "subjects",
                             MAX_SUBJECTS)
    for index, subject in enumerate(subjects):
        if not isinstance(subject, Mapping):
            raise FamilyChangeError(f"subjects[{index}] must be an object")
        _text(subject.get("identity"), f"subjects[{index}].identity")
        _text(subject.get("kind", "source"), f"subjects[{index}].kind",
              maximum=64)
        paths = _bounded_list(subject.get("paths", []),
                              f"subjects[{index}].paths", MAX_SUBJECT_PATHS)
        for path in paths:
            _text(path, f"subjects[{index}].paths[]",
                  maximum=MAX_PATH_STRING)
    contracts = _bounded_list(record.get("contracts_changed", []),
                              "contracts_changed", MAX_CONTRACTS)
    for index, contract in enumerate(contracts):
        if not isinstance(contract, Mapping):
            raise FamilyChangeError(
                f"contracts_changed[{index}] must be an object")
        _text(contract.get("contract"), f"contracts_changed[{index}].contract")
    operations = _bounded_list(record.get("operations", []), "operations",
                               MAX_OPERATIONS)
    validated_operations = [validate_operation(operation, f"operations[{i}]")
                            for i, operation in enumerate(operations)]
    evidence_refs = record.get("evidence_refs", {})
    if not isinstance(evidence_refs, Mapping):
        raise FamilyChangeError("evidence_refs must be an object")
    verification = record.get("verification", {})
    if not isinstance(verification, Mapping):
        raise FamilyChangeError("verification must be an object")
    intent = record.get("intent", {})
    if not isinstance(intent, Mapping):
        raise FamilyChangeError("intent must be an object")
    summary = intent.get("summary", "")
    if not isinstance(summary, str) or len(summary) > MAX_INTENT_CHARS:
        raise FamilyChangeError("intent.summary exceeds bounds")
    validated = {
        "schema_version": FAMILY_CHANGE_SCHEMA,
        "producer": {key: producer.get(key, "") for key in
                     ("repository", "checkout_kind", "session", "consumer",
                      "claim_id")},
        "base": {"head": base["head"], "generation": base["generation"]},
        "state": state,
        "supersedes": list(supersedes),
        "subjects": [{"identity": s["identity"],
                      "kind": s.get("kind", "source"),
                      "paths": list(s.get("paths", []))} for s in subjects],
        "contracts_changed": [dict(c) for c in contracts],
        "operations": validated_operations,
        "evidence_refs": dict(evidence_refs),
        "verification": dict(verification),
        "intent": dict(intent),
    }
    identity = _text(record.get("identity"), "identity", maximum=72)
    if identity != change_identity(change_core(validated)):
        raise FamilyChangeError("identity does not bind the change core")
    validated["identity"] = identity
    return validated


def validate_contributor(record: Any) -> dict[str, Any]:
    """Validate a contributor presence record (structured facts only)."""
    if not isinstance(record, Mapping):
        raise FamilyChangeError("contributor must be an object")
    if record.get("schema_version") != FAMILY_CONTRIBUTOR_SCHEMA:
        raise FamilyChangeError("contributor has an invalid schema version")
    _text(record.get("session"), "session", maximum=64)
    _text(record.get("consumer"), "consumer")
    _bounded_list(record.get("workspaces", []), "workspaces", 16)
    _bounded_list(record.get("active_changes", []), "active_changes", 16)
    _bounded_list(record.get("claims", []), "claims", 32)
    _non_negative_int(record.get("generation", 0), "generation")
    return {
        "schema_version": FAMILY_CONTRIBUTOR_SCHEMA,
        "session": record["session"],
        "consumer": record["consumer"],
        "workspaces": list(record.get("workspaces", [])),
        "active_changes": list(record.get("active_changes", [])),
        "claims": list(record.get("claims", [])),
        "generation": record.get("generation", 0),
        "updated_at": record.get("updated_at", ""),
    }


def validate_reconciliation(record: Any) -> dict[str, Any]:
    """Validate a per-consumer reconciliation row."""
    if not isinstance(record, Mapping):
        raise FamilyChangeError("reconciliation row must be an object")
    if record.get("schema_version") != FAMILY_RECONCILIATION_SCHEMA:
        raise FamilyChangeError("reconciliation row has an invalid schema")
    _text(record.get("change"), "change", maximum=72)
    _text(record.get("consumer"), "consumer")
    consumer_class = _text(record.get("consumer_class"), "consumer_class",
                           maximum=32)
    if consumer_class not in CONSUMER_CLASSES:
        raise FamilyChangeError("consumer_class is not a known ConsumerClass")
    _non_negative_int(record.get("observed_generation", 0),
                      "observed_generation")
    _non_negative_int(record.get("canonical_generation", 0),
                      "canonical_generation")
    repair = record.get("repair_state", "no_repair")
    if repair not in REPAIR_STATES:
        raise FamilyChangeError("repair_state is not a known RepairState")
    return {
        "schema_version": FAMILY_RECONCILIATION_SCHEMA,
        "change": record["change"],
        "consumer": record["consumer"],
        "consumer_class": consumer_class,
        "observed_generation": record.get("observed_generation", 0),
        "canonical_generation": record.get("canonical_generation", 0),
        "repair_state": repair,
        "attempts": record.get("attempts", 0),
        "detail": record.get("detail", ""),
        "evidence_ref": record.get("evidence_ref", ""),
    }


def validate_family_generation(record: Any) -> dict[str, Any]:
    """Validate the family generation row (per-project generations)."""
    if not isinstance(record, Mapping):
        raise FamilyChangeError("family generation must be an object")
    if record.get("schema_version") != FAMILY_GENERATION_SCHEMA:
        raise FamilyChangeError("family generation has an invalid schema")
    projects = record.get("projects", {})
    if not isinstance(projects, Mapping) or len(projects) > 128:
        raise FamilyChangeError("projects must be a bounded object")
    for repository, entry in projects.items():
        if not isinstance(entry, Mapping):
            raise FamilyChangeError(f"projects.{repository} must be an object")
        _non_negative_int(entry.get("generation", 0),
                          f"projects.{repository}.generation")
    return {
        "schema_version": FAMILY_GENERATION_SCHEMA,
        "projects": {repository: {
            "generation": entry.get("generation", 0),
            "head": entry.get("head", ""),
            "change": entry.get("change", "")} for repository, entry in
            projects.items()},
        "cursor": record.get("cursor", 0),
    }
