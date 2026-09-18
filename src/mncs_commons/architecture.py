"""Compact family architecture model and drift validator.

This is coordination metadata, not an application implementation registry.
It answers the cheap questions an autonomous worker needs before editing:
who owns a capability, which path is current, whether implementation
chronology is allowed, and how a temporary shadow retires.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping

from .family_registry import CANONICAL_FAMILY


MODEL_SCHEMA_VERSION = "commons.mncs.architecture-model/1"
_VERSIONED = re.compile(r"(?:^|/|\.)v\d+(?:\.|/|$)", re.IGNORECASE)


def load_architecture_model(root: str | Path) -> dict[str, Any]:
    path = Path(root) / "family/architecture-model-v1.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("architecture model root must be an object")
    return value


def validate_architecture_model(
    value: Mapping[str, Any], *, workspace_root: str | Path | None = None
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    if value.get("schema_version") != MODEL_SCHEMA_VERSION:
        errors.append("schema_version must be commons.mncs.architecture-model/1")
    policy = value.get("policy")
    if not isinstance(policy, Mapping):
        errors.append("policy must be an object")
        policy = {}
    capabilities = value.get("capabilities")
    if not isinstance(capabilities, list):
        errors.append("capabilities must be an array")
        capabilities = []
    seen: dict[str, str] = {}
    owners: dict[str, set[str]] = {}
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
        if not isinstance(canonical, Mapping) or not isinstance(canonical.get("path"), str):
            errors.append(f"{prefix}.canonical.path is required")
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
        if isinstance(canonical, Mapping) and isinstance(canonical.get("path"), str):
            if mode == "in_place" and _VERSIONED.search(canonical["path"]):
                errors.append(f"chronological canonical implementation path: {identity} -> {canonical['path']}")
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
        for alternate in alternates:
            if not isinstance(alternate, Mapping):
                errors.append(f"{prefix}.active_alternates contains a non-object")
                continue
            path = alternate.get("path")
            role = alternate.get("role")
            if (
                isinstance(path, str)
                and _VERSIONED.search(path)
                and not compatibility_required
                and role not in {"adapter", "differential_oracle", "shadow"}
            ):
                errors.append(f"chronological alternate without compatibility: {identity} -> {path}")
            if role not in {"adapter", "differential_oracle", "compatibility", "shadow", "implementation"}:
                errors.append(f"{prefix}.active_alternates role is not classified: {role!r}")
        shadow = capability.get("shadow")
        if shadow is not None:
            if not isinstance(shadow, Mapping):
                errors.append(f"{prefix}.shadow must be an object or null")
            else:
                required = ("supersedes", "parity_event", "retirement_condition", "survivor")
                missing = [field for field in required if not isinstance(shadow.get(field), str) or not shadow.get(field)]
                if missing:
                    errors.append(f"{prefix}.shadow is missing convergence fields: {', '.join(missing)}")
                shadow_path = shadow.get("path")
                if isinstance(shadow_path, str) and _VERSIONED.search(shadow_path):
                    warnings.append(f"chronological shadow still active: {identity} -> {shadow_path}")
        if isinstance(workspace_root, (str, Path)) and isinstance(canonical, Mapping):
            repository = canonical.get("repository")
            path = canonical.get("path")
            if repository == "mncs-commons" and isinstance(path, str):
                candidate = Path(workspace_root) / path
                if not candidate.is_file():
                    errors.append(f"canonical path does not exist: {path}")
    for identity, identity_owners in owners.items():
        if len(identity_owners) > 1:
            errors.append(f"capability ownership collision: {identity} -> {sorted(identity_owners)}")
    return {
        "schema_version": MODEL_SCHEMA_VERSION,
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "capability_count": len(capabilities),
    }
