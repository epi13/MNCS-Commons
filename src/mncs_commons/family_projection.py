"""Commons-owned bounded read projections for family-agent context.

This is the read boundary used by Language Service.  It is intentionally a
small query surface over the owning architecture and pressure services: the
caller receives validated identities, lifecycle-aware rows, and an explicit
freshness state, never Commons' storage layout or raw records.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .architecture import architecture_query, load_architecture_model, validate_architecture_model
from .canonical import canonical_json
from .pressure import PressureRegistry

SCHEMA = "commons.mncs.family-agent-projection/1"


def _identity(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value)).hexdigest()


def _registry_identity(root: Path) -> str:
    entries: list[tuple[str, str]] = []
    if root.exists():
        for path in sorted(root.rglob("*.json")):
            if "views" in path.parts:
                continue
            relative = path.relative_to(root).as_posix()
            entries.append((relative, "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()))
    return _identity(entries)


def _compact_pressure(registry: PressureRegistry, item: dict[str, Any]) -> dict[str, Any]:
    projection = registry.show(str(item["id"]))
    data = projection.data
    return {
        "id": item.get("id"),
        "title": item.get("title"),
        "target": item.get("target"),
        "domain": item.get("domain"),
        "severity": item.get("severity"),
        "status": item.get("status"),
        "verificationState": item.get("verificationState"),
        "unresolved": item.get("unresolved"),
        "affectedRepositories": item.get("affectedRepositories", []),
        "requiredBehavior": data.get("requiredBehavior", data.get("required_behavior")),
        "valid": projection.valid,
    }


def _verified_pressure_view(
    registry: PressureRegistry,
    pressure_root: Path,
) -> tuple[dict[str, Any] | None, str, str | None]:
    """Prove that the generated unresolved-language view matches the registry.

    ``PressureRegistry.validate`` owns record/event lifecycle validation, but it
    intentionally does not claim that generated views are fresh.  The bounded
    read surface therefore checks the view's schema and compares its complete
    generated payload with the owning query result before exposing rows.
    """

    view_path = pressure_root / "views" / "unresolved-language.json"
    try:
        view = json.loads(view_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None, "unavailable", "generated unresolved-language pressure view is unavailable"
    expected = registry.query(target="language", unresolved=True)
    if (
        not isinstance(view, dict)
        or view.get("schema") != "commons.mncs.dev/family-pressure-view/v1"
        or view.get("view") != "unresolved-language"
        or view.get("generatedFrom") != "commons.mncs.dev/family-pressure/v1"
        or view.get("pressures") != expected
    ):
        return None, "stale", "generated unresolved-language pressure view is stale"
    return view, "current", None


def build_family_agent_projection(
    root: str | Path,
    repository: str,
    *,
    since_architecture: str | None = None,
    max_items: int = 32,
) -> dict[str, Any]:
    """Return one bounded, freshly validated family read projection."""

    if not repository:
        raise ValueError("repository is required")
    if max_items < 1 or max_items > 64:
        raise ValueError("max_items must be between 1 and 64")
    root_path = Path(root).resolve()
    model = load_architecture_model(root_path)
    architecture_validation = validate_architecture_model(model, workspace_root=root_path)
    architecture_query_result = (
        architecture_query(model, "changes", since_architecture)
        if since_architecture is not None
        else architecture_query(model, "repository", repository)
    )
    if since_architecture is None:
        architecture_query_result["repository"] = repository
    scoped_architecture = architecture_query(model, "repository", repository)
    architecture_query_result["scoped_capabilities"] = scoped_architecture.get("capabilities", [])

    pressure_root = root_path / "pressures"
    registry = PressureRegistry(pressure_root)
    pressure_validation = registry.validate()
    pressure_rows: list[dict[str, Any]] = []
    pressure_limitations: list[str] = []
    pressure_freshness = "invalid"
    pressure_view: dict[str, Any] | None = None
    if pressure_validation.valid:
        pressure_view, pressure_freshness, view_limitation = _verified_pressure_view(
            registry, pressure_root
        )
        if view_limitation is not None:
            pressure_limitations.append(view_limitation)
        pressure_rows = [
            _compact_pressure(registry, item)
            for item in registry.query(target="language", repository=repository, unresolved=True)
        ]
        if len(pressure_rows) > max_items:
            pressure_rows = pressure_rows[:max_items]
            pressure_freshness = "truncated"
            pressure_limitations.append("pressure projection truncated at max_items")
    else:
        pressure_limitations.append("Commons pressure registry validation failed")

    architecture_projection = architecture_query_result.get("projection", {})
    architecture_limitations = list(architecture_projection.get("limitations", []))
    if len(architecture_query_result.get("capabilities", [])) > max_items:
        architecture_query_result["capabilities"] = architecture_query_result[
            "capabilities"
        ][:max_items]
        architecture_limitations.append("architecture projection truncated at max_items")
    architecture_validation_identity = _identity(architecture_validation)
    pressure_registry_identity = _registry_identity(pressure_root)
    limitations = architecture_limitations + pressure_limitations
    validated = bool(architecture_validation.get("valid")) and pressure_validation.valid
    architecture_freshness = "current" if not architecture_limitations else "truncated"
    if not validated:
        state = "invalid"
    elif architecture_freshness == "truncated" or pressure_freshness == "truncated":
        state = "truncated"
    elif pressure_freshness == "stale":
        state = "stale"
    elif pressure_freshness == "unavailable":
        state = "unavailable"
    else:
        state = "current"
    payload: dict[str, Any] = {
        "schema_version": SCHEMA,
        "status": "verified" if validated else "invalid",
        "freshness": state,
        "repository": repository,
        "architecture": {
            "schema_identity": model.get("schema_identity", model.get("schema_version")),
            "content_identity": model.get("content_identity"),
            "validation_identity": architecture_validation_identity,
            "validation_state": "verified" if architecture_validation.get("valid") else "invalid",
            "freshness": architecture_freshness,
            "query": architecture_query_result,
        },
        "pressures": {
            "registry_identity": pressure_registry_identity,
            "view_identity": _identity(pressure_view) if pressure_view is not None else None,
            "validation_state": "verified" if pressure_validation.valid else "invalid",
            "freshness": pressure_freshness,
            "rows": pressure_rows,
        },
        "limitations": limitations,
    }
    payload["projection_identity"] = _identity(payload)
    return payload


def projection_json(root: str | Path, repository: str, **kwargs: Any) -> str:
    return json.dumps(
        build_family_agent_projection(root, repository, **kwargs),
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
    )
