"""Compact family architecture facts, validation, and bounded projections.

This module is deliberately a coordination surface rather than an application
registry.  The checked-in model declares ownership and convergence state; the
helpers below make that declaration content-addressed, validate the declared
relationships, and expose only the slice a caller requested.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping

from .family_registry import CANONICAL_FAMILY


MODEL_SCHEMA_VERSION = "commons.mncs.architecture-model/1"
ARCHITECTURE_SCHEMA_IDENTITY = MODEL_SCHEMA_VERSION
DELTA_HISTORY_SCHEMA_VERSION = "commons.mncs.architecture-delta-history/1"
DEFAULT_DELTA_HISTORY_PATH = "family/architecture-delta-history-v1.json"
_CONTENT_PREFIX = "sha256:"
_VERSIONED = re.compile(r"(?:^|/|\.)v\d+(?:\.|/|$)", re.IGNORECASE)
_ROLES = {"adapter", "differential_oracle", "compatibility", "shadow", "implementation"}
_RETIREMENT_DIRECTIONS = {"canonical_survivor", "shadow_survivor"}
_RETIREMENT_STATES = {"active", "retired"}
_APPLICATION_PREFIXES = ("actions.", "debug.", "ravel.", "test.", "doctor.")
_REPOSITORY_DIRS = {
    "mncs-commons": "MNCS-Commons",
    "mncs-language": "mncs-language",
    "mncs-test": "mncs-test",
    "mncs-actions": "mncs-actions",
    "mncs-debug": "mncs-debug",
    "ravel": "RAVEL",
    "mncs-language-service": "mncs-language-service",
    "mncs-doctor": "mncs-doctor",
}


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def architecture_content_identity(value: Mapping[str, Any]) -> str:
    """Return the deterministic identity of a model without its identity field."""

    payload = dict(value)
    payload.pop("content_identity", None)
    # Accepting this legacy field makes validation useful while a caller is
    # migrating an in-memory model, but it never contributes to the digest.
    payload.pop("model_identity", None)
    # The loader attaches the sidecar history for query-time use.  It is
    # deliberately excluded from the model identity because a delta entry
    # cannot hash a model that contains a reference to its own identity.
    payload.pop("_delta_history", None)
    return _CONTENT_PREFIX + hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def load_architecture_model(root: str | Path) -> dict[str, Any]:
    root_path = Path(root)
    path = root_path / "family/architecture-model-v1.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("architecture model root must be an object")
    history_config = value.get("delta_history", {})
    history_path = DEFAULT_DELTA_HISTORY_PATH
    if isinstance(history_config, Mapping) and isinstance(history_config.get("path"), str):
        history_path = history_config["path"]
    sidecar = root_path / history_path
    if sidecar.is_file():
        history = json.loads(sidecar.read_text(encoding="utf-8"))
        if isinstance(history, dict):
            value["_delta_history"] = history
    return value


def _repository_root(workspace_root: Path, repository: object) -> Path | None:
    if not isinstance(repository, str) or not repository:
        return None
    directory = _REPOSITORY_DIRS.get(repository, repository)
    candidates = [workspace_root / directory]
    if repository == "mncs-commons" or workspace_root.name == directory:
        candidates.insert(0, workspace_root)
    if workspace_root.parent != workspace_root:
        candidates.append(workspace_root.parent / directory)
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return None


def _same_declared_path(left: object, right: object) -> bool:
    if not isinstance(left, str) or not isinstance(right, str):
        return False
    return left.strip("/") == right.strip("/")


def _projection_metrics(capabilities: list[Mapping[str, Any]], generators: list[Any]) -> dict[str, int]:
    return {
        "capabilities": len(capabilities),
        "alternates": sum(
            len(item.get("active_alternates", []))
            for item in capabilities
            if isinstance(item.get("active_alternates", []), list)
        ),
        "generators": len(generators),
    }


def _projection_envelope(
    model: Mapping[str, Any],
    *,
    mode: str,
    layers: list[str],
    counts: dict[str, int],
    complete: bool = True,
    limitations: list[str] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema_identity": model.get("schema_identity", model.get("schema_version")),
        "content_identity": model.get("content_identity"),
        "mode": mode,
        "layers": layers,
        "counts": counts,
        "complete": complete,
    }
    if limitations:
        result["limitations"] = limitations
    return result


def _compact_capability(capability: Mapping[str, Any]) -> dict[str, Any]:
    canonical = capability.get("canonical", {})
    return {
        "id": capability.get("id"),
        "owner": capability.get("owner"),
        "canonical": canonical,
        "versioning": capability.get("versioning", {}),
        "active_alternates": capability.get("active_alternates", []),
        "shadow": capability.get("shadow"),
        **({"evidence": capability["evidence"]} if "evidence" in capability else {}),
    }


def architecture_query(
    model: Mapping[str, Any],
    query: str,
    value: str | None = None,
) -> dict[str, Any]:
    """Build a bounded architecture projection for one conceptual query."""

    capabilities = [item for item in model.get("capabilities", []) if isinstance(item, Mapping)]
    generators = [item for item in model.get("generators", []) if isinstance(item, Mapping)]
    identity = _projection_envelope(
        model,
        mode="targeted",
        layers=["identity"],
        counts={"capabilities": 0, "alternates": 0, "generators": 0},
    )

    if query == "capability":
        matches = [item for item in capabilities if item.get("id") == value]
        identity["counts"] = _projection_metrics(matches, [])
        result: dict[str, Any] = {"projection": identity, "capability": None}
        if matches:
            capability = matches[0]
            identity["layers"] = ["identity", "architecture", "contract", "implementation", "evidence"]
            result["capability"] = _compact_capability(capability)
        else:
            identity["complete"] = False
            identity["limitations"] = ["capability id is not present in the current model"]
        return result

    if query == "canonical":
        matches = [item for item in capabilities if item.get("id") == value]
        identity["counts"] = _projection_metrics(matches, [])
        identity["layers"] = ["identity", "architecture", "contract", "implementation"]
        result = {"projection": identity, "capability": value, "canonical": None}
        if matches:
            result["canonical"] = {
                "owner": matches[0].get("owner"),
                "canonical": matches[0].get("canonical"),
                "versioning": matches[0].get("versioning", {}),
                "active_alternates": matches[0].get("active_alternates", []),
                "shadow": matches[0].get("shadow"),
            }
        else:
            identity["complete"] = False
            identity["limitations"] = ["capability id is not present in the current model"]
        return result

    if query == "repository":
        matches = [
            item
            for item in capabilities
            if item.get("owner") == value
            or (
                isinstance(item.get("canonical"), Mapping)
                and item["canonical"].get("repository") == value
            )
        ]
        identity["layers"] = ["identity", "architecture", "contract", "implementation"]
        identity["counts"] = _projection_metrics(matches, [])
        return {
            "projection": identity,
            "repository": value,
            "capabilities": [
                {
                    "id": item.get("id"),
                    "owner": item.get("owner"),
                    "canonical": item.get("canonical"),
                    "versioning": item.get("versioning", {}),
                    "active_alternates": item.get("active_alternates", []),
                    "shadow": item.get("shadow"),
                }
                for item in matches
            ],
        }

    if query == "changes":
        current = model.get("content_identity")
        if value == current:
            return {
                "projection": _projection_envelope(
                    model,
                    mode="unchanged",
                    layers=["identity", "delta"],
                    counts={"capabilities": 0, "alternates": 0, "generators": 0},
                ),
                "since": value,
            }
        history = model.get("_delta_history", {})
        deltas = history.get("deltas", []) if isinstance(history, Mapping) else []
        if isinstance(value, str) and isinstance(deltas, list):
            chain: list[Mapping[str, Any]] = []
            cursor = current
            while cursor != value:
                candidate = next(
                    (
                        item
                        for item in reversed(deltas)
                        if isinstance(item, Mapping) and item.get("current_content_identity") == cursor
                    ),
                    None,
                )
                if candidate is None:
                    chain = []
                    break
                chain.append(candidate)
                cursor = candidate.get("previous_content_identity")
                if not isinstance(cursor, str) or len(chain) > len(deltas):
                    chain = []
                    break
            if chain and cursor == value:
                chain.reverse()
                counts = {
                    "deltas": len(chain),
                    "capabilities": sum(
                        len(item.get("changed_capabilities", []))
                        for item in chain
                    ),
                    "alternates": sum(
                        len(item.get("shadow_state_transitions", []))
                        for item in chain
                    ),
                    "generators": 0,
                }
                return {
                    "projection": _projection_envelope(
                        model,
                        mode="delta",
                        layers=["identity", "delta"],
                        counts=counts,
                        complete=True,
                    ),
                    "since": value,
                    "delta": {"from": value, "to": current, "mode": "delta", "chain": chain},
                }
        full = _projection_envelope(
            model,
            mode="full",
            layers=["identity", "architecture", "contract", "delta", "implementation", "evidence"],
            counts=_projection_metrics(capabilities, generators),
            complete=True,
            limitations=["the requested architecture identity is outside the retained delta chain; current projection is returned"],
        )
        return {
            "projection": full,
            "since": value,
            "delta": {"from": value, "to": current, "mode": "full"},
            "architecture": {
                "capabilities": [_compact_capability(item) for item in capabilities],
                "generators": generators,
            },
        }

    raise ValueError(f"unsupported architecture query: {query}")


def validate_architecture_model(
    value: Mapping[str, Any], *, workspace_root: str | Path | None = None
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    schema_identity = value.get("schema_identity")
    if value.get("schema_version") != MODEL_SCHEMA_VERSION:
        errors.append("schema_version must be commons.mncs.architecture-model/1")
    if schema_identity != ARCHITECTURE_SCHEMA_IDENTITY:
        errors.append("schema_identity must be commons.mncs.architecture-model/1")
    content_identity = value.get("content_identity")
    expected_identity = architecture_content_identity(value)
    if not isinstance(content_identity, str) or not content_identity:
        errors.append("content_identity is required")
    elif content_identity != expected_identity:
        errors.append(
            f"content_identity does not match deterministic model content: {content_identity} != {expected_identity}"
        )
    policy = value.get("policy")
    if not isinstance(policy, Mapping):
        errors.append("policy must be an object")
        policy = {}
    capabilities = value.get("capabilities")
    if not isinstance(capabilities, list):
        errors.append("capabilities must be an array")
        capabilities = []
    generators = value.get("generators")
    if not isinstance(generators, list):
        errors.append("generators must be an array")
        generators = []
    delta_history = value.get("delta_history")
    if not isinstance(delta_history, Mapping):
        errors.append("delta_history must be an object")
        delta_history = {}
    else:
        if delta_history.get("schema_version") != DELTA_HISTORY_SCHEMA_VERSION:
            errors.append(
                "delta_history.schema_version must be commons.mncs.architecture-delta-history/1"
            )
        if not isinstance(delta_history.get("path"), str) or not delta_history.get("path"):
            errors.append("delta_history.path is required")
        retention = delta_history.get("retention")
        if not isinstance(retention, int) or retention < 1:
            errors.append("delta_history.retention must be a positive integer")
    attached_history = value.get("_delta_history")
    if attached_history is not None:
        if not isinstance(attached_history, Mapping):
            errors.append("attached architecture delta history must be an object")
        else:
            if attached_history.get("schema_version") != DELTA_HISTORY_SCHEMA_VERSION:
                errors.append("architecture delta history has an unexpected schema")
            history_deltas = attached_history.get("deltas")
            retention = delta_history.get("retention", 0)
            if not isinstance(history_deltas, list):
                errors.append("architecture delta history deltas must be an array")
            elif isinstance(retention, int) and len(history_deltas) > retention:
                errors.append("architecture delta history exceeds its retention bound")
            history_identity = attached_history.get("history_identity")
            history_payload = {
                key: item for key, item in attached_history.items() if key != "history_identity"
            }
            expected_history_identity = _CONTENT_PREFIX + hashlib.sha256(
                _canonical_bytes(history_payload)
            ).hexdigest()
            if history_identity != expected_history_identity:
                errors.append("architecture delta history identity is not content-addressed")
            if isinstance(history_deltas, list):
                for delta_index, delta in enumerate(history_deltas):
                    if not isinstance(delta, Mapping):
                        errors.append(f"architecture delta history deltas[{delta_index}] must be an object")
                        continue
                    for field in ("previous_content_identity", "current_content_identity"):
                        if not isinstance(delta.get(field), str) or not delta.get(field):
                            errors.append(f"architecture delta history deltas[{delta_index}] requires {field}")
                    for field in (
                        "changed_capabilities",
                        "added_contracts",
                        "removed_contracts",
                        "ownership_changes",
                        "shadow_state_transitions",
                    ):
                        if not isinstance(delta.get(field), list):
                            errors.append(
                                f"architecture delta history deltas[{delta_index}].{field} must be an array"
                            )
    seen: dict[str, str] = {}
    owners: dict[str, set[str]] = {}
    canonical_claims: dict[tuple[object, object], str] = {}
    checked_roots: set[str] = set()
    workspace = Path(workspace_root).resolve() if isinstance(workspace_root, (str, Path)) else None

    for index, capability in enumerate(capabilities):
        prefix = f"capabilities[{index}]"
        if not isinstance(capability, Mapping):
            errors.append(f"{prefix} must be an object")
            continue
        identity = capability.get("id")
        owner = capability.get("owner")
        canonical = capability.get("canonical")
        versioning = capability.get("versioning")
        if not isinstance(identity, str) or not identity:
            errors.append(f"{prefix}.id is required")
            continue
        if identity in seen:
            errors.append(f"capability ownership collision: {identity} appears more than once")
        seen[identity] = str(owner)
        if not isinstance(owner, str) or owner not in CANONICAL_FAMILY:
            errors.append(f"{prefix}.owner is not in the Commons family registry: {owner!r}")
        else:
            owners.setdefault(identity, set()).add(owner)
        if owner == "mncs-language" and identity.startswith(_APPLICATION_PREFIXES):
            errors.append(f"application policy is declared language-owned: {identity}")
        if not isinstance(canonical, Mapping) or not isinstance(canonical.get("path"), str):
            errors.append(f"{prefix}.canonical.path is required")
            canonical = {}
        repository = canonical.get("repository")
        canonical_path = canonical.get("path")
        canonical_key = (repository, canonical_path)
        if canonical_key in canonical_claims and canonical_path:
            errors.append(
                f"two capabilities claim the same canonical implementation: {canonical_claims[canonical_key]} and {identity}"
            )
        else:
            canonical_claims[canonical_key] = identity
        if not isinstance(versioning, Mapping):
            errors.append(f"{prefix}.versioning is required")
            versioning = {}
        mode = versioning.get("implementation")
        compatibility = versioning.get("compatibility")
        if mode not in {"in_place", "contract_identity"}:
            errors.append(f"{prefix}.versioning.implementation must be in_place or contract_identity")
        if not isinstance(compatibility, Mapping):
            errors.append(f"{prefix}.versioning.compatibility is required")
            compatibility = {}
        compatibility_required = bool(compatibility.get("required"))
        kind = canonical.get("kind")
        if (
            isinstance(canonical_path, str)
            and _VERSIONED.search(canonical_path)
            and kind != "wire-contract"
            and mode == "in_place"
        ):
            errors.append(f"chronological canonical implementation path: {identity} -> {canonical_path}")
        if workspace is not None and isinstance(repository, str) and isinstance(canonical_path, str):
            root = _repository_root(workspace, repository)
            if root is None:
                if repository not in checked_roots:
                    warnings.append(f"repository root unavailable; canonical path not checked: {repository}")
                    checked_roots.add(repository)
            elif not (root / canonical_path).exists():
                errors.append(f"canonical path does not exist: {repository}:{canonical_path}")
        alternates = capability.get("active_alternates", [])
        if not isinstance(alternates, list):
            errors.append(f"{prefix}.active_alternates must be an array")
            alternates = []
        active_implementations = [
            alternate
            for alternate in alternates
            if isinstance(alternate, Mapping)
            and alternate.get("role") not in {"adapter", "differential_oracle", "shadow"}
        ]
        if active_implementations and mode == "in_place" and not compatibility_required:
            errors.append(f"multiple active implementations without compatibility requirement: {identity}")
        alternate_paths: set[str] = set()
        for alternate in alternates:
            if not isinstance(alternate, Mapping):
                errors.append(f"{prefix}.active_alternates contains a non-object")
                continue
            path = alternate.get("path")
            role = alternate.get("role")
            if isinstance(path, str):
                alternate_paths.add(path)
                if (
                    _VERSIONED.search(path)
                    and kind != "wire-contract"
                    and not compatibility_required
                    and role not in {"adapter", "differential_oracle", "shadow"}
                ):
                    errors.append(f"chronological alternate without compatibility: {identity} -> {path}")
                if workspace is not None and isinstance(repository, str):
                    root = _repository_root(workspace, repository)
                    if root is None:
                        if repository not in checked_roots:
                            warnings.append(f"repository root unavailable; alternate paths not checked: {repository}")
                            checked_roots.add(repository)
                    elif not (root / path).exists():
                        errors.append(f"active alternate path does not exist: {repository}:{path}")
            if role not in _ROLES:
                errors.append(f"{prefix}.active_alternates role is not classified: {role!r}")
        shadow = capability.get("shadow")
        if shadow is not None:
            if not isinstance(shadow, Mapping):
                errors.append(f"{prefix}.shadow must be an object or null")
            else:
                required = (
                    "supersedes",
                    "parity_event",
                    "retirement_condition",
                    "survivor",
                    "retirement_direction",
                    "parity_state",
                    "retirement_state",
                )
                missing = [
                    field
                    for field in required
                    if not isinstance(shadow.get(field), str) or not shadow.get(field)
                ]
                if missing:
                    errors.append(f"{prefix}.shadow is missing convergence fields: {', '.join(missing)}")
                shadow_path = shadow.get("path")
                direction = shadow.get("retirement_direction")
                parity_state = shadow.get("parity_state")
                retirement_state = shadow.get("retirement_state")
                survivor = shadow.get("survivor")
                if isinstance(shadow_path, str) and shadow_path not in alternate_paths:
                    errors.append(f"{prefix}.shadow.path is not listed as an active alternate: {shadow_path}")
                if direction not in _RETIREMENT_DIRECTIONS:
                    errors.append(f"{prefix}.shadow.retirement_direction is invalid: {direction!r}")
                if parity_state not in {"pending", "achieved"}:
                    errors.append(f"{prefix}.shadow.parity_state is invalid: {parity_state!r}")
                if retirement_state not in _RETIREMENT_STATES:
                    errors.append(f"{prefix}.shadow.retirement_state is invalid: {retirement_state!r}")
                if direction == "canonical_survivor" and not _same_declared_path(survivor, canonical_path):
                    errors.append(
                        f"{prefix}.shadow survivor contradicts canonical_survivor direction: {survivor!r} != {canonical_path!r}"
                    )
                if direction == "shadow_survivor" and not _same_declared_path(survivor, shadow_path):
                    errors.append(
                        f"{prefix}.shadow survivor contradicts shadow_survivor direction: {survivor!r} != {shadow_path!r}"
                    )
                if parity_state == "achieved" and retirement_state != "retired":
                    errors.append(f"{prefix}.shadow parity is achieved but retirement_state is not retired")
                if parity_state == "pending" and retirement_state == "retired":
                    errors.append(f"{prefix}.shadow is retired before its parity event is achieved")
        evidence = capability.get("evidence")
        if evidence is not None:
            if not isinstance(evidence, list) or not evidence:
                errors.append(f"{prefix}.evidence must be a non-empty array")
            else:
                semantic_evidence = False
                for evidence_item in evidence:
                    if not isinstance(evidence_item, Mapping) or not isinstance(evidence_item.get("path"), str):
                        errors.append(f"{prefix}.evidence entries require path and role")
                        continue
                    role = evidence_item.get("role")
                    if role in {"semantic_authority", "canonical"}:
                        semantic_evidence = True
                        if not _same_declared_path(evidence_item["path"], canonical_path):
                            errors.append(
                                f"canonical evidence does not identify the canonical implementation: {identity} -> {evidence_item['path']}"
                            )
                    if workspace is not None and isinstance(repository, str):
                        root = _repository_root(workspace, repository)
                        if root is not None and not (root / evidence_item["path"]).exists():
                            errors.append(
                                f"canonical evidence path does not exist: {repository}:{evidence_item['path']}"
                            )
                if not semantic_evidence:
                    errors.append(f"{prefix}.canonical evidence points only to adapters/oracles")

    for identity, identity_owners in owners.items():
        if len(identity_owners) > 1:
            errors.append(f"capability ownership collision: {identity} -> {sorted(identity_owners)}")
    return {
        "schema_version": MODEL_SCHEMA_VERSION,
        "schema_identity": schema_identity,
        "content_identity": content_identity,
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "capability_count": len(capabilities),
        "generator_count": len(generators),
    }
