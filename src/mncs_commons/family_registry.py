"""Canonical active-family registry and bounded coverage projection.

Atlas remains descriptive orientation. This registry is the Commons-owned
coordination view: it records who is considered by the work system and never
asserts conformance, authentication, execution, or truth.
"""

from __future__ import annotations

import copy
import json
from enum import StrEnum
from importlib import resources
from typing import Any, Iterable, Mapping
from urllib.parse import urlparse

from .lane_policy import LANES, SAFE_LANES
from .work import list_work

REGISTRY_VERSION = "commons.mncs.dev/family-registry/v0alpha1"

CANONICAL_FAMILY = {
    "mncs": "epi13/machine-native-complexity-standard",
    "mncds": "epi13/machine-native-complexity-development-specification",
    "mncs-rights-provenance": "epi13/mncs-rights-provenance",
    "mncs-language": "epi13/mncs-language",
    "mncs-language-service": "epi13/mncs-language-service",
    "mncs-validator-rs": "epi13/mncs-validator-rs",
    "mncs-forge-mcp": "epi13/mncs-forge-mcp",
    "mncs-fabric": "epi13/mncs-fabric",
    "mncs-commons": "epi13/MNCS-Commons",
    "mncs-harness": "epi13/mncs-harness",
    "mncs-control-mcp": "epi13/mncs-control-mcp",
    "mncs-atlas": "epi13/mncs-atlas",
    "mncs-reference-studies": "epi13/mncs-reference-studies",
    "ravel": "epi13/RAVEL",
    "mnel": "epi13/Machine-Native-Experimental-Learning",
    "mncs-lineage": "epi13/mncs-lineage",
    "mncs-tui": "epi13/mncs-tui",
}
SOURCE_ID_ALIASES = {
    "mncs-forge": "mncs-forge-mcp",
    "forge": "mncs-forge-mcp",
    "mncs-control": "mncs-control-mcp",
    "control": "mncs-control-mcp",
    "fabric": "mncs-fabric",
    "rights-provenance": "mncs-rights-provenance",
    "rust-validator": "mncs-validator-rs",
    "reference-studies": "mncs-reference-studies",
    "commons": "mncs-commons",
    "atlas": "mncs-atlas",
}


class CoverageState(StrEnum):
    ACTIVE_WORK = "ACTIVE_WORK"
    HEALTHY_NO_WORK = "HEALTHY_NO_WORK"
    BLOCKED = "BLOCKED"
    WAITING_SHARED_CORE = "WAITING_SHARED_CORE"
    INTENTIONALLY_INACTIVE = "INTENTIONALLY_INACTIVE"
    NEEDS_REVIEW = "NEEDS_REVIEW"


_ACTIVE = frozenset({"AVAILABLE", "CLAIMED", "IN_PROGRESS", "VERIFYING"})
_PROJECT_FIELDS = frozenset(
    {
        "id",
        "repository",
        "displayName",
        "group",
        "role",
        "status",
        "authorityClass",
        "sharedCore",
        "eligibleWorkLanes",
        "consumes",
        "orientationSource",
        "coveragePosture",
    }
)


def _load_registry() -> dict[str, Any]:
    value = json.loads(
        resources.files("mncs_commons").joinpath("data/family-registry-v0alpha1.json").read_text(
            encoding="utf-8"
        )
    )
    if not isinstance(value, dict):
        raise ValueError("family registry must be an object")
    return value


def family_registry() -> dict[str, Any]:
    """Return a defensive copy of the machine-readable Commons family view."""

    value = _load_registry()
    validate_family_registry(value)
    return copy.deepcopy(value)


def validate_family_registry(value: Mapping[str, Any]) -> None:
    projects = value.get("projects")
    if value.get("registryVersion") != REGISTRY_VERSION or not isinstance(projects, list):
        raise ValueError("family registry envelope is invalid")
    if len(projects) != len(CANONICAL_FAMILY):
        raise ValueError("family registry must contain the canonical 17 projects")
    ids: set[str] = set()
    repositories: set[str] = set()
    for project in projects:
        if not isinstance(project, Mapping) or set(project) != _PROJECT_FIELDS:
            raise ValueError("family project fields are invalid")
        project_id = project.get("id")
        repository = project.get("repository")
        lanes = project.get("eligibleWorkLanes")
        if (
            not isinstance(project_id, str)
            or project_id in ids
            or not isinstance(repository, str)
            or repository in repositories
            or not isinstance(lanes, list)
            or not set(lanes).issubset(LANES)
            or project.get("status") != "active"
            or project.get("coveragePosture") not in {state.value for state in CoverageState}
            or CANONICAL_FAMILY.get(str(project_id)) != repository
        ):
            raise ValueError("family project entry is invalid")
        ids.add(project_id)
        repositories.add(repository)
    if ids != set(CANONICAL_FAMILY):
        raise ValueError("family registry identities are not canonical")


def _aliases(project: Mapping[str, Any]) -> frozenset[str]:
    repository = str(project["repository"])
    aliases = {str(project["id"]), repository, repository.rsplit("/", 1)[-1]}
    aliases.update(alias for alias, target in SOURCE_ID_ALIASES.items() if target == project["id"])
    return frozenset(aliases)


def _repository_from_url(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    parsed = urlparse(value)
    if parsed.hostname != "github.com":
        return None
    parts = [item for item in parsed.path.strip("/").split("/") if item]
    if len(parts) != 2:
        return None
    return f"{parts[0]}/{parts[1].removesuffix('.git')}"


def validate_family_sources(
    standard: Mapping[str, Any], atlas: Mapping[str, Any]
) -> dict[str, Any]:
    """Check exact family identity across Standard and Atlas snapshots."""

    source_entries = {
        "standard": standard.get("components", [])
        if isinstance(standard, Mapping)
        else [],
        "atlas": [
            *(atlas.get("projects", []) if isinstance(atlas, Mapping) else []),
            *(atlas.get("operator_components", []) if isinstance(atlas, Mapping) else []),
        ],
    }
    sources: dict[str, Any] = {}
    overall: list[str] = []
    for source_name, entries in source_entries.items():
        if not isinstance(entries, list):
            sources[source_name] = {"valid": False, "error": "entries must be a list"}
            overall.append(source_name)
            continue
        resolved: dict[str, list[dict[str, Any]]] = {}
        issues: list[dict[str, str]] = []
        for entry in entries:
            if not isinstance(entry, Mapping):
                issues.append({"code": "INVALID_ENTRY", "value": "entry is not an object"})
                continue
            source_id = str(entry.get("id", ""))
            canonical_id = (
                source_id
                if source_id in CANONICAL_FAMILY
                else SOURCE_ID_ALIASES.get(source_id)
            )
            repository_value = entry.get("repository")
            if isinstance(repository_value, Mapping):
                repository_value = repository_value.get("url")
            repository = _repository_from_url(repository_value)
            if canonical_id is None:
                issues.append({"code": "UNRESOLVED_IDENTITY", "value": source_id})
                continue
            resolved.setdefault(canonical_id, []).append(
                {"id": source_id, "repository": repository}
            )
            expected = CANONICAL_FAMILY[canonical_id]
            if repository is None and not (
                source_name == "atlas" and canonical_id == "mncs-control-mcp"
            ):
                issues.append({"code": "REPOSITORY_URL_REQUIRED", "value": source_id})
            elif repository is not None and repository.lower() != expected.lower():
                issues.append({"code": "REPOSITORY_MISMATCH", "value": source_id})
        missing = sorted(set(CANONICAL_FAMILY) - set(resolved))
        duplicate = sorted(item for item, values in resolved.items() if len(values) > 1)
        issues.extend({"code": "MISSING_PROJECT", "value": item} for item in missing)
        issues.extend({"code": "DUPLICATE_PROJECT", "value": item} for item in duplicate)
        valid = not issues and set(resolved) == set(CANONICAL_FAMILY)
        sources[source_name] = {
            "valid": valid,
            "projectCount": len(resolved),
            "resolved": {key: value for key, value in sorted(resolved.items())},
            "issues": issues,
        }
        if not valid:
            overall.append(source_name)
    return {
        "valid": not overall,
        "sources": sources,
        "canonicalProjectCount": len(CANONICAL_FAMILY),
        "issues": overall,
        "authority": (
            "bounded drift check; Standard discovery and Atlas orientation retain their own "
            "authority boundaries"
        ),
    }


def _matching_work(item: Mapping[str, Any], project: Mapping[str, Any]) -> bool:
    details = item.get("current", {}).get("details", {})
    if not isinstance(details, Mapping):
        return False
    aliases = _aliases(project)
    if details.get("repository") in aliases:
        return True
    affected = details.get("affectedRepositories", [])
    return isinstance(affected, list) and bool(
        aliases.intersection(str(value) for value in affected)
    )


def _project_state(
    project: Mapping[str, Any],
    work: Iterable[Mapping[str, Any]],
    health: Iterable[Mapping[str, Any]] = (),
) -> str:
    work_values = list(work)
    matching = [item for item in work_values if _matching_work(item, project)]
    if any(item.get("coordinationState") in _ACTIVE for item in matching):
        return CoverageState.ACTIVE_WORK.value
    blocked = [item for item in matching if item.get("coordinationState") == "BLOCKED"]
    if blocked:
        shared_core_ids = {
            item["workId"]
            for item in work_values
            if item.get("lane") == "SHARED_CORE"
            and item.get("coordinationState") not in {"COMPLETE", "ABANDONED", "SUPERSEDED"}
        }
        if any(
            any(
                dependency in shared_core_ids
                for dependency in item.get("current", {}).get("details", {}).get(
                    "dependencies", []
                )
            )
            for item in blocked
        ):
            return CoverageState.WAITING_SHARED_CORE.value
        return CoverageState.BLOCKED.value
    if any(item.get("coordinationState") == "NEEDS_RECONCILIATION" for item in matching):
        return CoverageState.NEEDS_REVIEW.value
    latest_health = [
        record
        for record in health
        if record.get("details", {}).get("healthRepository") in _aliases(project)
    ]
    if latest_health:
        latest_health.sort(
            key=lambda item: str(item.get("details", {}).get("observedAt", ""))
        )
        outcome = latest_health[-1].get("details", {}).get("outcome")
        if outcome == "PASS":
            return CoverageState.HEALTHY_NO_WORK.value
        if outcome == "UNKNOWN":
            return CoverageState.NEEDS_REVIEW.value
    posture = str(project["coveragePosture"])
    return (
        posture
        if posture != CoverageState.ACTIVE_WORK.value
        else CoverageState.NEEDS_REVIEW.value
    )


def family_coverage(records: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Project bounded current work coverage for every registered project."""

    registry = family_registry()
    record_values = list(records)
    work = list_work(record_values)
    health = [
        record
        for record in record_values
        if record.get("kind") == "Observation"
        and record.get("details", {}).get("observationType") == "family-health"
    ]
    projects: list[dict[str, Any]] = []
    for project in registry["projects"]:
        matching = [item for item in work if _matching_work(item, project)]
        state = _project_state(project, work, health)
        projects.append(
            {
                "projectId": project["id"],
                "repository": project["repository"],
                "state": state,
                "eligibleWorkLanes": list(project["eligibleWorkLanes"]),
                "work": [
                    {
                        "workId": item["workId"],
                        "lane": item["lane"],
                        "coordinationState": item["coordinationState"],
                    }
                    for item in matching
                ],
                "considered": True,
            }
        )
    lane_views: list[dict[str, Any]] = []
    for lane in sorted(SAFE_LANES | {"SHARED_CORE"}):
        eligible = [item for item in projects if lane in item["eligibleWorkLanes"]]
        lane_work = [
            work_item
            for project in eligible
            for work_item in project["work"]
            if work_item["lane"] == lane
        ]
        states = [item["state"] for item in eligible]
        lane_views.append(
            {
                "lane": lane,
                "eligible": len(eligible),
                "represented": len(eligible),
                "activeWork": sum(state == CoverageState.ACTIVE_WORK.value for state in states),
                "blocked": sum(state == CoverageState.BLOCKED.value for state in states),
                "waitingSharedCore": sum(
                    state == CoverageState.WAITING_SHARED_CORE.value for state in states
                ),
                "healthyNoWork": sum(
                    state == CoverageState.HEALTHY_NO_WORK.value for state in states
                ),
                "needsReview": sum(state == CoverageState.NEEDS_REVIEW.value for state in states),
                "workItems": len(lane_work),
                "noCurrentWork": [
                    item["projectId"]
                    for item in eligible
                    if not any(work_item["lane"] == lane for work_item in item["work"])
                ],
            }
        )
    return {
        "registryId": registry["registryId"],
        "registryVersion": registry["registryVersion"],
        "coverageMeaning": (
            "considered means represented in the coordination view, not assigned work"
        ),
        "projectCount": len(projects),
        "projects": projects,
        "lanes": lane_views,
        "atlas": {
            "role": "orientation-only",
            "source": registry["sourceReferences"][1],
            "schedulingAuthority": False,
        },
        "authority": "bounded projection of registered coverage and inert WorkRequest state",
        "contentTrust": "UNTRUSTED",
        "executionAuthority": "none",
    }


__all__ = [
    "CoverageState",
    "REGISTRY_VERSION",
    "family_coverage",
    "family_registry",
    "validate_family_registry",
    "validate_family_sources",
]
