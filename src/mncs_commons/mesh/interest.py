"""Interest projections: deterministic, machine-readable sync subscriptions.

A node interested in PTX compiler behavior must not retain every unrelated
Commons record.  An ``InterestFilter`` names the bounded subset a node wants
to receive; synchronization exchanges only matching records.

Dimensions mirror fields records actually carry:

- ``kinds`` -- record kinds (``Finding``, ``Replication``, ...).
- ``projects`` -- ``scope.context.project`` or ``scope.context.repository``.
- ``contracts`` -- ``affectedContracts`` entries.
- ``producers`` -- ``provenance.producer.id`` values.
- ``outcomes`` -- ``details.outcome`` or any ``evidence[].status``.
- ``lifecycle_states`` -- caller-supplied local lifecycle projection.
- ``relationship_types`` -- any ``relationships[].type``.
- ``labels`` -- ``metadata.labels`` entries.
- ``open_work_only`` -- only open ``WorkRequest`` records.
- ``promotion_relevant`` -- records in ``reproduced``/``verified``/``accepted``
  or carrying a replication relationship (candidates the governance layer
  may want to evaluate; Commons itself never promotes).
- ``record_ids`` -- explicit digest allowlist, matched as an OR-clause so a
  node can always request named identities (missing/wanted sets, relay
  location answers) regardless of the conjunctive dimensions above.

An empty filter matches everything: the default is a full mirror, and every
restriction is explicit.  Unknown mapping keys are rejected (a subscription
is executable local policy, not inert foreign data), while record-side
unknown vocabulary simply fails its dimension.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .errors import MeshError

INTEREST_VERSION = "commons.mncs.dev/interest/v0alpha1"

MAX_DIMENSION_ENTRIES = 64
MAX_DIMENSION_STRING = 256
MAX_RECORD_IDS = 1024

_PROMOTION_STATES = frozenset({"reproduced", "verified", "accepted"})
_REPLICATION_RELATIONS = frozenset({"replicates", "failed_to_replicate", "verifies"})


def _bounded_tuple(value: Any, name: str, maximum: int) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise MeshError("INVALID_INTEREST", f"{name} must be a list of strings")
    items = tuple(value)
    if len(items) > maximum:
        raise MeshError("INVALID_INTEREST", f"{name} exceeds {maximum} entries")
    for item in items:
        if not isinstance(item, str) or not item.strip() or len(item) > MAX_DIMENSION_STRING:
            raise MeshError("INVALID_INTEREST", f"{name} entries must be bounded strings")
    return tuple(sorted(set(items)))


@dataclass(frozen=True, slots=True)
class InterestFilter:
    """A deterministic subscription over Commons record metadata."""

    kinds: tuple[str, ...] = ()
    projects: tuple[str, ...] = ()
    contracts: tuple[str, ...] = ()
    producers: tuple[str, ...] = ()
    outcomes: tuple[str, ...] = ()
    lifecycle_states: tuple[str, ...] = ()
    relationship_types: tuple[str, ...] = ()
    labels: tuple[str, ...] = ()
    record_ids: tuple[str, ...] = ()
    open_work_only: bool = False
    promotion_relevant: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "interestVersion": INTEREST_VERSION,
            "kinds": list(self.kinds),
            "projects": list(self.projects),
            "contracts": list(self.contracts),
            "producers": list(self.producers),
            "outcomes": list(self.outcomes),
            "lifecycleStates": list(self.lifecycle_states),
            "relationshipTypes": list(self.relationship_types),
            "labels": list(self.labels),
            "recordIds": list(self.record_ids),
            "openWorkOnly": self.open_work_only,
            "promotionRelevant": self.promotion_relevant,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "InterestFilter":
        if not isinstance(value, Mapping):
            raise MeshError("INVALID_INTEREST", "interest filter must be an object")
        known = {
            "interestVersion",
            "kinds",
            "projects",
            "contracts",
            "producers",
            "outcomes",
            "lifecycleStates",
            "relationshipTypes",
            "labels",
            "recordIds",
            "openWorkOnly",
            "promotionRelevant",
        }
        unknown = sorted(str(key) for key in value if key not in known)
        if unknown:
            raise MeshError(
                "UNKNOWN_INTEREST_DIMENSION",
                f"unsupported interest dimensions: {','.join(unknown)}",
            )
        version = value.get("interestVersion", INTEREST_VERSION)
        if version != INTEREST_VERSION:
            raise MeshError("UNSUPPORTED_INTEREST_VERSION", f"interest {version!r} not supported")
        for flag in ("openWorkOnly", "promotionRelevant"):
            if flag in value and not isinstance(value[flag], bool):
                raise MeshError("INVALID_INTEREST", f"{flag} must be a boolean")
        return cls(
            kinds=_bounded_tuple(value.get("kinds"), "kinds", MAX_DIMENSION_ENTRIES),
            projects=_bounded_tuple(value.get("projects"), "projects", MAX_DIMENSION_ENTRIES),
            contracts=_bounded_tuple(value.get("contracts"), "contracts", MAX_DIMENSION_ENTRIES),
            producers=_bounded_tuple(value.get("producers"), "producers", MAX_DIMENSION_ENTRIES),
            outcomes=_bounded_tuple(value.get("outcomes"), "outcomes", MAX_DIMENSION_ENTRIES),
            lifecycle_states=_bounded_tuple(
                value.get("lifecycleStates"), "lifecycleStates", MAX_DIMENSION_ENTRIES
            ),
            relationship_types=_bounded_tuple(
                value.get("relationshipTypes"), "relationshipTypes", MAX_DIMENSION_ENTRIES
            ),
            labels=_bounded_tuple(value.get("labels"), "labels", MAX_DIMENSION_ENTRIES),
            record_ids=_bounded_tuple(value.get("recordIds"), "recordIds", MAX_RECORD_IDS),
            open_work_only=bool(value.get("openWorkOnly", False)),
            promotion_relevant=bool(value.get("promotionRelevant", False)),
        )

    @classmethod
    def match_all(cls) -> "InterestFilter":
        return cls()

    def is_empty(self) -> bool:
        return self == InterestFilter()


def _record_projects(record: Mapping[str, Any]) -> set[str]:
    scope = record.get("scope")
    if not isinstance(scope, Mapping):
        return set()
    context = scope.get("context")
    if not isinstance(context, Mapping):
        return set()
    projects = set()
    for key in ("project", "repository"):
        value = context.get(key)
        if isinstance(value, str) and value:
            projects.add(value)
    return projects


def _record_outcomes(record: Mapping[str, Any]) -> set[str]:
    outcomes = set()
    details = record.get("details")
    if isinstance(details, Mapping):
        outcome = details.get("outcome")
        if isinstance(outcome, str) and outcome:
            outcomes.add(outcome)
    evidence = record.get("evidence")
    if isinstance(evidence, list):
        for entry in evidence:
            if isinstance(entry, Mapping):
                status = entry.get("status")
                if isinstance(status, str) and status:
                    outcomes.add(status)
    return outcomes


def _record_relationship_types(record: Mapping[str, Any]) -> set[str]:
    relationships = record.get("relationships")
    if not isinstance(relationships, list):
        return set()
    return {
        str(item.get("type"))
        for item in relationships
        if isinstance(item, Mapping) and isinstance(item.get("type"), str)
    }


def _record_labels(record: Mapping[str, Any]) -> set[str]:
    metadata = record.get("metadata")
    if not isinstance(metadata, Mapping):
        return set()
    labels = metadata.get("labels")
    if not isinstance(labels, list):
        return set()
    return {str(item) for item in labels if isinstance(item, str)}


def _record_digest(record: Mapping[str, Any]) -> str | None:
    digest = record.get("contentDigest")
    return str(digest) if isinstance(digest, str) and digest else None


def _is_open_work(record: Mapping[str, Any]) -> bool:
    if record.get("kind") != "WorkRequest":
        return False
    details = record.get("details")
    if not isinstance(details, Mapping):
        return False
    return details.get("requestState", "open") == "open"


def _is_promotion_relevant(record: Mapping[str, Any], lifecycle_state: str | None) -> bool:
    if lifecycle_state in _PROMOTION_STATES:
        return True
    if _record_relationship_types(record) & _REPLICATION_RELATIONS:
        return True
    return False


# Discriminant tables shared with the MNCS kernel
# ``src/mncs_commons/mesh/mncs/commons/mesh/interest.mncs``.  The host
# projects open vocabulary (kind strings, outcome names, lifecycle states)
# to these closed discriminants; the kernel owns the Boolean combination
# law.  ``matches_discriminants`` is the exact Python mirror of the kernel
# entry point ``candidate_matches`` and must agree with it on every input
# (see ``tests/test_mesh_interop.py`` and the lattice corpora).
KIND_DISCRIMINANTS = {
    "Finding": 0,
    "Claim": 1,
    "Replication": 2,
    "Observation": 3,
    "Question": 4,
    "WorkRequest": 5,
}
OUTCOME_DISCRIMINANTS = {"PASS": 0, "FAIL": 1, "UNKNOWN": 2}
LIFECYCLE_DISCRIMINANTS = {
    "proposed": 0,
    "reproduced": 1,
    "verified": 2,
    "accepted": 3,
    "disputed": 4,
}


def _lifecycle_rank(state: int) -> int:
    if state == 0:
        return 1
    if state == 1:
        return 2
    if state == 2:
        return 3
    if state == 3:
        return 4
    return 0


def matches_discriminants(
    kind: int,
    outcome: int,
    state: int,
    *,
    want_kinds: tuple[bool, bool, bool, bool, bool, bool],
    want_outcomes: tuple[bool, bool, bool],
    min_rank: int,
) -> bool:
    """Python mirror of the MNCS ``candidate_matches`` entry point."""

    kind_ok = kind in (0, 1, 2, 3, 4, 5) and want_kinds[kind]
    outcome_ok = outcome in (0, 1, 2) and want_outcomes[outcome]
    return bool(kind_ok and outcome_ok and _lifecycle_rank(state) >= min_rank)


def project_to_discriminants(
    record: Mapping[str, Any], *, lifecycle_state: str | None = None
) -> tuple[int, int, int]:
    """Project a record to ``(kind, outcome, lifecycle)`` discriminants.

    Unknown vocabulary maps to the ``Other`` discriminants (6 / 9 / 5),
    which the kernel never matches: unknown names stay inert, never
    silently included.
    """

    kind = KIND_DISCRIMINANTS.get(str(record.get("kind")), 6)
    outcome = _projected_outcome_discriminant(record)
    state = LIFECYCLE_DISCRIMINANTS.get(str(lifecycle_state), 5)
    return (kind, outcome, state)


def _projected_outcome_discriminant(record: Mapping[str, Any]) -> int:
    """Strongest-asserted outcome wins (PASS > FAIL > UNKNOWN); none is 9.

    Both the Python ``matches`` path and the MNCS kernel project through
    this function so mixed-evidence records decide identically everywhere.
    """

    outcomes = _record_outcomes(record)
    if "PASS" in outcomes:
        return 0
    if "FAIL" in outcomes:
        return 1
    if "UNKNOWN" in outcomes:
        return 2
    return 9


def matches(
    record: Mapping[str, Any],
    interest: InterestFilter,
    *,
    lifecycle_state: str | None = None,
) -> bool:
    """Decide deterministically whether ``record`` falls in ``interest``."""

    digest = _record_digest(record)
    if digest is not None and digest in interest.record_ids:
        return True
    if interest.kinds and str(record.get("kind")) not in interest.kinds:
        return False
    if interest.projects and not (_record_projects(record) & set(interest.projects)):
        return False
    if interest.contracts:
        contracts = record.get("affectedContracts")
        names = (
            {str(item) for item in contracts if isinstance(item, str)}
            if isinstance(contracts, list)
            else set()
        )
        if not (names & set(interest.contracts)):
            return False
    if interest.producers:
        provenance = record.get("provenance")
        producer_id = None
        if isinstance(provenance, Mapping):
            producer = provenance.get("producer")
            if isinstance(producer, Mapping):
                producer_id = producer.get("id")
        if not isinstance(producer_id, str) or producer_id not in interest.producers:
            return False
    if interest.outcomes:
        projected = _projected_outcome_discriminant(record)
        outcome_names = ("PASS", "FAIL", "UNKNOWN")
        if projected > 2 or outcome_names[projected] not in interest.outcomes:
            return False
    if interest.lifecycle_states and lifecycle_state not in interest.lifecycle_states:
        return False
    if interest.relationship_types and not (
        _record_relationship_types(record) & set(interest.relationship_types)
    ):
        return False
    if interest.labels and not (_record_labels(record) & set(interest.labels)):
        return False
    if interest.open_work_only and not _is_open_work(record):
        return False
    if interest.promotion_relevant and not _is_promotion_relevant(record, lifecycle_state):
        return False
    return True
