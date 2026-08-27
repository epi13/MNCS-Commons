"""Small, deterministic authority policies for Commons work lanes.

The policy is intentionally a bounded path/scope check, not an IAM system.  It
describes what a task may change; Harness/Fabric and the repository still own
actual authorization and execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from fnmatch import fnmatchcase
from typing import Any, Mapping


class WorkLane(StrEnum):
    DOCUMENTATION = "DOCUMENTATION"
    CONVERSION_PREP = "CONVERSION_PREP"
    VERIFICATION = "VERIFICATION"
    REPO_LOCAL = "REPO_LOCAL"
    REPO_HYGIENE = "REPO_HYGIENE"
    SHARED_CORE = "SHARED_CORE"


LANES = frozenset(item.value for item in WorkLane)
SAFE_LANES = frozenset(
    {
        WorkLane.DOCUMENTATION.value,
        WorkLane.CONVERSION_PREP.value,
        WorkLane.VERIFICATION.value,
        WorkLane.REPO_LOCAL.value,
        WorkLane.REPO_HYGIENE.value,
    }
)


@dataclass(frozen=True, slots=True)
class LanePolicy:
    lane: str
    read: tuple[str, ...]
    write: tuple[str, ...]
    may_publish: tuple[str, ...]
    must_not_modify: tuple[str, ...]
    exclusive: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "lane": self.lane,
            "read": list(self.read),
            "write": list(self.write),
            "mayPublish": list(self.may_publish),
            "mustNotModify": list(self.must_not_modify),
            "exclusive": self.exclusive,
        }


_SHARED_FORBIDDEN = (
    "mncs-language/compiler/**",
    "mncs-language/src/**",
    "mncs-language/stdlib/**",
    "Commons protocol/schema semantics",
    "Fabric protocol semantics",
    "Harness policy semantics",
    "family-wide semantic schemas",
    "conformance and evaluator semantics",
)
_PUBLISH = ("observations", "findings", "work_requests", "blockers", "handoffs")


def lane_policy(lane: str) -> LanePolicy:
    """Return the machine-readable policy for one lane."""

    try:
        selected = WorkLane(lane)
    except ValueError as error:
        raise ValueError(f"unsupported work lane: {lane}") from error
    write: tuple[str, ...]
    if selected is WorkLane.DOCUMENTATION:
        write = ("assigned_repo/docs/**", "assigned_repo/README*", "assigned_repo/examples/**")
    elif selected is WorkLane.CONVERSION_PREP:
        write = ("assigned_repo/**",)
    elif selected is WorkLane.VERIFICATION:
        write = ("assigned_repo/tests/**", "assigned_repo/fixtures/**", "assigned_repo/.github/**")
    elif selected is WorkLane.REPO_LOCAL:
        write = ("assigned_repo/**",)
    elif selected is WorkLane.REPO_HYGIENE:
        write = (
            "assigned_repo/.github/**",
            "assigned_repo/tests/**",
            "assigned_repo/fixtures/**",
            "assigned_repo/**",
        )
    else:
        write = ("explicitly-authorized-shared-core/**",)
    return LanePolicy(
        selected.value,
        ("mncs-family/**",),
        write,
        _PUBLISH,
        () if selected is WorkLane.SHARED_CORE else _SHARED_FORBIDDEN,
        selected is WorkLane.SHARED_CORE,
    )


def validate_lane_request(details: Mapping[str, Any]) -> list[tuple[str, str]]:
    """Return ``(diagnostic-code, field)`` pairs for lane/scope mismatches."""

    lane = details.get("lane")
    if lane is None:
        return []
    if not isinstance(lane, str) or lane not in LANES:
        return [("WORK_LANE_INVALID", "details.lane")]
    policy = lane_policy(lane)
    shared_impact = details.get("sharedCoreImpact")
    if lane == WorkLane.SHARED_CORE.value and shared_impact is not True:
        return [("WORK_SHARED_CORE_IMPACT_REQUIRED", "details.sharedCoreImpact")]
    if lane != WorkLane.SHARED_CORE.value and shared_impact is True:
        return [("WORK_SAFE_LANE_SHARED_CORE", "details.sharedCoreImpact")]
    forbidden = details.get("forbiddenWriteScope")
    if isinstance(forbidden, list) and any(
        item not in policy.must_not_modify for item in forbidden
    ):
        return [("WORK_FORBIDDEN_SCOPE_INVALID", "details.forbiddenWriteScope")]
    return []


def scope_decision(
    lane: str, path: str, *, assigned_repository: str | None = None
) -> dict[str, Any]:
    """Deterministically assess whether a path is writable under a lane."""

    policy = lane_policy(lane)
    normalized = path.strip().strip("/")
    if not normalized or "\x00" in normalized:
        return {"allowed": False, "code": "SCOPE_INVALID", "lane": lane, "path": path}
    if policy.exclusive:
        allowed = normalized.startswith("explicitly-authorized-shared-core/")
    else:
        prefix = f"{assigned_repository.strip('/')}/" if assigned_repository else "assigned_repo/"
        allowed = normalized.startswith(prefix)
        if policy.lane == WorkLane.DOCUMENTATION.value:
            allowed = allowed and any(
                fnmatchcase(normalized, pattern.replace("assigned_repo/", prefix))
                for pattern in policy.write
            )
    return {
        "allowed": allowed,
        "code": "SCOPE_ALLOWED" if allowed else "SCOPE_DENIED",
        "lane": lane,
        "path": normalized,
        "policy": policy.as_dict(),
        "authority": "policy hint; repository/Harness authorization remains external",
    }


__all__ = [
    "LANES",
    "SAFE_LANES",
    "LanePolicy",
    "WorkLane",
    "lane_policy",
    "scope_decision",
    "validate_lane_request",
]
