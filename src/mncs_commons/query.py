"""Deterministic filtering and scope compatibility checks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Iterable, Mapping


class ScopeAssessment(StrEnum):
    COMPATIBLE = "compatible"
    INCOMPATIBLE = "incompatible"
    REVIEW_REQUIRED = "review-required"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class QueryFilter:
    kind: str | None = None
    state: str | None = None
    subject: str | None = None
    contract: str | None = None
    artifact: str | None = None
    related: str | None = None
    domain: str | None = None
    open_work_requests: bool = False
    needs_review: bool = False
    now: datetime | None = None


@dataclass(frozen=True, slots=True)
class GraphTraversal:
    records: tuple[Mapping[str, Any], ...]
    edges: tuple[Mapping[str, str], ...]
    unresolved: tuple[str, ...] = ()
    truncated: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "records": list(self.records),
            "edges": list(self.edges),
            "unresolved": list(self.unresolved),
            "truncated": self.truncated,
        }


@dataclass(frozen=True, slots=True)
class ReplicationCorrelation:
    target: str
    replications: tuple[Mapping[str, Any], ...]
    outcomes: Mapping[str, int]
    shared_dimensions: Mapping[str, Mapping[str, tuple[str, ...]]]

    def as_dict(self) -> dict[str, object]:
        return {
            "target": self.target,
            "replications": list(self.replications),
            "outcomes": dict(self.outcomes),
            "sharedDimensions": {
                dimension: {key: list(values) for key, values in groups.items()}
                for dimension, groups in self.shared_dimensions.items()
            },
        }


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def assess_scope(
    record: Mapping[str, Any], current_context: Mapping[str, Any], *, now: datetime | None = None
) -> ScopeAssessment:
    """Compare declared material context exactly; version similarity is not equivalence."""

    scope = record.get("scope")
    if not isinstance(scope, Mapping):
        return ScopeAssessment.UNKNOWN
    review_at = scope.get("reviewAt")
    review_clock_unknown = False
    if review_at:
        try:
            moment = _parse_timestamp(str(review_at))
            if now is not None and now.tzinfo is not None and moment <= now:
                return ScopeAssessment.REVIEW_REQUIRED
            review_clock_unknown = now is None or now.tzinfo is None
        except ValueError:
            return ScopeAssessment.UNKNOWN
    declared = scope.get("context")
    if not isinstance(declared, Mapping) or not declared:
        return ScopeAssessment.UNKNOWN
    compared = False
    for key, expected in declared.items():
        if key not in current_context:
            return ScopeAssessment.UNKNOWN
        compared = True
        if current_context[key] != expected:
            return ScopeAssessment.INCOMPATIBLE
    if review_clock_unknown:
        return ScopeAssessment.UNKNOWN
    return ScopeAssessment.COMPATIBLE if compared else ScopeAssessment.UNKNOWN


def review_required(record: Mapping[str, Any], *, now: datetime | None) -> bool:
    """Return a definite review result; an omitted clock is intentionally unknown."""

    review_at = record.get("scope", {}).get("reviewAt")
    if not review_at or now is None:
        return False
    try:
        return _parse_timestamp(str(review_at)) <= now
    except ValueError:
        return False


def record_matches(record: Mapping[str, Any], query: QueryFilter, state: str | None = None) -> bool:
    if query.kind and record.get("kind") != query.kind:
        return False
    if query.state and state != query.state:
        return False
    subject = record.get("subject", {})
    if query.subject and not (
        isinstance(subject, Mapping)
        and query.subject in {subject.get("identity"), subject.get("type")}
    ):
        return False
    if query.contract:
        contracts = record.get("affectedContracts", [])
        subject_contracts = subject.get("contracts", []) if isinstance(subject, Mapping) else []
        if query.contract not in contracts and query.contract not in subject_contracts:
            return False
    if query.artifact:
        artifacts = {
            item.get("id") for item in record.get("evidence", []) if isinstance(item, Mapping)
        }
        if (
            query.artifact not in artifacts
            and record.get("subject", {}).get("identity") != query.artifact
        ):
            return False
    if query.related:
        relationships = record.get("relationships", [])
        if not any(
            isinstance(item, Mapping) and item.get("target") == query.related
            for item in relationships
        ):
            return False
    if query.open_work_requests:
        details = record.get("details")
        request_state = details.get("requestState") if isinstance(details, Mapping) else None
        return record.get("kind") == "WorkRequest" and (
            request_state in {None, "open", "claimed", "responded"}
            and state in {"proposed", "reproduced", "disputed", "domain-scoped"}
        )
    return True


def records_for(
    records: Iterable[Mapping[str, Any]], query: QueryFilter, states: Mapping[str, str]
) -> list[Mapping[str, Any]]:
    result = [
        record
        for record in records
        if record_matches(record, query, states.get(str(record.get("contentDigest"))))
    ]
    return sorted(
        result,
        key=lambda item: (
            str(item.get("metadata", {}).get("createdAt", "")),
            str(item.get("contentDigest", "")),
        ),
    )


def unresolved_relationships(
    record: Mapping[str, Any], known_references: set[str]
) -> list[Mapping[str, Any]]:
    """Return unresolved typed edges without treating them as validation failures."""

    return [
        relationship
        for relationship in record.get("relationships", [])
        if isinstance(relationship, Mapping) and relationship.get("target") not in known_references
    ]


def bounded_graph(
    records: Iterable[Mapping[str, Any]],
    roots: Iterable[str],
    *,
    max_depth: int = 2,
    max_nodes: int = 1_000,
) -> GraphTraversal:
    """Traverse typed relationships in both directions with explicit bounds."""

    if max_depth < 0 or max_nodes < 1:
        raise ValueError("graph bounds must be non-negative depth and positive node count")
    values = tuple(records)
    by_ref: dict[str, Mapping[str, Any]] = {}
    for record in values:
        digest = str(record.get("contentDigest"))
        by_ref[digest] = record
        metadata = record.get("metadata")
        if isinstance(metadata, Mapping) and metadata.get("recordId"):
            by_ref[str(metadata["recordId"])] = record
    edge_rows: list[dict[str, str]] = []
    unresolved: set[str] = set()
    adjacency: dict[str, set[str]] = {}
    for record in values:
        source = str(record.get("contentDigest"))
        for relation in record.get("relationships", []):
            if not isinstance(relation, Mapping):
                continue
            target = str(relation.get("target", ""))
            edge = {"source": source, "target": target, "type": str(relation.get("type", ""))}
            edge_rows.append(edge)
            resolved = by_ref.get(target)
            if resolved is None:
                unresolved.add(target)
                continue
            target_digest = str(resolved.get("contentDigest"))
            adjacency.setdefault(source, set()).add(target_digest)
            adjacency.setdefault(target_digest, set()).add(source)
    edge_rows.sort(key=lambda item: (item["source"], item["type"], item["target"]))
    root_digests = sorted(
        {
            str(by_ref[reference].get("contentDigest"))
            for reference in roots
            if reference in by_ref
        }
    )
    queue = [(item, 0) for item in root_digests]
    selected: list[str] = []
    seen: set[str] = set()
    truncated = False
    while queue:
        node, depth = queue.pop(0)
        if node in seen:
            continue
        if len(selected) >= max_nodes:
            truncated = True
            break
        seen.add(node)
        selected.append(node)
        if depth < max_depth:
            queue.extend((item, depth + 1) for item in sorted(adjacency.get(node, set())))
    selected_set = set(selected)
    selected_edges = tuple(
        edge
        for edge in edge_rows
        if edge["source"] in selected_set
        or (edge["target"] in selected_set and edge["target"] in by_ref)
    )
    selected_records = tuple(
        sorted(
            (by_ref[node] for node in selected),
            key=lambda item: str(item.get("contentDigest", "")),
        )
    )
    return GraphTraversal(
        selected_records,
        selected_edges,
        tuple(sorted(unresolved)),
        truncated,
    )


def replication_correlation(
    records: Iterable[Mapping[str, Any]], target: str
) -> ReplicationCorrelation:
    """Summarize shared declared ancestry; never compute an independence score."""

    values = tuple(records)
    replications: list[Mapping[str, Any]] = []
    for record in values:
        if record.get("kind") != "Replication":
            continue
        details = record.get("details")
        target_record = details.get("targetRecord") if isinstance(details, Mapping) else None
        relations = record.get("relationships", [])
        linked = any(
            isinstance(item, Mapping)
            and item.get("type") in {"replicates", "failed_to_replicate"}
            and item.get("target") == target
            for item in relations
        )
        if target_record == target or linked:
            replications.append(record)
    outcomes: dict[str, int] = {}
    groups: dict[str, dict[str, list[str]]] = {}
    dimensions = (
        "modelFamily",
        "promptSource",
        "harness",
        "compiler",
        "machine",
        "provider",
        "artifactAncestry",
        "verifierImplementation",
    )
    for record in replications:
        details = record.get("details")
        outcome = (
            str(details.get("outcome", "UNKNOWN"))
            if isinstance(details, Mapping)
            else "UNKNOWN"
        )
        outcomes[outcome] = outcomes.get(outcome, 0) + 1
        identity = str(record.get("contentDigest"))
        independence = details.get("independence", {}) if isinstance(details, Mapping) else {}
        if not isinstance(independence, Mapping):
            continue
        for dimension in dimensions:
            if dimension not in independence:
                continue
            value = json_key(independence[dimension])
            groups.setdefault(dimension, {}).setdefault(value, []).append(identity)
    shared = {
        dimension: {
            key: tuple(sorted(identities))
            for key, identities in values.items()
            if len(identities) > 1
        }
        for dimension, values in groups.items()
    }
    return ReplicationCorrelation(target, tuple(replications), outcomes, shared)


def json_key(value: Any) -> str:
    """Stable display key for correlation metadata, including structured values."""

    if isinstance(value, (dict, list)):
        import json

        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return str(value)


def state_matches(state: str, query: QueryFilter, domain_states: Mapping[str, str]) -> bool:
    """Match one explicit domain or any domain without inventing a global state."""

    if not query.state:
        return True
    if query.domain:
        return state == query.state
    return query.state in domain_states.values() or state == query.state
