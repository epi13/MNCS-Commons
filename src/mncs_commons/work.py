"""Durable, inert work-record revisions for persistent coordination.

Work records describe requested and observed execution state.  They never grant
permission to execute the task, and no code in this module dispatches work.
"""

from __future__ import annotations

import copy
import uuid
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from .canonical import canonical_digest
from .models import Diagnostic

WORK_PROTOCOL = "commons.mncs.dev/work-record/v0alpha1"
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
    "submitted": frozenset({"accepted", "failed", "cancelled"}),
    "accepted": frozenset({"assigned", "queued", "failed", "cancelled"}),
    "assigned": frozenset({"queued", "running", "blocked", "retrying", "failed", "cancelled"}),
    "queued": frozenset({"assigned", "running", "blocked", "retrying", "failed", "cancelled"}),
    "running": frozenset(
        {"checkpointed", "blocked", "retrying", "completed", "failed", "cancelled"}
    ),
    "checkpointed": frozenset(
        {"running", "blocked", "retrying", "completed", "failed", "cancelled"}
    ),
    "blocked": frozenset(
        {"assigned", "queued", "running", "retrying", "failed", "cancelled"}
    ),
    "retrying": frozenset({"assigned", "queued", "running", "blocked", "failed", "cancelled"}),
    "completed": frozenset(),
    "failed": frozenset(),
    "cancelled": frozenset(),
}
_MAX_TEXT = 16_384
_MAX_ITEMS = 128


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
        "requestedKind",
        "submittingConsumer",
        "project",
        "repository",
        "constraints",
        "parentWorkId",
        "authorityBoundary",
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
    if state not in allowed_work_transitions(previous_state):
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
        "constraints",
        "parentWorkId",
        "fabricJobId",
        "workerId",
        "modelId",
        "attempt",
        "securitySensitivity",
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
    relationships = []
    if parent_work_id:
        relationships.append({"type": "depends_on", "target": parent_work_id})
    context: dict[str, Any] = {"project": project}
    if repository:
        context["repository"] = repository
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
        "statement": {"summary": task},
        "evidence": [],
        "dependencies": [],
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
            "requestedKind": "WorkExecution",
            "requestState": "open",
            "workProtocol": WORK_PROTOCOL,
            "workId": work_id,
            "state": "submitted",
            "submittingConsumer": submitter,
            "project": project,
            "repository": repository,
            "constraints": constraints,
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
    target_state = _text(transition.get("state"), "state", maximum=32)
    if target_state not in allowed_work_transitions(previous_state):
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
    routing = _mapping(next_details.get("routing"), "routing")
    for field in ("fabricJobId", "workerId", "modelId"):
        if field in transition:
            routing[field] = _text(transition[field], field)
    next_details["routing"] = routing
    if "attempt" in transition:
        attempt = transition["attempt"]
        if (
            isinstance(attempt, bool)
            or not isinstance(attempt, int)
            or not 0 <= attempt <= 10_000
        ):
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
            if state not in allowed_work_transitions(previous_state or ""):
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
    return {
        "workId": work_id,
        "state": previous_state,
        "currentDigest": previous_digest,
        "current": current,
        "history": history,
        "contentTrust": "UNTRUSTED",
        "executionAuthority": "none",
    }


def list_work(
    records: Iterable[Mapping[str, Any]], states: set[str] | None = None
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
    return [item for item in projected if not states or item["state"] in states]
