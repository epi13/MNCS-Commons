"""Canonical transport contract for ``mncs.verification-plan/1``.

Commons owns the family transport contract only.  This module validates the
shape, vocabulary, identity, and cross-repository binding of a plan; it does
not choose a verification level or reinterpret compiler impact.  Consumers
may add role-specific checks (for example, binding the source to the current
checkout or joining selected test identities to their inventory).
"""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping, Sequence


PLAN_SCHEMA = "mncs.verification-plan/1"
PLAN_ID_ALGORITHM = "sha256(canonical-json-without-plan_id):hex-lowercase-v1"

VERIFICATION_LEVELS = (
    "changed_item",
    "direct_dependents",
    "affected_subsystem",
    "repository_canonical",
    "family",
)

RISK_FLAGS = (
    "abi_boundary",
    "effect_semantics",
    "high_connectivity",
    "public_contract",
    "shared_type",
    "truncated",
    "unknown_root",
)

ESCALATION_REASONS = (
    "abi_boundary_changed",
    "canonical_fixture_changed",
    "cross_repository_contract_changed",
    "cross_repository_graph_incomplete",
    "direct_dependents_affected",
    "dependent_targeted_test_failed",
    "effect_semantics_changed",
    "high_connectivity_definition_changed",
    "impact_evidence_truncated",
    "language_profile_changed",
    "migration_broad_semantic_surface",
    "parser_semantics_changed",
    "public_contract_changed",
    "serialization_format_changed",
    "shared_type_changed",
    "test_selection_unresolved",
    "unknown_changed_identity",
)

REQUIRED_EVIDENCE = (
    "selected_test_cases_pass",
    "repository_canonical_suite_pass",
    "selected_consumer_proofs_pass",
    "family_verification_pass",
)

PROOF_BOUNDARIES = (
    "changed_item",
    "direct_dependents",
    "affected_subsystem",
    "repository",
    "selected_repositories",
    "family",
)

# A family-level selection may route to an explicit consumer set without
# claiming that the entire family has been proven. Keep routing scope separate
# from the proof-boundary vocabulary.
ROUTING_SCOPES = (
    "local",
    "selected_repositories",
    "family",
)

_SHA256 = re.compile(r"^[a-f0-9]{64}$")


class VerificationPlanError(ValueError):
    """A deterministic contract rejection with a stable diagnostic code."""

    def __init__(self, code: str, path: str, message: str) -> None:
        self.code = code
        self.path = path
        self.message = message
        super().__init__(f"{code} at {path}: {message}")


def canonical_plan_bytes(value: Mapping[str, Any]) -> bytes:
    """Encode a plan identity projection with the family-defined JSON rules."""

    projection = {key: item for key, item in deepcopy(dict(value)).items() if not str(key).startswith("_")}
    projection.pop("plan_id", None)
    return json.dumps(
        projection,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def plan_identity(value: Mapping[str, Any]) -> str:
    """Return the canonical lower-case SHA-256 identity for a plan."""

    return hashlib.sha256(canonical_plan_bytes(value)).hexdigest()


def _object(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise VerificationPlanError("TYPE_OBJECT", path, "must be an object")
    return value


def _string(value: Any, path: str, *, sha256: bool = False) -> str:
    if not isinstance(value, str) or not value:
        raise VerificationPlanError("TYPE_STRING", path, "must be a non-empty string")
    if sha256 and not _SHA256.fullmatch(value):
        raise VerificationPlanError("IDENTITY_INVALID", path, "must be a lower-case SHA-256 hex identity")
    return value


def _strings(value: Any, path: str, *, allowed: Sequence[str] | None = None) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise VerificationPlanError("TYPE_STRING_ARRAY", path, "must be an array of non-empty strings")
    result = list(value)
    if len(result) != len(set(result)):
        raise VerificationPlanError("DUPLICATE_IDENTITY", path, "must not contain duplicates")
    if allowed is not None:
        unknown = sorted(set(result) - set(allowed))
        if unknown:
            raise VerificationPlanError("VOCABULARY_UNKNOWN", path, ", ".join(unknown))
    return result


def _non_negative_int(value: Any, path: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise VerificationPlanError("INTEGER_INVALID", path, "must be a non-negative integer")
    return value


def _cross_repository(value: Any) -> dict[str, Any]:
    cross = _object(value, "impact.cross_repository")
    _string(cross.get("graph_identity"), "impact.cross_repository.graph_identity", sha256=True)
    edges = cross.get("edges")
    if not isinstance(edges, list):
        raise VerificationPlanError("TYPE_ARRAY", "impact.cross_repository.edges", "must be an array")
    for index, edge_value in enumerate(edges):
        edge = _object(edge_value, f"impact.cross_repository.edges[{index}]")
        for field in ("producer_repository", "consumer_repository", "contract_identity", "contract_revision", "provenance", "fingerprint"):
            _string(edge.get(field), f"impact.cross_repository.edges[{index}].{field}", sha256=field == "fingerprint")
        _string(edge.get("consuming_identity"), f"impact.cross_repository.edges[{index}].consuming_identity")
    _strings(cross.get("selected_repositories"), "impact.cross_repository.selected_repositories")
    if not isinstance(cross.get("complete"), bool):
        raise VerificationPlanError("TYPE_BOOLEAN", "impact.cross_repository.complete", "must be boolean")
    _strings(cross.get("limitations"), "impact.cross_repository.limitations")
    edge_repositories = sorted(
        {
            edge["consumer_repository"]
            for edge_value in edges
            for edge in [_object(edge_value, "impact.cross_repository.edges")]
        }
    )
    if edge_repositories != sorted(cross["selected_repositories"]):
        raise VerificationPlanError(
            "INVENTORY_MISMATCH",
            "impact.cross_repository.selected_repositories",
            "must equal the consumer repositories represented by edges",
        )
    return dict(cross)


def validate_plan(
    value: Any,
    *,
    source_path: Path | None = None,
    plan_path: Path | None = None,
    inventory_test_identities: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Validate and return a detached plan projection.

    ``source_path`` and ``inventory_test_identities`` are optional role-bound
    checks.  They live here so every consumer uses the same stale-source and
    inventory disposition when it elects to provide those facts.
    """

    plan = _object(value, "<root>")
    if plan.get("schema_version") != PLAN_SCHEMA:
        raise VerificationPlanError("SCHEMA_UNSUPPORTED", "schema_version", f"must be {PLAN_SCHEMA}")
    plan_id = _string(plan.get("plan_id"), "plan_id", sha256=True)
    if plan_id != plan_identity(plan):
        raise VerificationPlanError("IDENTITY_MISMATCH", "plan_id", "does not match the canonical plan identity")

    source = _object(plan.get("source"), "source")
    _string(source.get("path"), "source.path")
    _string(source.get("sha256"), "source.sha256", sha256=True)
    for field in ("subject_identity", "subject_fingerprint"):
        if field in source:
            _string(source[field], f"source.{field}", sha256=field == "subject_fingerprint")

    impact = _object(plan.get("impact"), "impact")
    _string(impact.get("graph_identity"), "impact.graph_identity", sha256=True)
    _strings(impact.get("roots"), "impact.roots")
    _non_negative_int(impact.get("affected_count"), "impact.affected_count")
    _strings(impact.get("direct_dependents"), "impact.direct_dependents")
    _strings(impact.get("test_identities"), "impact.test_identities")
    _strings(impact.get("risk_flags"), "impact.risk_flags", allowed=RISK_FLAGS)
    if not isinstance(impact.get("complete"), bool):
        raise VerificationPlanError("TYPE_BOOLEAN", "impact.complete", "must be boolean")
    _strings(impact.get("limitations"), "impact.limitations")
    cross = _cross_repository(impact.get("cross_repository"))

    selection = _object(plan.get("selection"), "selection")
    level = selection.get("level")
    if level not in VERIFICATION_LEVELS:
        raise VerificationPlanError("VOCABULARY_UNKNOWN", "selection.level", "unsupported verification level")
    selected = _strings(selection.get("selected_test_identities"), "selection.selected_test_identities")
    available = _non_negative_int(selection.get("available_test_count"), "selection.available_test_count")
    if len(selected) > available:
        raise VerificationPlanError("INVENTORY_MISMATCH", "selection.selected_test_identities", "selected count exceeds available test count")
    _strings(selection.get("escalation_reasons"), "selection.escalation_reasons", allowed=ESCALATION_REASONS)
    selected_repositories = _strings(selection.get("selected_repositories"), "selection.selected_repositories")
    repository_count = _non_negative_int(selection.get("available_repository_count"), "selection.available_repository_count")
    if len(selected_repositories) > repository_count:
        raise VerificationPlanError("INVENTORY_MISMATCH", "selection.selected_repositories", "selected count exceeds available repository count")
    routing_scope = selection.get("routing_scope")
    if routing_scope is None:
        # Preserve the interpretation of plans emitted before this explicit
        # distinction was added.
        routing_scope = (
            "selected_repositories"
            if level == "family" and selected_repositories
            else ("family" if level == "family" else "local")
        )
    elif routing_scope not in ROUTING_SCOPES:
        raise VerificationPlanError("VOCABULARY_UNKNOWN", "selection.routing_scope", "unsupported routing scope")
    if routing_scope == "local" and selected_repositories:
        raise VerificationPlanError(
            "ROUTING_SCOPE_INVALID",
            "selection.routing_scope",
            "local routing cannot name selected repositories",
        )
    if routing_scope == "selected_repositories" and not selected_repositories:
        raise VerificationPlanError(
            "ROUTING_SCOPE_INVALID",
            "selection.selected_repositories",
            "selected-repository routing requires at least one consumer",
        )
    if routing_scope == "family" and level != "family":
        raise VerificationPlanError(
            "ROUTING_SCOPE_INVALID",
            "selection.routing_scope",
            "family routing requires family verification level",
        )

    proof = _object(plan.get("proof"), "proof")
    if not isinstance(proof.get("sufficient_to_stop"), bool):
        raise VerificationPlanError("TYPE_BOOLEAN", "proof.sufficient_to_stop", "must be boolean")
    evidence = _strings(proof.get("required_evidence"), "proof.required_evidence", allowed=REQUIRED_EVIDENCE)
    boundary = _object(proof.get("boundary"), "proof.boundary")
    claimed_scope = boundary.get("claimed_scope")
    if claimed_scope not in PROOF_BOUNDARIES:
        raise VerificationPlanError("VOCABULARY_UNKNOWN", "proof.boundary.claimed_scope", "unsupported proof boundary")
    if not isinstance(boundary.get("established"), bool):
        raise VerificationPlanError("TYPE_BOOLEAN", "proof.boundary.established", "must be boolean")
    _string(boundary.get("executor"), "proof.boundary.executor")
    stop_condition = _string(boundary.get("stop_condition"), "proof.boundary.stop_condition")
    if stop_condition not in evidence:
        raise VerificationPlanError(
            "PROOF_BOUNDARY_INVALID",
            "proof.boundary.stop_condition",
            "must name one of proof.required_evidence",
        )
    expected_scope = "repository" if level == "repository_canonical" else level
    if routing_scope == "selected_repositories":
        expected_scope = "selected_repositories"
    if claimed_scope != expected_scope:
        raise VerificationPlanError(
            "PROOF_BOUNDARY_INVALID",
            "proof.boundary.claimed_scope",
            f"must be {expected_scope} for selection level {level}",
        )
    if boundary["established"] != proof["sufficient_to_stop"]:
        raise VerificationPlanError(
            "PROOF_BOUNDARY_INVALID",
            "proof.boundary.established",
            "must match proof.sufficient_to_stop",
        )
    if level == "family" and proof["sufficient_to_stop"]:
        raise VerificationPlanError("PROOF_BOUNDARY_INVALID", "proof.sufficient_to_stop", "family routing evidence is not family proof")
    if level == "family" and routing_scope == "family" and "family_verification_pass" not in evidence:
        raise VerificationPlanError("PROOF_BOUNDARY_INVALID", "proof.required_evidence", "family plans require family_verification_pass")
    if routing_scope == "selected_repositories" and "selected_consumer_proofs_pass" not in evidence:
        raise VerificationPlanError(
            "PROOF_BOUNDARY_INVALID",
            "proof.required_evidence",
            "selected-repository plans require selected_consumer_proofs_pass",
        )

    provenance = _object(plan.get("provenance"), "provenance")
    _string(provenance.get("provider"), "provenance.provider")
    _string(provenance.get("policy"), "provenance.policy")

    reasons = selection["escalation_reasons"]
    if not impact["complete"] and not ({"impact_evidence_truncated", "unknown_changed_identity"} & set(reasons)):
        raise VerificationPlanError("COMPLETENESS_REASON_MISSING", "selection.escalation_reasons", "incomplete impact requires an explicit uncertainty reason")
    if not cross["complete"] and "cross_repository_contract_changed" in reasons and "cross_repository_graph_incomplete" not in reasons:
        raise VerificationPlanError("COMPLETENESS_REASON_MISSING", "selection.escalation_reasons", "incomplete cross-repository graph requires cross_repository_graph_incomplete")

    if source_path is not None:
        try:
            current_sha256 = hashlib.sha256(source_path.read_bytes()).hexdigest()
        except OSError as error:
            raise VerificationPlanError("SOURCE_UNAVAILABLE", "source.path", str(error)) from error
        if source["sha256"] != current_sha256:
            raise VerificationPlanError("SOURCE_STALE", "source.sha256", "does not match the current source")
        declared = Path(source["path"])
        if not declared.is_absolute() and plan_path is not None:
            declared = plan_path.parent / declared
        try:
            if declared.resolve() != source_path.resolve():
                raise VerificationPlanError("SOURCE_BINDING_MISMATCH", "source.path", "does not match the current source")
        except OSError as error:
            raise VerificationPlanError("SOURCE_UNAVAILABLE", "source.path", str(error)) from error

    if inventory_test_identities is not None:
        inventory = set(inventory_test_identities)
        missing = sorted(set(selected) - inventory)
        if missing:
            raise VerificationPlanError("INVENTORY_MISMATCH", "selection.selected_test_identities", ", ".join(missing))
        if available != len(inventory):
            raise VerificationPlanError("INVENTORY_MISMATCH", "selection.available_test_count", "does not match the current inventory")

    return deepcopy(dict(plan))


def load_plan(path: Path, **kwargs: Any) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise VerificationPlanError("DOCUMENT_INVALID", str(path), str(error)) from error
    return validate_plan(value, plan_path=path, **kwargs)
