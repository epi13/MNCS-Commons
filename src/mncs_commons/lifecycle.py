"""Append-only lifecycle rules and trust-domain-aware projections."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from .canonical import canonical_digest
from .diagnostics import ValidationReport
from .models import Diagnostic, LifecycleState

UNREVIEWED_STATE = "unreviewed"
DOMAIN_SCOPED_STATE = "domain-scoped"

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
    """A deterministic projection, optionally from one named trust domain.

    A projection without ``domain`` is deliberately not an acceptance view.  Once
    domain-scoped events exist its state is ``domain-scoped`` and the independent
    dispositions are available in ``domain_states``.
    """

    current_state: str
    events: tuple[str, ...]
    diagnostics: tuple[Diagnostic, ...] = ()
    domain: str | None = None
    domain_states: tuple[tuple[str, str], ...] = ()

    @property
    def valid(self) -> bool:
        return not any(item.severity == "error" for item in self.diagnostics)

    @property
    def transition_state(self) -> str:
        """State to use when appending another event in this projection."""

        return self.current_state if self.domain is not None else UNREVIEWED_STATE

    def as_dict(self) -> dict[str, object]:
        return {
            "state": self.current_state,
            "domain": self.domain,
            "domainStates": {key: value for key, value in self.domain_states},
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
    return ValidationReport(tuple(diagnostics))


def _event_domain(event: Mapping[str, Any]) -> str | None:
    authority = event.get("authority")
    if not isinstance(authority, Mapping):
        return None
    value = authority.get("domain")
    return str(value).strip() or None


def _target_digest(event: Mapping[str, Any]) -> str | None:
    target = event.get("target")
    if not isinstance(target, Mapping):
        return None
    value = target.get("contentDigest")
    return str(value) if value else None


def _derive_for_domain(
    record: Mapping[str, Any], events: Iterable[Mapping[str, Any]], domain: str
) -> LifecycleView:
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
        if _target_digest(event) != target_digest or _event_domain(event) != domain:
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
    return LifecycleView(state, tuple(applied), tuple(diagnostics), domain=domain)


def derive_lifecycle(
    record: Mapping[str, Any],
    events: Iterable[Mapping[str, Any]],
    *,
    domain: str | None = None,
) -> LifecycleView:
    """Project append-only events without turning local acceptance into truth.

    ``domain="name"`` projects only that trust domain.  With no domain, all
    domain views are retained and the state is ``domain-scoped`` whenever events
    exist.  This prevents a consumer from reading one project's acceptance as a
    universal disposition.
    """

    event_list = tuple(events)
    if domain is not None:
        return _derive_for_domain(record, event_list, domain)

    target_digest = str(record.get("contentDigest") or canonical_digest(record))
    domains = sorted(
        {
            event_domain
            for event in event_list
            if _target_digest(event) == target_digest
            and (event_domain := _event_domain(event)) is not None
        }
    )
    views = tuple(_derive_for_domain(record, event_list, item) for item in domains)
    diagnostics = tuple(item for view in views for item in view.diagnostics)
    applied = tuple(item for view in views for item in view.events)
    state = LifecycleState.PROPOSED.value if not domains else DOMAIN_SCOPED_STATE
    return LifecycleView(
        state,
        applied,
        diagnostics,
        domain=None,
        domain_states=tuple((view.domain or "", view.current_state) for view in views),
    )


def domain_views(
    record: Mapping[str, Any], events: Iterable[Mapping[str, Any]]
) -> dict[str, LifecycleView]:
    """Return deterministic views for every domain represented in the history."""

    event_list = tuple(events)
    target_digest = str(record.get("contentDigest") or canonical_digest(record))
    domains = sorted(
        {
            event_domain
            for event in event_list
            if _target_digest(event) == target_digest
            and (event_domain := _event_domain(event)) is not None
        }
    )
    return {item: _derive_for_domain(record, event_list, item) for item in domains}
