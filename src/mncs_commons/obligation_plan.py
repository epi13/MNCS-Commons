"""Canonical obligation/evidence planning transport.

Commons owns the bounded wire contract and identity checks. RAVEL owns the
selection decision that populates it; repository owners own the obligation
inventory; providers own execution and evidence. This module intentionally
does not execute commands or decide whether a semantic change is relevant.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping, Sequence


OBLIGATION_PLAN_SCHEMA = "mncs.verification-obligation-plan/1"
OBLIGATION_INVENTORY_SCHEMA = "mncs-family.verification-obligation-inventory/v1"
OBLIGATION_STATUSES = (
    "required",
    "current",
    "new_execution_required",
    "stale",
    "contradictory",
    "selection_unresolved",
    "escalation_required",
    "not_selected",
)
LIFECYCLES = ("permanent", "transitional", "scheduled", "reference_only", "retired")
GUARANTEE_DOMAINS = (
    "semantic",
    "parser_front_end",
    "type_system",
    "compiler",
    "runtime",
    "backend_portability",
    "integration",
    "family_contract",
)
EVIDENCE_ROLES = (
    "canonical_regression",
    "conformance",
    "differential_oracle",
    "migration_parity",
    "pressure_reproducer",
    "historical_reference",
)
EXECUTOR_KINDS = (
    "native_first_class_test",
    "compile_experiment",
    "diagnostic_test",
    "backend_check",
    "differential_oracle",
    "migration_parity",
    "external_integration",
)
OBLIGATION_SCOPES = ("local", "consumer", "family", "repository_canonical")
REPOSITORY_PLAN_SCOPES = ("source_module", "repository_canonical")
_IDENTITY_LENGTH = 4096


class ObligationPlanError(ValueError):
    """A deterministic obligation contract rejection."""

    def __init__(self, code: str, path: str, message: str) -> None:
        self.code = code
        self.path = path
        self.message = message
        super().__init__(f"{code} at {path}: {message}")


def _string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ObligationPlanError("TYPE_STRING", path, "must be a non-empty string")
    if len(value) > _IDENTITY_LENGTH:
        raise ObligationPlanError("BOUND_EXCEEDED", path, "string exceeds the contract bound")
    return value


def _strings(value: Any, path: str, *, allowed: Sequence[str] | None = None) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ObligationPlanError("TYPE_STRING_ARRAY", path, "must be an array of non-empty strings")
    result = list(value)
    if len(result) != len(set(result)):
        raise ObligationPlanError("DUPLICATE_IDENTITY", path, "must not contain duplicates")
    if allowed is not None:
        unknown = sorted(set(result) - set(allowed))
        if unknown:
            raise ObligationPlanError("VOCABULARY_UNKNOWN", path, ", ".join(unknown))
    return result


def _object(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ObligationPlanError("TYPE_OBJECT", path, "must be an object")
    return value


def _positive_int(value: Any, path: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ObligationPlanError("INTEGER_INVALID", path, "must be a positive integer")
    return value


def _optional_strings(value: Any, path: str) -> list[str]:
    if value is None:
        return []
    return _strings(value, path)


def _ordered_strings(value: Any, path: str) -> list[str]:
    if not isinstance(value, list) or not value or not all(isinstance(item, str) and item for item in value):
        raise ObligationPlanError("TYPE_ARRAY", path, "must be a non-empty array of non-empty strings")
    if len(value) > 16:
        raise ObligationPlanError("BOUND_EXCEEDED", path, "must contain at most 16 arguments")
    return list(value)


def _validate_executor(value: Any, path: str) -> dict[str, Any]:
    executor = _object(value, path)
    provider = _string(executor.get("provider"), f"{path}.provider")
    kind = executor.get("kind")
    if kind not in EXECUTOR_KINDS:
        raise ObligationPlanError("VOCABULARY_UNKNOWN", f"{path}.kind", f"unsupported executor kind {kind!r}")
    entrypoint = _string(executor.get("entrypoint"), f"{path}.entrypoint")
    result = {"provider": provider, "kind": kind, "entrypoint": entrypoint}
    for field in ("declaration_identities", "test_case_identities", "source_paths", "library_paths"):
        if field in executor:
            result[field] = _strings(executor[field], f"{path}.{field}")
    for field in ("verifier_identity", "target_identity", "working_directory"):
        if field in executor:
            result[field] = _string(executor[field], f"{path}.{field}")
    if "argv" in executor:
        result["argv"] = _ordered_strings(executor["argv"], f"{path}.argv")
    if "timeout_seconds" in executor:
        timeout = executor["timeout_seconds"]
        if not isinstance(timeout, int) or isinstance(timeout, bool) or not 1 <= timeout <= 3600:
            raise ObligationPlanError("INTEGER_INVALID", f"{path}.timeout_seconds", "must be between 1 and 3600")
        result["timeout_seconds"] = timeout
    return result


def _validate_evidence_identity(value: Any, path: str) -> dict[str, Any]:
    evidence = _object(value, path)
    result = {}
    for field in ("subject_fields", "definition_fields", "execution_fields"):
        result[field] = _strings(evidence.get(field), f"{path}.{field}")
    return result


def _validate_inventory_obligation(value: Any, index: int) -> dict[str, Any]:
    path = f"obligations[{index}]"
    item = _object(value, path)
    identity = _string(item.get("identity"), f"{path}.identity")
    domain = item.get("guarantee_domain")
    if domain not in GUARANTEE_DOMAINS:
        raise ObligationPlanError("VOCABULARY_UNKNOWN", f"{path}.guarantee_domain", f"unsupported domain {domain!r}")
    role = item.get("evidence_role")
    if role not in EVIDENCE_ROLES:
        raise ObligationPlanError("VOCABULARY_UNKNOWN", f"{path}.evidence_role", f"unsupported evidence role {role!r}")
    lifecycle = item.get("lifecycle")
    if lifecycle not in LIFECYCLES:
        raise ObligationPlanError("VOCABULARY_UNKNOWN", f"{path}.lifecycle", f"unsupported lifecycle {lifecycle!r}")
    scope = item.get("scope")
    if scope not in OBLIGATION_SCOPES:
        raise ObligationPlanError("VOCABULARY_UNKNOWN", f"{path}.scope", f"unsupported scope {scope!r}")
    result = {
        "identity": identity,
        "title": _string(item.get("title", identity), f"{path}.title"),
        "guarantee_domain": domain,
        "evidence_role": role,
        "lifecycle": lifecycle,
        "scope": scope,
        "subjects": _strings(item.get("subjects"), f"{path}.subjects"),
        "invalidation_dependencies": _strings(
            item.get("invalidation_dependencies"), f"{path}.invalidation_dependencies"
        ),
        "executor": _validate_executor(item.get("executor"), f"{path}.executor"),
        "evidence_identity": _validate_evidence_identity(item.get("evidence_identity"), f"{path}.evidence_identity"),
    }
    if "backend_requirements" in item:
        backend = _object(item["backend_requirements"], f"{path}.backend_requirements")
        result["backend_requirements"] = {
            field: _optional_strings(backend.get(field), f"{path}.backend_requirements.{field}")
            for field in ("profiles", "runtimes", "backends")
            if field in backend
        }
    if "retirement" in item:
        retirement = _object(item["retirement"], f"{path}.retirement")
        keep = retirement.get("retain_as")
        if keep not in {"delete", "reference_only", "scheduled"}:
            raise ObligationPlanError("VOCABULARY_UNKNOWN", f"{path}.retirement.retain_as", f"unsupported disposition {keep!r}")
        result["retirement"] = {
            "trigger": _string(retirement.get("trigger"), f"{path}.retirement.trigger"),
            "retain_as": keep,
        }
        if retirement.get("replacement") is not None:
            result["retirement"]["replacement"] = _string(retirement["replacement"], f"{path}.retirement.replacement")
    if item.get("notes") is not None:
        result["notes"] = _string(item["notes"], f"{path}.notes")
    return result


def validate_inventory(value: Any, *, repository: str | None = None) -> dict[str, Any]:
    root = _object(value, "<root>")
    if root.get("schema_version") != OBLIGATION_INVENTORY_SCHEMA:
        raise ObligationPlanError("SCHEMA_UNSUPPORTED", "schema_version", f"must be {OBLIGATION_INVENTORY_SCHEMA}")
    inventory_repository = _string(root.get("repository"), "repository")
    if repository is not None and inventory_repository != repository:
        raise ObligationPlanError("REPOSITORY_MISMATCH", "repository", f"must be {repository}")
    revision = _positive_int(root.get("revision"), "revision")
    raw_obligations = root.get("obligations")
    if not isinstance(raw_obligations, list):
        raise ObligationPlanError("TYPE_ARRAY", "obligations", "must be an array")
    obligations = [_validate_inventory_obligation(item, index) for index, item in enumerate(raw_obligations)]
    identities = [item["identity"] for item in obligations]
    if len(identities) != len(set(identities)):
        raise ObligationPlanError("DUPLICATE_IDENTITY", "obligations", "obligation identities must be unique")
    normalized = {
        "schema_version": OBLIGATION_INVENTORY_SCHEMA,
        "repository": inventory_repository,
        "revision": revision,
        "obligations": obligations,
    }
    return normalized


def canonical_inventory_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(dict(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def inventory_identity(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_inventory_bytes(value)).hexdigest()


def _canonical_plan_projection(value: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(value))
    result.pop("obligation_plan_id", None)
    return result


def obligation_plan_identity(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(_canonical_plan_projection(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _validate_evidence(value: Any, path: str) -> dict[str, Any]:
    evidence = _object(value, path)
    status = evidence.get("status")
    if status not in {"PASS", "FAIL", "UNKNOWN"}:
        raise ObligationPlanError("VOCABULARY_UNKNOWN", f"{path}.status", f"unsupported evidence status {status!r}")
    result = {"status": status, "evidence_identity": _string(evidence.get("evidence_identity"), f"{path}.evidence_identity")}
    for field in (
        "obligation_identity",
        "repository_identity",
        "repository_revision",
        "repository_fingerprint",
        "subject_identity",
        "subject_fingerprint",
        "definition_identity",
        "executor_identity",
        "verifier_identity",
        "invalidation_identity",
        "reason",
    ):
        if evidence.get(field) is not None:
            result[field] = _string(evidence[field], f"{path}.{field}")
    return result


def _validate_selected(value: Any, index: int) -> dict[str, Any]:
    path = f"obligations[{index}]"
    item = _object(value, path)
    status = item.get("status")
    if status not in OBLIGATION_STATUSES:
        raise ObligationPlanError("VOCABULARY_UNKNOWN", f"{path}.status", f"unsupported status {status!r}")
    lifecycle = item.get("lifecycle")
    if lifecycle not in LIFECYCLES:
        raise ObligationPlanError("VOCABULARY_UNKNOWN", f"{path}.lifecycle", f"unsupported lifecycle {lifecycle!r}")
    domain = item.get("guarantee_domain")
    if domain not in GUARANTEE_DOMAINS:
        raise ObligationPlanError("VOCABULARY_UNKNOWN", f"{path}.guarantee_domain", f"unsupported domain {domain!r}")
    role = item.get("evidence_role")
    if role not in EVIDENCE_ROLES:
        raise ObligationPlanError("VOCABULARY_UNKNOWN", f"{path}.evidence_role", f"unsupported evidence role {role!r}")
    result = {
        "identity": _string(item.get("identity"), f"{path}.identity"),
        "scope": item.get("scope", "local"),
        "status": status,
        "lifecycle": lifecycle,
        "guarantee_domain": domain,
        "evidence_role": role,
        "reason": _string(item.get("reason"), f"{path}.reason"),
        "evidence_identities": _strings(item.get("evidence_identities", []), f"{path}.evidence_identities"),
        "test_case_identities": _strings(item.get("test_case_identities", []), f"{path}.test_case_identities"),
    }
    if result["scope"] not in OBLIGATION_SCOPES:
        raise ObligationPlanError("VOCABULARY_UNKNOWN", f"{path}.scope", "unsupported scope")
    for field in (
        "definition_identity",
        "subject_identity",
        "subject_fingerprint",
        "executor_identity",
        "verifier_identity",
        "invalidation_identity",
    ):
        if item.get(field) is not None:
            result[field] = _string(item[field], f"{path}.{field}")
    if item.get("executor") is not None:
        result["executor"] = _validate_executor(item["executor"], f"{path}.executor")
    return result


def validate_obligation_plan(value: Any) -> dict[str, Any]:
    root = _object(value, "<root>")
    if root.get("schema_version") != OBLIGATION_PLAN_SCHEMA:
        raise ObligationPlanError("SCHEMA_UNSUPPORTED", "schema_version", f"must be {OBLIGATION_PLAN_SCHEMA}")
    plan_id = _string(root.get("obligation_plan_id"), "obligation_plan_id")
    if plan_id != obligation_plan_identity(root):
        raise ObligationPlanError("IDENTITY_MISMATCH", "obligation_plan_id", "does not match canonical identity")
    _string(root.get("verification_plan_id"), "verification_plan_id")
    source = _object(root.get("source"), "source")
    _string(source.get("path"), "source.path")
    _string(source.get("sha256"), "source.sha256")
    _string(root.get("impact_identity"), "impact_identity")
    if root.get("impact") is not None:
        impact = _object(root["impact"], "impact")
        _strings(impact.get("guarantee_domains", []), "impact.guarantee_domains", allowed=GUARANTEE_DOMAINS)
        _strings(impact.get("change_kinds", []), "impact.change_kinds")
        _strings(impact.get("roots", []), "impact.roots")
    inventory = _object(root.get("inventory"), "inventory")
    _string(inventory.get("repository"), "inventory.repository")
    _string(inventory.get("identity"), "inventory.identity")
    _positive_int(inventory.get("revision"), "inventory.revision")
    repository = root.get("repository")
    repository_scope: str | None = None
    if repository is not None:
        repository = _object(repository, "repository")
        _string(repository.get("identity"), "repository.identity")
        _string(repository.get("revision"), "repository.revision")
        _string(repository.get("fingerprint"), "repository.fingerprint")
        _string(repository.get("inventory_identity"), "repository.inventory_identity")
        repository_scope = repository.get("scope")
        if repository_scope not in REPOSITORY_PLAN_SCOPES:
            raise ObligationPlanError("VOCABULARY_UNKNOWN", "repository.scope", "unsupported repository proof scope")
        if not isinstance(repository.get("complete"), bool):
            raise ObligationPlanError("TYPE_BOOLEAN", "repository.complete", "must be boolean")
        required_repository = _strings(repository.get("required_obligation_identities"), "repository.required_obligation_identities")
        selected_repository = _strings(repository.get("selected_obligation_identities"), "repository.selected_obligation_identities")
        missing_repository = _strings(repository.get("missing_obligation_identities"), "repository.missing_obligation_identities")
        source_inventories = repository.get("compiler_test_inventories", [])
        if not isinstance(source_inventories, list):
            raise ObligationPlanError("TYPE_ARRAY", "repository.compiler_test_inventories", "must be an array")
        for index, source_inventory_value in enumerate(source_inventories):
            source_inventory = _object(source_inventory_value, f"repository.compiler_test_inventories[{index}]")
            _string(source_inventory.get("path"), f"repository.compiler_test_inventories[{index}].path")
            if source_inventory.get("scope") != "source_module":
                raise ObligationPlanError("PROOF_BOUNDARY_INVALID", f"repository.compiler_test_inventories[{index}].scope", "compiler test inventories remain source_module scoped")
            _string(source_inventory.get("identity"), f"repository.compiler_test_inventories[{index}].identity")
            _strings(source_inventory.get("test_case_identities"), f"repository.compiler_test_inventories[{index}].test_case_identities")
        if sorted(set(required_repository) - set(selected_repository)) != sorted(missing_repository):
            raise ObligationPlanError("INVENTORY_MISMATCH", "repository.missing_obligation_identities", "must equal the declared required identities absent from the selected set")
        if repository.get("complete") and (missing_repository or required_repository != selected_repository):
            raise ObligationPlanError("PROOF_BOUNDARY_INVALID", "repository.complete", "complete closure must select every declared repository obligation")
    obligations = root.get("obligations")
    if not isinstance(obligations, list):
        raise ObligationPlanError("TYPE_ARRAY", "obligations", "must be an array")
    normalized_obligations = [_validate_selected(item, index) for index, item in enumerate(obligations)]
    if len({item["identity"] for item in normalized_obligations}) != len(normalized_obligations):
        raise ObligationPlanError("DUPLICATE_IDENTITY", "obligations", "selected identities must be unique")
    if root.get("excluded") is not None:
        excluded = root["excluded"]
        if not isinstance(excluded, list):
            raise ObligationPlanError("TYPE_ARRAY", "excluded", "must be an array")
        for index, item in enumerate(excluded):
            entry = _object(item, f"excluded[{index}]")
            _string(entry.get("identity"), f"excluded[{index}].identity")
            if entry.get("lifecycle") not in LIFECYCLES:
                raise ObligationPlanError("VOCABULARY_UNKNOWN", f"excluded[{index}].lifecycle", "unsupported lifecycle")
            _string(entry.get("reason"), f"excluded[{index}].reason")
    evidence = root.get("evidence", [])
    if not isinstance(evidence, list):
        raise ObligationPlanError("TYPE_ARRAY", "evidence", "must be an array")
    normalized_evidence = [_validate_evidence(item, f"evidence[{index}]") for index, item in enumerate(evidence)]
    stop = _object(root.get("stop"), "stop")
    if not isinstance(stop.get("sufficient_to_stop"), bool):
        raise ObligationPlanError("TYPE_BOOLEAN", "stop.sufficient_to_stop", "must be boolean")
    required_stop = _strings(stop.get("required_obligation_identities"), "stop.required_obligation_identities")
    _strings(stop.get("new_execution_required"), "stop.new_execution_required")
    _strings(stop.get("escalation_reasons"), "stop.escalation_reasons")
    _string(stop.get("boundary"), "stop.boundary")
    if repository_scope == "repository_canonical":
        if not repository.get("complete") and stop.get("sufficient_to_stop"):
            raise ObligationPlanError("PROOF_BOUNDARY_INVALID", "stop.sufficient_to_stop", "incomplete repository closure cannot establish a proof")
        if set(required_repository) != set(required_stop):
            raise ObligationPlanError("INVENTORY_MISMATCH", "stop.required_obligation_identities", "must equal the repository-canonical obligation set")
        if set(selected_repository) != set(required_stop) and stop.get("sufficient_to_stop"):
            raise ObligationPlanError("PROOF_BOUNDARY_INVALID", "stop.sufficient_to_stop", "repository closure requires every declared obligation")
        by_identity = {item["identity"]: item for item in normalized_obligations}
        actual_selected_repository = [
            item["identity"]
            for item in normalized_obligations
            if item["scope"] == "repository_canonical"
        ]
        if set(actual_selected_repository) != set(repository.get("selected_obligation_identities", [])):
            raise ObligationPlanError("INVENTORY_MISMATCH", "repository.selected_obligation_identities", "must match the selected repository-canonical obligations")
        evidence_by_id: dict[str, list[dict[str, Any]]] = {}
        for item in normalized_evidence:
            obligation_identity = item.get("obligation_identity")
            if obligation_identity:
                evidence_by_id.setdefault(obligation_identity, []).append(item)
        for identity in stop["required_obligation_identities"]:
            selected = by_identity.get(identity)
            if selected is None and identity in missing_repository and not repository.get("complete"):
                continue
            if selected is None or selected["scope"] != "repository_canonical":
                raise ObligationPlanError("INVENTORY_MISMATCH", "obligations", f"repository obligation {identity!r} is absent or has source-local scope")
            if selected.get("status") == "current":
                exact_evidence = [
                    item
                    for item in evidence_by_id.get(identity, [])
                    if item.get("repository_identity") == repository.get("identity")
                    and item.get("repository_fingerprint") == repository.get("fingerprint")
                    and item.get("subject_identity") == selected.get("subject_identity")
                    and item.get("subject_fingerprint") == selected.get("subject_fingerprint")
                    and item.get("definition_identity") == selected.get("definition_identity")
                    and item.get("executor_identity") == selected.get("executor_identity")
                    and item.get("verifier_identity") == selected.get("verifier_identity")
                    and item.get("invalidation_identity") == selected.get("invalidation_identity")
                ]
                if not exact_evidence or any(item.get("status") != "PASS" for item in exact_evidence):
                    raise ObligationPlanError("EVIDENCE_STALE", f"obligations.{identity}", "current status lacks complete, current identity-bound PASS evidence")
        if stop.get("sufficient_to_stop") and any(by_identity[identity]["status"] != "current" for identity in stop["required_obligation_identities"]):
            raise ObligationPlanError("PROOF_BOUNDARY_INVALID", "stop.sufficient_to_stop", "all required repository obligations must be current PASS")
    elif repository_scope == "source_module" and stop.get("sufficient_to_stop"):
        raise ObligationPlanError("PROOF_BOUNDARY_INVALID", "stop.sufficient_to_stop", "source-module inventory cannot establish repository closure")
    elif stop.get("sufficient_to_stop") and any(item["scope"] == "repository_canonical" for item in normalized_obligations):
        raise ObligationPlanError("PROOF_BOUNDARY_INVALID", "stop.sufficient_to_stop", "repository-canonical obligations require an explicit repository closure object")
    return deepcopy(dict(root))


def load_inventory(path: Path, *, repository: str | None = None) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ObligationPlanError("DOCUMENT_INVALID", str(path), str(error)) from error
    return validate_inventory(document, repository=repository)


def load_obligation_plan(path: Path) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ObligationPlanError("DOCUMENT_INVALID", str(path), str(error)) from error
    return validate_obligation_plan(document)
