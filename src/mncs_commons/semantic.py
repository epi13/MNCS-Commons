"""Store-level invariants that require knowledge of local history."""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from .models import Diagnostic, RelationType
from .work import work_semantic_diagnostics


def _identity(record: Mapping[str, Any]) -> str:
    digest = record.get("contentDigest")
    if isinstance(digest, str):
        return digest
    metadata = record.get("metadata")
    if isinstance(metadata, Mapping) and metadata.get("recordId"):
        return str(metadata["recordId"])
    return ""


def _logical_id(record: Mapping[str, Any]) -> str:
    metadata = record.get("metadata")
    if isinstance(metadata, Mapping) and metadata.get("recordId"):
        return str(metadata["recordId"])
    return _identity(record)


def _relation_edges(records: Iterable[Mapping[str, Any]]) -> dict[str, set[str]]:
    known: dict[str, str] = {}
    for record in records:
        node = _identity(record)
        known[node] = node
        known[_logical_id(record)] = node
    edges: dict[str, set[str]] = {}
    for record in records:
        source = _identity(record)
        for relation in record.get("relationships", []):
            if not isinstance(relation, Mapping) or relation.get("type") not in {
                RelationType.SUPERSEDES.value,
                RelationType.DEPENDS_ON.value,
            }:
                continue
            target = known.get(str(relation.get("target")))
            if target is not None:
                edges.setdefault(source, set()).add(target)
    return edges


def _has_cycle(edges: Mapping[str, set[str]]) -> bool:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> bool:
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        if any(visit(target) for target in edges.get(node, set())):
            return True
        visiting.remove(node)
        visited.add(node)
        return False

    return any(visit(node) for node in edges)


def record_semantic_diagnostics(
    candidate: Mapping[str, Any], existing: Iterable[Mapping[str, Any]]
) -> tuple[Diagnostic, ...]:
    """Check invariants that cannot be decided by a standalone schema validator."""

    records = tuple(existing)
    diagnostics: list[Diagnostic] = []
    candidate_identity = _identity(candidate)
    candidate_logical = _logical_id(candidate)
    existing_same_id = [item for item in records if _logical_id(item) == candidate_logical]
    if any(_identity(item) == candidate_identity for item in existing_same_id):
        return ()
    if existing_same_id:
        latest = max(
            existing_same_id,
            key=lambda item: int(item.get("metadata", {}).get("revision", 1)),
        )
        metadata = candidate.get("metadata", {})
        revision = metadata.get("revision") if isinstance(metadata, Mapping) else None
        previous = metadata.get("previousDigest") if isinstance(metadata, Mapping) else None
        expected_revision = int(latest.get("metadata", {}).get("revision", 1)) + 1
        if revision != expected_revision or previous != _identity(latest):
            diagnostics.append(
                Diagnostic(
                    "REVISION_REQUIRED",
                    "metadata",
                    "a changed logical record requires the next revision and previousDigest",
                )
            )
    diagnostics.extend(work_semantic_diagnostics(candidate, existing_same_id))

    known = {_identity(item) for item in records} | {_logical_id(item) for item in records}
    known.add(candidate_identity)
    known.add(candidate_logical)
    for index, relation in enumerate(candidate.get("relationships", [])):
        if not isinstance(relation, Mapping):
            continue
        target = str(relation.get("target", ""))
        if target in {candidate_identity, candidate_logical}:
            diagnostics.append(
                Diagnostic(
                    "SELF_RELATION",
                    f"relationships[{index}]",
                    "relation target is the record itself",
                )
            )
    if candidate.get("kind") == "Replication":
        details = candidate.get("details")
        replication_target = (
            str(details.get("targetRecord")) if isinstance(details, Mapping) else None
        )
        if replication_target in {candidate_identity, candidate_logical}:
            diagnostics.append(
                Diagnostic(
                    "SELF_REPLICATION",
                    "details.targetRecord",
                    "a replication cannot target itself",
                )
            )

    all_records = (*records, candidate)
    if _has_cycle(_relation_edges(all_records)):
        diagnostics.append(
            Diagnostic(
                "RELATION_CYCLE",
                "relationships",
                "supersedes and depends_on relationships must remain acyclic",
            )
        )
    return tuple(diagnostics)
