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

from .lane_policy import LANES, SAFE_LANES
from .work import list_work

REGISTRY_VERSION = "commons.mncs.dev/family-registry/v0alpha1"


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
    if len(projects) != 17:
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
        ):
            raise ValueError("family project entry is invalid")
        ids.add(project_id)
        repositories.add(repository)


def _aliases(project: Mapping[str, Any]) -> frozenset[str]:
    repository = str(project["repository"])
    return frozenset({str(project["id"]), repository, repository.rsplit("/", 1)[-1]})


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


def _project_state(project: Mapping[str, Any], work: Iterable[Mapping[str, Any]]) -> str:
    matching = [item for item in work if _matching_work(item, project)]
    if any(item.get("coordinationState") in _ACTIVE for item in matching):
        return CoverageState.ACTIVE_WORK.value
    blocked = [item for item in matching if item.get("coordinationState") == "BLOCKED"]
    if blocked:
        if any(
            item.get("lane") == "SHARED_CORE"
            or item.get("current", {}).get("details", {}).get("sharedCoreImpact") is True
            or item.get("current", {}).get("details", {}).get("blockingWorkIds")
            for item in blocked
        ):
            return CoverageState.WAITING_SHARED_CORE.value
        return CoverageState.BLOCKED.value
    if any(item.get("coordinationState") == "NEEDS_RECONCILIATION" for item in matching):
        return CoverageState.NEEDS_REVIEW.value
    return str(project["coveragePosture"])


def family_coverage(records: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Project bounded current work coverage for every registered project."""

    registry = family_registry()
    work = list_work(records)
    projects: list[dict[str, Any]] = []
    for project in registry["projects"]:
        matching = [item for item in work if _matching_work(item, project)]
        state = _project_state(project, work)
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
]
