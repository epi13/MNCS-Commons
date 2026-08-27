"""Durable, inert work-record revisions for persistent coordination.

Work records describe requested and observed execution state.  They never grant
permission to execute the task, and no code in this module dispatches work.
"""

from __future__ import annotations

import copy
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from .canonical import canonical_digest
from .lane_policy import LANES, WorkLane, lane_policy, validate_lane_request
from .models import Diagnostic

# Stable code for repo-local hygiene scope violation.
WORK_HYGIENE_SCOPE_CODE = "WORK_HYGIENE_REPOSITORY_SCOPE_INVALID"


def _hygiene_scope_invalid(details: Mapping[str, Any]) -> bool:
    """Return True if a REPO_HYGIENE request violates repo-local scope."""

    if details.get("lane") != WorkLane.REPO_HYGIENE.value:
        return False
    # Only AVAILABLE hygiene must be repo-local; NEEDS_RECONCILIATION is the
    # fail-closed audit trail for invalid attempts.
    if details.get("coordinationState") == "NEEDS_RECONCILIATION":
        return False
    # For records without an explicit coordination state, treat missing as
    # AVAILABLE-equivalent for validation (new_work_record defaults to AVAILABLE).
    # However during construction, new_work_record will have explicit AVAILABLE.
    # So we only skip when explicitly NEEDS_RECONCILIATION; otherwise enforce.
    # Lazy import to avoid circular dependency (family_registry -> work).
    try:
        from .family_registry import canonical_project_identity as _canon
    except Exception:  # pragma: no cover - missing registry should fail closed as invalid
        return True

    # Resolve primary canonical repository
    canonical_primary = details.get("canonicalRepository")
    primary: str | None = None
    if isinstance(canonical_primary, str) and canonical_primary.strip():
        ident = _canon(canonical_primary)
        if ident is None:
            return True
        primary = ident["repository"]
    else:
        repo = details.get("repository")
        if not isinstance(repo, str) or not repo.strip():
            return True
        ident = _canon(repo)
        if ident is None:
            return True
        primary = ident["repository"]

    # Resolve affected set to canonical identities
    canonical_affected = details.get("canonicalAffectedRepositories")
    affected_set: set[str] = set()
    if isinstance(canonical_affected, list) and canonical_affected:
        for item in canonical_affected:
            if not isinstance(item, str) or not item.strip():
                return True
            ident = _canon(item)
            if ident is None:
                return True
            affected_set.add(ident["repository"])
    else:
        affected = details.get("affectedRepositories")
        if not isinstance(affected, list) or not affected:
            return True
        for item in affected:
            if not isinstance(item, str) or not item.strip():
                return True
            ident = _canon(item)
            if ident is None:
                return True
            affected_set.add(ident["repository"])

    if len(affected_set) != 1:
        return True
    if primary not in affected_set:
        return True
    return False

WORK_PROTOCOL = "commons.mncs.dev/work-record/v0alpha1"
WORK_COORDINATION_STATES = frozenset(
    {
        "AVAILABLE",
        "CLAIMED",
        "IN_PROGRESS",
        "BLOCKED",
        "VERIFYING",
        "COMPLETE",
        "ABANDONED",
        "SUPERSEDED",
        "NEEDS_RECONCILIATION",
    }
)
TERMINAL_COORDINATION_STATES = frozenset({"COMPLETE", "ABANDONED", "SUPERSEDED"})
_COORDINATION_TRANSITIONS: dict[str, frozenset[str]] = {
    "AVAILABLE": frozenset({"CLAIMED", "ABANDONED", "SUPERSEDED"}),
    "CLAIMED": frozenset({"IN_PROGRESS", "BLOCKED", "ABANDONED", "SUPERSEDED"}),
    "IN_PROGRESS": frozenset(
        {"BLOCKED", "VERIFYING", "COMPLETE", "ABANDONED", "NEEDS_RECONCILIATION"}
    ),
    "BLOCKED": frozenset({"CLAIMED", "IN_PROGRESS", "ABANDONED", "NEEDS_RECONCILIATION"}),
    "VERIFYING": frozenset({"COMPLETE", "BLOCKED", "NEEDS_RECONCILIATION"}),
    "NEEDS_RECONCILIATION": frozenset({"CLAIMED", "IN_PROGRESS", "ABANDONED"}),
    "COMPLETE": frozenset(),
    "ABANDONED": frozenset(),
    "SUPERSEDED": frozenset(),
}
WORK_STATES = frozenset(
    {
        "submitted",
        "accepted",
        "assigned",
        "queued",
        "running",
        "checkpointed",
        "blocked",
        "retrying",
        "completed",
        "failed",
        "cancelled",
    }
)
TERMINAL_WORK_STATES = frozenset({"completed", "failed", "cancelled"})
_TRANSITIONS: dict[str, frozenset[str]] = {
    "submitted": frozenset({"accepted", "assigned", "failed", "cancelled"}),
    "accepted": frozenset({"assigned", "queued", "failed", "cancelled"}),
    "assigned": frozenset({"queued", "running", "blocked", "retrying", "failed", "cancelled"}),
    "queued": frozenset({"assigned", "running", "blocked", "retrying", "failed", "cancelled"}),
    "running": frozenset(
        {"checkpointed", "blocked", "retrying", "completed", "failed", "cancelled"}
    ),
    "checkpointed": frozenset(
        {"running", "blocked", "retrying", "completed", "failed", "cancelled"}
    ),
    "blocked": frozenset({"assigned", "queued", "running", "retrying", "failed", "cancelled"}),
    "retrying": frozenset({"assigned", "queued", "running", "blocked", "failed", "cancelled"}),
    "completed": frozenset(),
    "failed": frozenset(),
    "cancelled": frozenset(),
}
_MAX_TEXT = 16_384
_MAX_ITEMS = 128
_CAPABILITY_SEPARATORS = re.compile(r"[\s_./:-]+")
_CAPABILITY_ALIASES = {
    "masked": "mask",
    "reduction": "reduce",
    "reductions": "reduce",
}


class WorkProtocolError(ValueError):
    """A stable work-protocol rejection."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _text(value: object, field: str, *, maximum: int = _MAX_TEXT) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum or "\x00" in value:
        raise WorkProtocolError("WORK_INVALID", f"{field} must be bounded non-empty text")
    return value.strip()


def _optional_text(value: object, field: str) -> str | None:
    return None if value is None else _text(value, field)


def _string_list(value: object, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > _MAX_ITEMS:
        raise WorkProtocolError("WORK_INVALID", f"{field} must be a bounded list")
    return [_text(item, f"{field}[]") for item in value]


def _mapping(value: object, field: str, *, required: bool = False) -> dict[str, Any]:
    if value is None and not required:
        return {}
    if not isinstance(value, Mapping) or len(value) > _MAX_ITEMS:
        raise WorkProtocolError("WORK_INVALID", f"{field} must be a bounded object")
    return copy.deepcopy(dict(value))


def _bounded_string_list(value: object, field: str) -> list[str]:
    return _string_list(value, field)


def _bounded_mapping_list(value: object, field: str) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > _MAX_ITEMS:
        raise WorkProtocolError("WORK_INVALID", f"{field} must be a bounded list")
    result: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping) or len(item) > _MAX_ITEMS:
            raise WorkProtocolError("WORK_INVALID", f"{field}[] must be a bounded object")
        result.append(copy.deepcopy(dict(item)))
    return result


def normalize_capability(value: object) -> str:
    """Return a conservative stable capability identity for proposal matching."""

    text = _text(value, "capability", maximum=256).lower()
    parts = [part for part in _CAPABILITY_SEPARATORS.split(text) if part]
    return ".".join(_CAPABILITY_ALIASES.get(part, part) for part in parts)


def capability_overlap(left: object, right: object) -> str:
    """Classify capability comparison without treating fuzzy text as identity."""

    left_id = normalize_capability(left)
    right_id = normalize_capability(right)
    if left_id == right_id:
        return "exact"
    if len(set(left_id.split(".")).intersection(right_id.split("."))) >= 2:
        return "ambiguous"
    return "distinct"


def _bounded_priority(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 1000:
        raise WorkProtocolError("WORK_INVALID", "priority must be an integer between 0 and 1000")
    return value


def allowed_coordination_transitions(state: str) -> frozenset[str]:
    return _COORDINATION_TRANSITIONS.get(state, frozenset())


def coordination_state(details: Mapping[str, Any]) -> str:
    explicit = details.get("coordinationState")
    if explicit in WORK_COORDINATION_STATES:
        return str(explicit)
    return {
        "submitted": "AVAILABLE",
        "accepted": "AVAILABLE",
        "assigned": "CLAIMED",
        "queued": "CLAIMED",
        "running": "IN_PROGRESS",
        "checkpointed": "VERIFYING",
        "blocked": "BLOCKED",
        "retrying": "NEEDS_RECONCILIATION",
        "completed": "COMPLETE",
        "failed": "ABANDONED",
        "cancelled": "ABANDONED",
    }.get(str(details.get("state")), "AVAILABLE")


def _actor(value: object, field: str) -> dict[str, str]:
    actor = _mapping(value, field, required=True)
    unknown = set(actor) - {"type", "id"}
    if unknown:
        raise WorkProtocolError("WORK_INVALID", f"{field} contains unexpected fields")
    return {
        "type": _text(actor.get("type"), f"{field}.type", maximum=128),
        "id": _text(actor.get("id"), f"{field}.id", maximum=1024),
    }


def allowed_work_transitions(state: str) -> frozenset[str]:
    return _TRANSITIONS.get(state, frozenset())


def validate_work_record(value: Mapping[str, Any]) -> tuple[Diagnostic, ...]:
    """Validate the self-contained portion of an opt-in durable WorkRequest."""

    if value.get("kind") != "WorkRequest":
        return ()
    details = value.get("details")
    if not isinstance(details, Mapping) or not (
        "workProtocol" in details or "workId" in details or "stateEvent" in details
    ):
        return ()
    diagnostics: list[Diagnostic] = []
    if details.get("workProtocol") != WORK_PROTOCOL:
        diagnostics.append(
            Diagnostic("WORK_PROTOCOL_UNSUPPORTED", "details.workProtocol", "unsupported protocol")
        )
    work_id = details.get("workId")
    metadata = value.get("metadata")
    record_id = metadata.get("recordId") if isinstance(metadata, Mapping) else None
    if not isinstance(work_id, str) or not work_id.startswith("work:") or len(work_id) > 256:
        diagnostics.append(Diagnostic("WORK_ID_INVALID", "details.workId", "invalid work identity"))
    elif record_id != work_id:
        diagnostics.append(
            Diagnostic("WORK_ID_MISMATCH", "metadata.recordId", "recordId must equal workId")
        )
    state = details.get("state")
    if state not in WORK_STATES:
        diagnostics.append(Diagnostic("WORK_STATE_INVALID", "details.state", "unsupported state"))
    event = details.get("stateEvent")
    if not isinstance(event, Mapping):
        diagnostics.append(
            Diagnostic("WORK_EVENT_REQUIRED", "details.stateEvent", "state event is required")
        )
    else:
        if event.get("to") != state:
            diagnostics.append(
                Diagnostic("WORK_EVENT_MISMATCH", "details.stateEvent.to", "must equal state")
            )
        actor = event.get("actor")
        if not isinstance(actor, Mapping) or not actor.get("type") or not actor.get("id"):
            diagnostics.append(
                Diagnostic("WORK_ACTOR_REQUIRED", "details.stateEvent.actor", "actor is required")
            )
        metadata = value.get("metadata")
        author = metadata.get("author") if isinstance(metadata, Mapping) else None
        if actor != author:
            diagnostics.append(
                Diagnostic(
                    "WORK_ACTOR_MISMATCH",
                    "metadata.author",
                    "revision author must equal the state-event actor",
                )
            )
    if details.get("authorityBoundary") != "record-only; execution requires external authority":
        diagnostics.append(
            Diagnostic(
                "WORK_AUTHORITY_BOUNDARY_REQUIRED",
                "details.authorityBoundary",
                "work records must deny execution authority",
            )
        )
    for field in ("objective", "requestedKind", "submittingConsumer", "project", "constraints"):
        if field not in details:
            diagnostics.append(
                Diagnostic("WORK_FIELD_REQUIRED", f"details.{field}", "work field is required")
            )
    coordination = details.get("coordinationState")
    if coordination not in WORK_COORDINATION_STATES:
        diagnostics.append(
            Diagnostic(
                "WORK_COORDINATION_STATE_INVALID",
                "details.coordinationState",
                "unsupported coordination state",
            )
        )
    if (
        coordination == "AVAILABLE"
        and details.get("proposalStatus") == "ACCEPTED"
        and details.get("lane") not in LANES
    ):
        diagnostics.append(
            Diagnostic(
                "WORK_LANE_REQUIRED",
                "details.lane",
                "claimable work must declare a lane",
            )
        )
    if "lane" in details:
        lane = details.get("lane")
        if lane not in LANES:
            diagnostics.append(
                Diagnostic("WORK_LANE_INVALID", "details.lane", "unsupported work lane")
            )
        for code, field in validate_lane_request(details):
            diagnostics.append(Diagnostic(code, field, "lane policy combination is invalid"))
        for field in (
            "affectedRepositories",
            "dependencies",
            "capabilityRequirements",
            "blockingWorkIds",
            "evidenceLinks",
            "allowedWriteScope",
            "forbiddenWriteScope",
        ):
            if field in details and (
                not isinstance(details[field], list)
                or len(details[field]) > _MAX_ITEMS
                or not all(isinstance(item, str) and item.strip() for item in details[field])
            ):
                diagnostics.append(
                    Diagnostic(
                        "WORK_FIELD_INVALID", f"details.{field}", "must be a bounded string list"
                    )
                )
        for field in ("capability", "reason", "expectedSemantics"):
            if field in details and (
                not isinstance(details[field], str)
                or not details[field].strip()
                or len(details[field]) > _MAX_TEXT
            ):
                diagnostics.append(
                    Diagnostic("WORK_FIELD_INVALID", f"details.{field}", "must be bounded text")
                )
        priority = details.get("priority")
        if isinstance(priority, bool) or not isinstance(priority, int) or not 0 <= priority <= 1000:
            diagnostics.append(
                Diagnostic(
                    "WORK_PRIORITY_INVALID",
                    "details.priority",
                    "priority must be between 0 and 1000",
                )
            )
        claim = details.get("claim")
        if claim is not None and not isinstance(claim, Mapping):
            diagnostics.append(
                Diagnostic("WORK_CLAIM_INVALID", "details.claim", "claim must be an object or null")
            )
        if coordination in {"CLAIMED", "IN_PROGRESS", "VERIFYING"} and not isinstance(
            claim, Mapping
        ):
            diagnostics.append(
                Diagnostic("WORK_CLAIM_REQUIRED", "details.claim", "active work requires a claim")
            )
        if coordination == "BLOCKED" and not details.get("blockers"):
            diagnostics.append(
                Diagnostic(
                    "WORK_BLOCKERS_REQUIRED", "details.blockers", "blocked work requires blockers"
                )
            )
        if coordination == "COMPLETE":
            result = details.get("result")
            if not isinstance(result, Mapping) or not result.get("terminalOutcome"):
                diagnostics.append(
                    Diagnostic(
                        "WORK_COMPLETION_EVIDENCE_REQUIRED",
                        "details.result",
                        "complete work requires a result",
                    )
                )
        # REPO_HYGIENE must be repo-local when it is claimable (AVAILABLE).
        # Invalid hygiene is persisted as NEEDS_RECONCILIATION for audit, so
        # only AVAILABLE hygiene is diagnosed as a violation here.
        if details.get("lane") == WorkLane.REPO_HYGIENE.value:
            if coordination == "AVAILABLE" and _hygiene_scope_invalid(details):
                diagnostics.append(
                    Diagnostic(
                        WORK_HYGIENE_SCOPE_CODE,
                        "details.affectedRepositories",
                        "REPO_HYGIENE work must be scoped to exactly one "
                        "canonical repository equal to the primary repository",
                    )
                )
    security = value.get("security")
    if not isinstance(security, Mapping) or security.get("instructionsAreUntrusted") is not True:
        diagnostics.append(
            Diagnostic(
                "WORK_TRUST_BOUNDARY_REQUIRED",
                "security.instructionsAreUntrusted",
                "work instructions must remain untrusted",
            )
        )
    return tuple(diagnostics)


def work_semantic_diagnostics(
    candidate: Mapping[str, Any], existing_same_id: Iterable[Mapping[str, Any]]
) -> tuple[Diagnostic, ...]:
    """Check immutable request data and state lineage against local history."""

    details = candidate.get("details")
    if not isinstance(details, Mapping) or details.get("workProtocol") != WORK_PROTOCOL:
        return ()
    prior = list(existing_same_id)
    if not prior:
        event = details.get("stateEvent")
        if (
            details.get("state") != "submitted"
            or not isinstance(event, Mapping)
            or event.get("from") is not None
        ):
            return (
                Diagnostic(
                    "WORK_INITIAL_STATE_INVALID",
                    "details.stateEvent",
                    "first work revision must submit from no prior state",
                ),
            )
        return ()
    latest = max(prior, key=lambda item: int(item.get("metadata", {}).get("revision", 1)))
    latest_details = latest.get("details")
    if (
        not isinstance(latest_details, Mapping)
        or latest_details.get("workProtocol") != WORK_PROTOCOL
    ):
        return (
            Diagnostic(
                "WORK_HISTORY_INVALID", "details.workProtocol", "logical identity changed protocol"
            ),
        )
    diagnostics: list[Diagnostic] = []
    for field in (
        "workId",
        "objective",
        "title",
        "summary",
        "requestedKind",
        "submittingConsumer",
        "project",
        "repository",
        "constraints",
        "lane",
        "affectedRepositories",
        "priority",
        "dependencies",
        "capabilityRequirements",
        "capability",
        "reason",
        "expectedSemantics",
        "blockingWorkIds",
        "evidenceLinks",
        "sharedCoreImpact",
        "allowedWriteScope",
        "forbiddenWriteScope",
        "createdFrom",
        "parentWorkId",
        "authorityBoundary",
        "proposalStatus",
        "proposalSource",
        "observationTimestamp",
        "findingIdentity",
        "healthStatus",
        "proposalReason",
        "deduplication",
        "canonicalRepository",
        "canonicalAffectedRepositories",
    ):
        if details.get(field) != latest_details.get(field):
            diagnostics.append(
                Diagnostic(
                    "WORK_REQUEST_MUTATED",
                    f"details.{field}",
                    "submitted work identity and request fields are immutable",
                )
            )
    previous_state = str(latest_details.get("state"))
    state = str(details.get("state"))
    event = details.get("stateEvent")
    if state != previous_state and state not in allowed_work_transitions(previous_state):
        diagnostics.append(
            Diagnostic(
                "WORK_TRANSITION_REJECTED",
                "details.state",
                f"{previous_state} -> {state} is not allowed",
            )
        )
    if not isinstance(event, Mapping) or event.get("from") != previous_state:
        diagnostics.append(
            Diagnostic(
                "WORK_EVENT_STALE",
                "details.stateEvent.from",
                "state event does not name the previous state",
            )
        )
    previous_coordination = coordination_state(latest_details)
    next_coordination = coordination_state(details)
    if (
        next_coordination != previous_coordination
        and next_coordination not in allowed_coordination_transitions(previous_coordination)
    ):
        diagnostics.append(
            Diagnostic(
                "WORK_COORDINATION_TRANSITION_REJECTED",
                "details.coordinationState",
                f"{previous_coordination} -> {next_coordination} is not allowed",
            )
        )
    return tuple(diagnostics)


def _request_state(state: str) -> str:
    if state == "completed":
        return "completed"
    if state == "failed":
        return "unable_to_complete"
    if state == "cancelled":
        return "withdrawn"
    if state == "submitted":
        return "open"
    return "claimed"


def new_work_record(request: Mapping[str, Any]) -> dict[str, Any]:
    """Construct one untrusted submitted WorkRequest from bounded input."""

    allowed = {
        "workId",
        "submittingConsumer",
        "project",
        "repository",
        "task",
        "title",
        "summary",
        "lane",
        "affectedRepositories",
        "priority",
        "dependencies",
        "capabilityRequirements",
        "capability",
        "reason",
        "expectedSemantics",
        "blockingWorkIds",
        "evidenceLinks",
        "sharedCoreImpact",
        "allowedWriteScope",
        "forbiddenWriteScope",
        "createdFrom",
        "constraints",
        "parentWorkId",
        "fabricJobId",
        "workerId",
        "modelId",
        "attempt",
        "securitySensitivity",
        "coordinationState",
        "proposalStatus",
        "proposalSource",
        "observationTimestamp",
        "findingIdentity",
        "healthStatus",
        "proposalReason",
        "deduplication",
        "attachments",
        "canonicalRepository",
        "canonicalAffectedRepositories",
    }
    if set(request) - allowed:
        raise WorkProtocolError("WORK_INVALID", "work submission contains unexpected fields")
    work_id = _optional_text(request.get("workId"), "workId") or f"work:{uuid.uuid4().hex}"
    if not work_id.startswith("work:") or len(work_id) > 256:
        raise WorkProtocolError("WORK_INVALID", "workId must start with work:")
    submitter = _actor(request.get("submittingConsumer"), "submittingConsumer")
    task = _text(request.get("task"), "task")
    project = _mapping(request.get("project"), "project", required=True)
    repository = _optional_text(request.get("repository"), "repository")
    constraints = _string_list(request.get("constraints"), "constraints")
    parent_work_id = _optional_text(request.get("parentWorkId"), "parentWorkId")
    title = _optional_text(request.get("title"), "title") or task
    summary = _optional_text(request.get("summary"), "summary") or task
    lane = request.get("lane")
    if lane is not None and lane not in LANES:
        raise WorkProtocolError("WORK_LANE_INVALID", "lane is unsupported")
    policy = lane_policy(lane) if lane is not None else None
    affected_repositories = _bounded_string_list(
        request.get("affectedRepositories", [repository] if repository else []),
        "affectedRepositories",
    )
    priority = _bounded_priority(request.get("priority", 100))
    dependencies = _bounded_string_list(request.get("dependencies"), "dependencies")
    capability_requirements = _bounded_string_list(
        request.get("capabilityRequirements"), "capabilityRequirements"
    )
    capability = _optional_text(request.get("capability"), "capability")
    reason = _optional_text(request.get("reason"), "reason")
    expected_semantics = _optional_text(request.get("expectedSemantics"), "expectedSemantics")
    blocking_work_ids = _bounded_string_list(request.get("blockingWorkIds"), "blockingWorkIds")
    evidence_links = _bounded_string_list(request.get("evidenceLinks"), "evidenceLinks")
    shared_core_impact = request.get("sharedCoreImpact", lane == WorkLane.SHARED_CORE.value)
    if not isinstance(shared_core_impact, bool):
        raise WorkProtocolError("WORK_INVALID", "sharedCoreImpact must be boolean")
    allowed_write_scope = _bounded_string_list(
        request.get("allowedWriteScope", list(policy.write) if policy else []), "allowedWriteScope"
    )
    forbidden_write_scope = _bounded_string_list(
        request.get("forbiddenWriteScope", list(policy.must_not_modify) if policy else []),
        "forbiddenWriteScope",
    )
    created_from = _bounded_string_list(request.get("createdFrom"), "createdFrom")
    coordination = request.get("coordinationState", "AVAILABLE")
    if coordination not in WORK_COORDINATION_STATES:
        raise WorkProtocolError(
            "WORK_COORDINATION_STATE_INVALID", "coordinationState is unsupported"
        )
    proposal_status = _optional_text(request.get("proposalStatus"), "proposalStatus")
    proposal_source = _optional_text(request.get("proposalSource"), "proposalSource")
    observation_timestamp_raw = _optional_text(
        request.get("observationTimestamp"), "observationTimestamp"
    )
    # Normalize observationTimestamp to UTC instant if present (reject naive)
    observation_timestamp = None
    if observation_timestamp_raw is not None:
        try:
            from datetime import datetime, timezone

            instant = datetime.fromisoformat(
                observation_timestamp_raw.strip().replace("Z", "+00:00")
            )
            if instant.tzinfo is None:
                raise WorkProtocolError(
                    "WORK_INVALID", "observationTimestamp must include timezone info"
                )
            observation_timestamp = instant.astimezone(timezone.utc).isoformat().replace(
                "+00:00", "Z"
            )
        except ValueError as error:
            raise WorkProtocolError(
                "WORK_INVALID", "observationTimestamp must be an ISO-8601 timestamp"
            ) from error
    finding_identity = _optional_text(request.get("findingIdentity"), "findingIdentity")
    health_status = _optional_text(request.get("healthStatus"), "healthStatus")
    proposal_reason = _optional_text(request.get("proposalReason"), "proposalReason")
    deduplication = _mapping(request.get("deduplication"), "deduplication")
    attachments = _bounded_mapping_list(request.get("attachments"), "attachments")
    canonical_repository = _optional_text(
        request.get("canonicalRepository"), "canonicalRepository"
    )
    canonical_affected = _bounded_string_list(
        request.get("canonicalAffectedRepositories"), "canonicalAffectedRepositories"
    )
    if lane == WorkLane.SHARED_CORE.value and not shared_core_impact:
        raise WorkProtocolError(
            "WORK_SHARED_CORE_IMPACT_REQUIRED", "SHARED_CORE work must declare impact"
        )
    if lane is not None and lane != WorkLane.SHARED_CORE.value and shared_core_impact:
        raise WorkProtocolError(
            "WORK_SAFE_LANE_SHARED_CORE", "safe-lane work cannot declare shared-core impact"
        )
    # Enforce repo-local hygiene for AVAILABLE hygiene directly.
    # NEEDS_RECONCILIATION is the fail-closed audit trail for invalid attempts.
    if lane == WorkLane.REPO_HYGIENE.value and coordination == "AVAILABLE":
        probe: dict[str, Any] = {
            "lane": lane,
            "repository": repository,
            "affectedRepositories": affected_repositories,
            "coordinationState": coordination,
        }
        if canonical_repository is not None:
            probe["canonicalRepository"] = canonical_repository
        if canonical_affected:
            probe["canonicalAffectedRepositories"] = canonical_affected
        if _hygiene_scope_invalid(probe):
            raise WorkProtocolError(
                WORK_HYGIENE_SCOPE_CODE,
                "REPO_HYGIENE work must be scoped to exactly one "
                "canonical repository equal to the primary repository",
            )
    attempt = request.get("attempt", 0)
    if isinstance(attempt, bool) or not isinstance(attempt, int) or not 0 <= attempt <= 10_000:
        raise WorkProtocolError("WORK_INVALID", "attempt must be an integer between 0 and 10000")
    sensitivity = request.get("securitySensitivity", "restricted")
    if sensitivity not in {"public", "restricted", "sensitive", "security-sensitive"}:
        raise WorkProtocolError("WORK_INVALID", "securitySensitivity is invalid")
    created = _now()
    routing = {
        key: value
        for key, field in (
            ("fabricJobId", "fabricJobId"),
            ("workerId", "workerId"),
            ("modelId", "modelId"),
        )
        if (value := _optional_text(request.get(field), field)) is not None
    }
    relationships = [{"type": "depends_on", "target": item} for item in dependencies]
    relationships.extend({"type": "derived_from", "target": item} for item in created_from)
    if parent_work_id:
        relationships.append({"type": "depends_on", "target": parent_work_id})
    context: dict[str, Any] = {"project": project}
    if repository:
        context["repository"] = repository
    lane_details: dict[str, Any] = {}
    if lane is not None:
        lane_details = {
            "lane": lane,
            "affectedRepositories": affected_repositories,
            "priority": priority,
            "dependencies": dependencies,
            "capabilityRequirements": capability_requirements,
            "blockingWorkIds": blocking_work_ids,
            "evidenceLinks": evidence_links,
            "sharedCoreImpact": shared_core_impact,
            "allowedWriteScope": allowed_write_scope,
            "forbiddenWriteScope": forbidden_write_scope,
            "createdFrom": created_from,
            "coordinationState": coordination,
            "claim": None,
            "blockers": [],
            "result": None,
            "attachments": attachments,
        }
        for key, value in (
            ("capability", capability),
            ("reason", reason),
            ("expectedSemantics", expected_semantics),
        ):
            if value is not None:
                lane_details[key] = value
    else:
        lane_details = {
            "coordinationState": coordination,
            "claim": None,
            "blockers": [],
            "result": None,
            "attachments": attachments,
        }
    for key, value in (
        ("proposalStatus", proposal_status),
        ("proposalSource", proposal_source),
        ("observationTimestamp", observation_timestamp),
        ("findingIdentity", finding_identity),
        ("healthStatus", health_status),
        ("proposalReason", proposal_reason),
    ):
        if value is not None:
            lane_details[key] = value
    if canonical_repository is not None:
        lane_details["canonicalRepository"] = canonical_repository
    if canonical_affected:
        lane_details["canonicalAffectedRepositories"] = canonical_affected
    if deduplication:
        lane_details["deduplication"] = deduplication
    return {
        "apiVersion": "commons.mncs.dev/v0alpha1",
        "kind": "WorkRequest",
        "metadata": {
            "recordId": work_id,
            "createdAt": created,
            "author": submitter,
            "revision": 1,
            "labels": ["durable-work", "untrusted"],
        },
        "subject": {"type": "project", "identity": repository or work_id},
        "scope": {
            "context": context,
            "limitations": ["record carries no execution authority", *constraints],
        },
        "statement": {"summary": title, "details": summary},
        "evidence": [],
        "dependencies": dependencies,
        "affectedContracts": [],
        "provenance": {"producer": submitter, "sourceRecords": []},
        "confidence": {
            "level": "unreported",
            "rationale": "work state is an untrusted coordination assertion",
        },
        "security": {
            "sensitivity": sensitivity,
            "executableAttachments": False,
            "instructionsAreUntrusted": True,
            "requiredExternalAuthority": True,
        },
        "lifecycle": {"initialState": "proposed", "reviewWhen": ["work state changes"]},
        "relationships": relationships,
        "details": {
            "objective": task,
            "title": title,
            "summary": summary,
            "requestedKind": "WorkExecution",
            "requestState": "open",
            "workProtocol": WORK_PROTOCOL,
            "workId": work_id,
            "state": "submitted",
            "submittingConsumer": submitter,
            "project": project,
            "repository": repository,
            "constraints": constraints,
            **lane_details,
            "parentWorkId": parent_work_id,
            "attempt": attempt,
            "routing": routing,
            "stateEvent": {"from": None, "to": "submitted", "actor": submitter},
            "authorityBoundary": "record-only; execution requires external authority",
        },
    }


def revised_work_record(
    current: Mapping[str, Any], transition: Mapping[str, Any]
) -> dict[str, Any]:
    """Create the next immutable revision after validating a state transition."""

    allowed = {
        "state",
        "actor",
        "expectedPreviousDigest",
        "reason",
        "fabricJobId",
        "workerId",
        "modelId",
        "attempt",
        "progress",
        "blockers",
        "result",
        "coordinationState",
        "claim",
        "followOnRequests",
        "attachments",
    }
    if set(transition) - allowed:
        raise WorkProtocolError("WORK_INVALID", "work transition contains unexpected fields")
    details = current.get("details")
    metadata = current.get("metadata")
    if not isinstance(details, Mapping) or not isinstance(metadata, Mapping):
        raise WorkProtocolError("WORK_INVALID", "current work record is malformed")
    previous_digest = str(current.get("contentDigest") or canonical_digest(current))
    if transition.get("expectedPreviousDigest") != previous_digest:
        raise WorkProtocolError("WORK_CONFLICT", "expectedPreviousDigest is stale or missing")
    previous_state = str(details.get("state"))
    target_state = _text(transition.get("state", previous_state), "state", maximum=32)
    if target_state not in allowed_work_transitions(previous_state) and not (
        target_state == previous_state and "attachments" in transition
    ):
        raise WorkProtocolError(
            "WORK_TRANSITION_REJECTED", f"{previous_state} -> {target_state} is not allowed"
        )
    actor = _actor(transition.get("actor"), "actor")
    candidate = copy.deepcopy(dict(current))
    candidate.pop("contentDigest", None)
    candidate["metadata"] = {
        **dict(metadata),
        "createdAt": _now(),
        "author": actor,
        "revision": int(metadata.get("revision", 1)) + 1,
        "previousDigest": previous_digest,
    }
    next_details = copy.deepcopy(dict(details))
    next_details["state"] = target_state
    next_details["requestState"] = _request_state(target_state)
    next_details["stateEvent"] = {
        "from": previous_state,
        "to": target_state,
        "actor": actor,
        **(
            {"reason": _text(transition.get("reason"), "reason")}
            if transition.get("reason") is not None
            else {}
        ),
    }
    if "coordinationState" in transition:
        next_coordination = _text(transition["coordinationState"], "coordinationState", maximum=32)
        if next_coordination not in WORK_COORDINATION_STATES:
            raise WorkProtocolError(
                "WORK_COORDINATION_STATE_INVALID", "coordinationState is unsupported"
            )
    else:
        next_coordination = {
            "submitted": "AVAILABLE",
            "accepted": "AVAILABLE",
            "assigned": "CLAIMED",
            "queued": "CLAIMED",
            "running": "IN_PROGRESS",
            "checkpointed": "VERIFYING",
            "blocked": "BLOCKED",
            "retrying": "NEEDS_RECONCILIATION",
            "completed": "COMPLETE",
            "failed": "ABANDONED",
            "cancelled": "ABANDONED",
        }.get(target_state, coordination_state(details))
    previous_coordination = coordination_state(details)
    if (
        next_coordination != previous_coordination
        and next_coordination not in allowed_coordination_transitions(previous_coordination)
    ):
        raise WorkProtocolError(
            "WORK_COORDINATION_TRANSITION_REJECTED",
            f"{previous_coordination} -> {next_coordination} is not allowed",
        )
    next_details["coordinationState"] = next_coordination
    if "claim" in transition:
        claim = transition["claim"]
        next_details["claim"] = None if claim is None else _mapping(claim, "claim", required=True)
    if "followOnRequests" in transition:
        follow_on_requests = _bounded_string_list(
            transition["followOnRequests"], "followOnRequests"
        )
        next_details["followOnRequests"] = follow_on_requests
        relationships = list(candidate.get("relationships", []))
        existing_relationships = {
            (item.get("type"), item.get("target"))
            for item in relationships
            if isinstance(item, Mapping)
        }
        relationships.extend(
            {"type": "follows_up", "target": item}
            for item in follow_on_requests
            if ("follows_up", item) not in existing_relationships
        )
        candidate["relationships"] = relationships
    if "attachments" in transition:
        next_details["attachments"] = _bounded_mapping_list(
            transition["attachments"], "attachments"
        )
    routing = _mapping(next_details.get("routing"), "routing")
    for field in ("fabricJobId", "workerId", "modelId"):
        if field in transition:
            routing[field] = _text(transition[field], field)
    next_details["routing"] = routing
    if "attempt" in transition:
        attempt = transition["attempt"]
        if isinstance(attempt, bool) or not isinstance(attempt, int) or not 0 <= attempt <= 10_000:
            raise WorkProtocolError(
                "WORK_INVALID", "attempt must be an integer between 0 and 10000"
            )
        next_details["attempt"] = attempt
    for field in ("progress", "result"):
        if field in transition:
            next_details[field] = _mapping(transition[field], field, required=True)
    if "blockers" in transition:
        next_details["blockers"] = _string_list(transition["blockers"], "blockers")
    if target_state == "blocked" and not next_details.get("blockers"):
        raise WorkProtocolError("WORK_INVALID", "blocked work requires blockers")
    if target_state in {"completed", "failed"}:
        result = next_details.get("result")
        if not isinstance(result, Mapping) or not result.get("terminalOutcome"):
            raise WorkProtocolError(
                "WORK_INVALID", f"{target_state} work requires result.terminalOutcome"
            )
    if details.get("lane") and next_coordination in {"CLAIMED", "IN_PROGRESS", "VERIFYING"}:
        if not isinstance(next_details.get("claim"), Mapping):
            raise WorkProtocolError("WORK_CLAIM_REQUIRED", "active work requires a claim")
    if next_coordination == "BLOCKED" and not next_details.get("blockers"):
        raise WorkProtocolError("WORK_INVALID", "blocked work requires blockers")
    if next_coordination == "COMPLETE" and details.get("lane"):
        result = next_details.get("result")
        if not isinstance(result, Mapping) or not (
            isinstance(result.get("evidence"), list) and result.get("evidence")
        ):
            raise WorkProtocolError(
                "WORK_COMPLETION_EVIDENCE_REQUIRED",
                "lane work completion requires non-empty result.evidence",
            )
    candidate["details"] = next_details
    return candidate


def project_work_history(records: Iterable[Mapping[str, Any]], work_id: str) -> dict[str, Any]:
    """Project ordered revisions while preserving each immutable source record."""

    selected = [
        item
        for item in records
        if isinstance(item.get("details"), Mapping)
        and item["details"].get("workProtocol") == WORK_PROTOCOL
        and item["details"].get("workId") == work_id
    ]
    if not selected:
        raise WorkProtocolError("WORK_NOT_FOUND", "work record was not found")
    selected.sort(key=lambda item: int(item.get("metadata", {}).get("revision", 0)))
    previous_digest: str | None = None
    previous_state: str | None = None
    history: list[dict[str, Any]] = []
    for expected_revision, item in enumerate(selected, 1):
        metadata = item.get("metadata", {})
        details = item.get("details", {})
        state = str(details.get("state"))
        event = details.get("stateEvent", {})
        if metadata.get("revision") != expected_revision:
            raise WorkProtocolError("WORK_HISTORY_INVALID", "work revisions are not contiguous")
        if expected_revision == 1:
            if metadata.get("previousDigest") is not None or state != "submitted":
                raise WorkProtocolError("WORK_HISTORY_INVALID", "first work revision is invalid")
        else:
            if metadata.get("previousDigest") != previous_digest:
                raise WorkProtocolError("WORK_HISTORY_INVALID", "work revision lineage is broken")
            if state != previous_state and state not in allowed_work_transitions(
                previous_state or ""
            ):
                raise WorkProtocolError("WORK_HISTORY_INVALID", "work state history is invalid")
            if not isinstance(event, Mapping) or event.get("from") != previous_state:
                raise WorkProtocolError("WORK_HISTORY_INVALID", "work state event is stale")
        digest = str(item.get("contentDigest") or canonical_digest(item))
        history.append(
            {
                "revision": expected_revision,
                "digest": digest,
                "createdAt": metadata.get("createdAt"),
                "state": state,
                "event": copy.deepcopy(event),
            }
        )
        previous_digest = digest
        previous_state = state
    current = copy.deepcopy(selected[-1])
    current_details = current.get("details", {})
    return {
        "workId": work_id,
        "state": previous_state,
        "coordinationState": coordination_state(current_details)
        if isinstance(current_details, Mapping)
        else "AVAILABLE",
        "lane": current_details.get("lane") if isinstance(current_details, Mapping) else None,
        "currentDigest": previous_digest,
        "current": current,
        "history": history,
        "contentTrust": "UNTRUSTED",
        "executionAuthority": "none",
    }


def list_work(
    records: Iterable[Mapping[str, Any]],
    states: set[str] | None = None,
    *,
    lanes: set[str] | None = None,
    coordination_states: set[str] | None = None,
) -> list[dict[str, Any]]:
    work_ids = sorted(
        {
            str(details["workId"])
            for item in records
            if isinstance((details := item.get("details")), Mapping)
            and details.get("workProtocol") == WORK_PROTOCOL
            and isinstance(details.get("workId"), str)
        }
    )
    projected = [project_work_history(records, work_id) for work_id in work_ids]
    result = [item for item in projected if not states or item["state"] in states]
    if lanes:
        result = [
            item for item in result if item["current"].get("details", {}).get("lane") in lanes
        ]
    if coordination_states:
        result = [
            item
            for item in result
            if coordination_state(item["current"].get("details", {})) in coordination_states
        ]
    return result


def next_work(
    records: Iterable[Mapping[str, Any]],
    *,
    lane: str | None = None,
    repository: str | None = None,
    capabilities: set[str] | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Return deterministic, dependency-aware AVAILABLE work opportunities."""

    if lane is not None and lane not in LANES:
        raise WorkProtocolError("WORK_LANE_INVALID", "lane is unsupported")
    all_records = list(records)
    projected = list_work(
        all_records,
        lanes={lane} if lane else None,
        coordination_states={"AVAILABLE"},
    )
    completed = {
        item["workId"] for item in list_work(all_records, coordination_states={"COMPLETE"})
    }
    # Active repositories include canonical identities for fair tie-breaking
    active_repositories: set[str] = set()
    for active_item in list_work(
        all_records,
        coordination_states={"CLAIMED", "IN_PROGRESS", "VERIFYING"},
    ):
        details = active_item["current"].get("details", {})
        for repo in details.get("affectedRepositories", []):
            if isinstance(repo, str):
                active_repositories.add(repo)
        for repo in details.get("canonicalAffectedRepositories", []):
            if isinstance(repo, str):
                active_repositories.add(repo)
        canon = details.get("canonicalRepository")
        if isinstance(canon, str):
            active_repositories.add(canon)
        # Also add aliases via canonical resolution for robustness
        try:
            from .family_registry import canonical_project_identity as _canon

            for repo in list(details.get("affectedRepositories", [])):
                if isinstance(repo, str):
                    ident = _canon(repo)
                    if ident:
                        active_repositories.add(ident["repository"])
                        active_repositories.add(ident["projectId"])
        except Exception:
            pass
    dependent_counts: dict[str, int] = {}
    for candidate in list_work(all_records):
        for dependency in candidate["current"].get("details", {}).get("dependencies", []):
            dependent_counts[str(dependency)] = dependent_counts.get(str(dependency), 0) + 1
    eligible: list[dict[str, Any]] = []
    requested_capabilities = capabilities or set()
    # Resolve repository filter via canonical identity if possible
    canonical_filter: str | None = None
    if repository:
        try:
            from .family_registry import canonical_project_identity as _canon

            ident = _canon(repository)
            canonical_filter = ident["repository"] if ident else None
        except Exception:
            canonical_filter = None
    for item in projected:
        details = item["current"].get("details", {})
        if repository:
            affected = details.get("affectedRepositories", [])
            canon_affected = details.get("canonicalAffectedRepositories", [])
            canon_repo = details.get("canonicalRepository")
            # Check direct match, canonical match, or via canonical resolution
            in_affected = repository in affected if isinstance(affected, list) else False
            in_canon_affected = False
            in_canon_repo = False
            if canonical_filter and isinstance(canon_affected, list):
                in_canon_affected = canonical_filter in canon_affected
            if canonical_filter and isinstance(canon_repo, str):
                in_canon_repo = canonical_filter == canon_repo
            # Also check if the filter's canonical matches any affected string via resolution
            if not (in_affected or in_canon_affected or in_canon_repo):
                # Fallback: try resolving affected strings to canonical
                if canonical_filter and isinstance(affected, list):
                    for val in affected:
                        if isinstance(val, str):
                            try:
                                from .family_registry import canonical_project_identity as _c2

                                ident2 = _c2(val)
                                if ident2 and ident2["repository"] == canonical_filter:
                                    in_affected = True
                                    break
                            except Exception:
                                continue
                if not in_affected:
                    continue
        required = set(details.get("capabilityRequirements", []))
        if not required.issubset(requested_capabilities):
            continue
        dependencies = set(details.get("dependencies", []))
        if details.get("parentWorkId"):
            dependencies.add(str(details["parentWorkId"]))
        if any(
            dependency.startswith("work:") and dependency not in completed
            for dependency in dependencies
        ):
            continue
        eligible.append(item)
    def _item_repos(details: dict[str, Any]) -> set[str]:
        repos: set[str] = set()
        for repo in details.get("affectedRepositories", []):
            if isinstance(repo, str):
                repos.add(repo)
        for repo in details.get("canonicalAffectedRepositories", []):
            if isinstance(repo, str):
                repos.add(repo)
        canon = details.get("canonicalRepository")
        if isinstance(canon, str):
            repos.add(canon)
        return repos

    eligible.sort(
        key=lambda item: (
            int(item["current"].get("details", {}).get("priority", 100)),
            -dependent_counts.get(item["workId"], 0),
            0
            if active_repositories.intersection(
                _item_repos(item["current"].get("details", {}))  # type: ignore[arg-type]
            )
            else -1,
            str(item["current"].get("metadata", {}).get("createdAt", "")),
            item["workId"],
        )
    )
    return eligible[: max(1, min(limit, 1000))]
