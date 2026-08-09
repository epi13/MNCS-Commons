"""Append-only lifecycle transition rules and deterministic projection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from .canonical import canonical_digest
from .diagnostics import ValidationReport
from .models import Diagnostic, LifecycleState

_ALLOWED: dict[str, frozenset[str]] = {
    LifecycleState.PROPOSED.value: frozenset(
        {"reproduced", "disputed", "expired", "rejected", "withdrawn"}
    ),
    LifecycleState.REPRODUCED.value: frozenset(
        {"verified", "disputed", "expired", "rejected", "withdrawn"}
    ),
    LifecycleState.VERIFIED.value: frozenset(
        {"accepted", "disputed", "superseded", "expired", "withdrawn"}
    ),
    LifecycleState.ACCEPTED.value: frozenset({"superseded", "expired", "withdrawn"}),
    LifecycleState.DISPUTED.value: frozenset(
        {"reproduced", "verified", "superseded", "expired", "rejected", "withdrawn"}
    ),
    LifecycleState.SUPERSEDED.value: frozenset(),
    LifecycleState.EXPIRED.value: frozenset(),
    LifecycleState.REJECTED.value: frozenset({"superseded", "withdrawn"}),
    LifecycleState.WITHDRAWN.value: frozenset(),
}


@dataclass(frozen=True, slots=True)
class LifecycleView:
    current_state: str
    events: tuple[str, ...]
    diagnostics: tuple[Diagnostic, ...] = ()

    @property
    def valid(self) -> bool:
        return not any(item.severity == "error" for item in self.diagnostics)

    def as_dict(self) -> dict[str, object]:
        return {
            "state": self.current_state,
            "eventDigests": list(self.events),
            "valid": self.valid,
            "diagnostics": [item.as_dict() for item in self.diagnostics],
        }


def allowed_transitions(state: str) -> frozenset[str]:
    return _ALLOWED.get(state, frozenset())


def validate_transition(current: str, target: str, event: Mapping[str, Any]) -> ValidationReport:
    diagnostics: list[Diagnostic] = []
    if current not in _ALLOWED:
        diagnostics.append(
            Diagnostic("UNKNOWN_CURRENT_STATE", "current", "current lifecycle state is unknown")
        )
    if target not in _ALLOWED:
        diagnostics.append(
            Diagnostic("UNKNOWN_TARGET_STATE", "transition.to", "target lifecycle state is unknown")
        )
    if target not in allowed_transitions(current):
        diagnostics.append(
            Diagnostic(
                "FORBIDDEN_TRANSITION", "transition", f"{current} -> {target} is not allowed"
            )
        )
    transition = event.get("transition", {})
    if not isinstance(transition, Mapping) or transition.get("from") != current:
        diagnostics.append(
            Diagnostic("STALE_TRANSITION", "transition.from", f"expected current state {current}")
        )
    authority = event.get("authority", {})
    if not isinstance(authority, Mapping) or not str(authority.get("domain", "")).strip():
        diagnostics.append(
            Diagnostic(
                "AUTHORITY_DOMAIN_REQUIRED",
                "authority.domain",
                "every transition needs an explicit domain",
            )
        )
    if target == LifecycleState.ACCEPTED.value and not str(authority.get("domain", "")).strip():
        diagnostics.append(
            Diagnostic(
                "LOCAL_ACCEPTANCE_REQUIRED",
                "authority.domain",
                "acceptance is local to a named domain",
            )
        )
    return ValidationReport(tuple(diagnostics))


def derive_lifecycle(
    record: Mapping[str, Any], events: Iterable[Mapping[str, Any]]
) -> LifecycleView:
    """Apply events in supplied append order; never guesses around a broken history."""

    state = str(record.get("lifecycle", {}).get("initialState", LifecycleState.PROPOSED.value))
    target_digest = str(record.get("contentDigest") or canonical_digest(record))
    applied: list[str] = []
    diagnostics: list[Diagnostic] = []
    seen: set[str] = set()
    for event in events:
        event_digest = str(event.get("contentDigest") or canonical_digest(event))
        if event_digest in seen:
            continue
        seen.add(event_digest)
        if event.get("target", {}).get("contentDigest") != target_digest:
            continue
        transition = event.get("transition", {})
        if not isinstance(transition, Mapping):
            diagnostics.append(
                Diagnostic("INVALID_TRANSITION", "transition", "transition must be an object")
            )
            continue
        next_state = str(transition.get("to", ""))
        report = validate_transition(state, next_state, event)
        if not report.valid:
            diagnostics.extend(report.diagnostics)
            continue
        state = next_state
        applied.append(event_digest)
    return LifecycleView(state, tuple(applied), tuple(diagnostics))
