"""Deterministic filtering and scope compatibility checks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Iterable, Mapping

from .models import INSTITUTIONAL_MEMORY_KINDS


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
    institutional_memory: bool = False
    needs_review: bool = False
    now: datetime | None = None
    concept: str | None = None
    language_profile: str | None = None
    backend: str | None = None
    participant: str | None = None
    failure_classification: str | None = None
    experiment_status: str | None = None


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


def _experiment_matches(
    record: Mapping[str, Any], query: QueryFilter, failure_experiments: set[str]
) -> bool:
    experiment_filter = any(
        (
            query.concept,
            query.language_profile,
            query.backend,
            query.participant,
            query.failure_classification,
            query.experiment_status,
        )
    )
    if not experiment_filter:
        return True
    if record.get("kind") != "ConceptExperiment":
        return False
    details = record.get("details")
    if not isinstance(details, Mapping):
        return False
    if query.concept and details.get("conceptId") != query.concept:
        return False
    if query.language_profile and details.get("languageProfile") != query.language_profile:
        return False
    if query.experiment_status and details.get("experimentStatus") != query.experiment_status:
        return False
    references = [
        item
        for item in details.get("references") or []
        if isinstance(item, Mapping) and isinstance(item.get("reference"), Mapping)
    ]
    if query.backend and not any(
        item.get("relation") == "backend"
        and query.backend
        in {
            item["reference"].get("stableId"),
            item["reference"].get("recordKind"),
            (item["reference"].get("scope") or {}).get("backend"),
        }
        for item in references
    ):
        return False
    if query.participant:
        actors = [item for item in details.get("actors") or [] if isinstance(item, Mapping)]
        if not any(
            query.participant
            in {
                actor.get("model"),
                actor.get("provider"),
                actor.get("worker"),
                actor.get("route"),
                (actor.get("reference") or {}).get("stableId"),
                (actor.get("reference") or {}).get("producer"),
            }
            for actor in actors
        ):
            return False
    if query.failure_classification:
        identity = str(record.get("subject", {}).get("identity", ""))
        if identity not in failure_experiments:
            return False
    return True


def record_matches(
    record: Mapping[str, Any],
    query: QueryFilter,
    state: str | None = None,
    failure_experiments: set[str] | None = None,
) -> bool:
    if not _experiment_matches(record, query, failure_experiments or set()):
        return False
    if query.institutional_memory and record.get("kind") not in INSTITUTIONAL_MEMORY_KINDS:
        return False
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
    values = list(records)
    failure_experiments: set[str] = set()
    if query.failure_classification:
        for record in values:
            details = record.get("details")
            subject = record.get("subject")
            if (
                record.get("kind") == "FailureClassification"
                and isinstance(details, Mapping)
                and details.get("classification") == query.failure_classification
                and isinstance(subject, Mapping)
                and isinstance(subject.get("identity"), str)
            ):
                failure_experiments.add(subject["identity"])
    if query.open_work_requests:
        latest: dict[str, Mapping[str, Any]] = {}
        unrevisioned: list[Mapping[str, Any]] = []
        for record in values:
            if record.get("kind") != "WorkRequest":
                continue
            metadata = record.get("metadata")
            record_id = metadata.get("recordId") if isinstance(metadata, Mapping) else None
            revision = metadata.get("revision") if isinstance(metadata, Mapping) else None
            if not isinstance(record_id, str) or not isinstance(revision, int):
                unrevisioned.append(record)
                continue
            current = latest.get(record_id)
            current_metadata = current.get("metadata") if isinstance(current, Mapping) else None
            current_revision = (
                current_metadata.get("revision") if isinstance(current_metadata, Mapping) else None
            )
            if not isinstance(current_revision, int) or revision > current_revision:
                latest[record_id] = record
        values = [*unrevisioned, *latest.values()]
    result = [
        record
        for record in values
        if record_matches(
            record,
            query,
            states.get(str(record.get("contentDigest"))),
            failure_experiments,
        )
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


def concept_experiment_graph(
    records: Iterable[Mapping[str, Any]],
    root: str,
    *,
    max_depth: int = 3,
    max_nodes: int = 1_000,
) -> dict[str, object]:
    """Project one bounded experiment graph without interpreting producer outcomes."""

    values = tuple(records)
    candidates = [
        record
        for record in values
        if record.get("kind") == "ConceptExperiment"
        and (
            record.get("contentDigest") == root
            or record.get("metadata", {}).get("recordId") == root
            or record.get("subject", {}).get("identity") == root
        )
    ]
    if not candidates:
        raise ValueError("concept experiment was not found")
    experiment = max(
        candidates,
        key=lambda item: (
            int(item.get("metadata", {}).get("revision", 1)),
            str(item.get("metadata", {}).get("createdAt", "")),
        ),
    )
    graph = bounded_graph(
        values,
        [str(experiment.get("contentDigest"))],
        max_depth=max_depth,
        max_nodes=max_nodes,
    ).as_dict()
    details = experiment.get("details")
    direct: dict[str, list[Mapping[str, Any]]] = {}
    if isinstance(details, Mapping):
        for entry in details.get("references") or []:
            if isinstance(entry, Mapping) and isinstance(entry.get("reference"), Mapping):
                direct.setdefault(str(entry.get("relation")), []).append(entry["reference"])
        for values_for_relation in direct.values():
            values_for_relation.sort(key=lambda item: str(item.get("stableId", "")))
    graph_records = graph.get("records")
    related_records = (
        [
            record
            for record in graph_records
            if isinstance(record, Mapping)
            and record.get("contentDigest") != experiment.get("contentDigest")
        ]
        if isinstance(graph_records, list)
        else []
    )
    revisions = sorted(
        candidates,
        key=lambda item: int(item.get("metadata", {}).get("revision", 1)),
    )
    lineage = [
        item
        for item in experiment.get("relationships") or []
        if isinstance(item, Mapping)
        and item.get("type") in {"rerun_of", "predecessor", "supersedes", "derived_from"}
    ]
    return {
        "schema": "commons.mncs.dev/concept-experiment-graph/v0alpha1",
        "experiment": experiment,
        "revisions": revisions,
        "producerReferences": {key: direct[key] for key in sorted(direct)},
        "actors": list(details.get("actors") or []) if isinstance(details, Mapping) else [],
        "lineage": lineage,
        "relatedRecords": related_records,
        "edges": graph["edges"],
        "unresolved": graph["unresolved"],
        "truncated": graph["truncated"],
        "authorityBoundary": (
            "bounded graph projection only; producer-native semantics and UNKNOWN are unchanged"
        ),
    }


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


def development_lineage(
    records: Iterable[Mapping[str, Any]],
    root: str,
    *,
    max_depth: int = 3,
    max_nodes: int = 1_000,
) -> dict[str, object]:
    """Project the development lineage around one DevelopmentRecord.

    The projection reconstructs, from durable identities only: the projected
    MNCDS record, its supersession chain across DevelopmentRecord records, the
    ConceptExperiment records it derives from, and every stored record reachable
    through typed relationships.  Producer-native outcomes, including tri-state
    statuses, are preserved exactly and never reinterpreted.
    """

    values = tuple(records)
    candidates = [
        record
        for record in values
        if record.get("kind") == "DevelopmentRecord"
        and (
            record.get("contentDigest") == root
            or record.get("metadata", {}).get("recordId") == root
            or (record.get("details", {}) or {}).get("recordId") == root
        )
    ]
    if not candidates:
        raise ValueError("development record was not found")
    graph = bounded_graph(
        values,
        [str(record.get("contentDigest")) for record in candidates],
        max_depth=max_depth,
        max_nodes=max_nodes,
    ).as_dict()
    primary = candidates[0]
    details = primary.get("details") or {}
    supersession: list[dict[str, str]] = []
    development_records: list[Mapping[str, Any]] = []
    experiments: list[Mapping[str, Any]] = []
    for record in values:
        if record.get("kind") == "DevelopmentRecord":
            development_records.append(record)
            for relation in record.get("relationships", []):
                if (
                    isinstance(relation, Mapping)
                    and relation.get("type") == "supersedes"
                ):
                    supersession.append(
                        {
                            "successor": str((record.get("details", {}) or {}).get("recordId", "")),
                            "predecessor": str(relation.get("target", "")),
                        }
                    )
        elif record.get("kind") == "ConceptExperiment":
            experiments.append(record)
    supersession.sort(key=lambda item: (item["successor"], item["predecessor"]))
    graph_records = graph.get("records")
    primary_digest = primary.get("contentDigest")
    related = [
        record
        for record in (graph_records if isinstance(graph_records, list) else [])
        if isinstance(record, Mapping) and record.get("contentDigest") != primary_digest
    ]
    return {
        "schema": "commons.mncs.dev/development-lineage/v0alpha1",
        "developmentRecord": primary,
        "computedStatus": details.get("computedStatus", "UNKNOWN")
        if isinstance(details, Mapping)
        else "UNKNOWN",
        "supersession": supersession,
        "experiments": sorted(
            experiments,
            key=lambda item: str(item.get("contentDigest", "")),
        ),
        "relatedRecords": related,
        "edges": graph["edges"],
        "unresolved": graph["unresolved"],
        "truncated": graph["truncated"],
        "authorityBoundary": (
            "bounded projection only; MNCDS owns selection, release, and lifecycle "
            "meaning and producer-native UNKNOWN is unchanged"
        ),
    }
