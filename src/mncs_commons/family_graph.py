"""Bounded family semantic-edge overlay.

The overlay is topology, not compiler truth.  Producers publish an exported
contract identity and consumers publish the semantic identity they bind.  A
planner may use it to select actual consumers without scanning every family
repository; an incomplete overlay is an explicit escalation condition.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping, Sequence


GRAPH_SCHEMA = "commons.mncs.dev/family-semantic-edges/v1"


class FamilyGraphError(ValueError):
    pass


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def edge_fingerprint(edge: Mapping[str, Any]) -> str:
    value = dict(edge)
    value.pop("fingerprint", None)
    return hashlib.sha256(_canonical(value)).hexdigest()


def graph_identity(value: Mapping[str, Any]) -> str:
    projection = deepcopy(dict(value))
    projection.pop("graph_identity", None)
    for edge in projection.get("edges", []):
        if isinstance(edge, dict):
            edge.pop("fingerprint", None)
    return hashlib.sha256(_canonical(projection)).hexdigest()


def validate_graph(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or value.get("schema_version") != GRAPH_SCHEMA:
        raise FamilyGraphError(f"family graph must be {GRAPH_SCHEMA}")
    repositories = value.get("repositories")
    if not isinstance(repositories, list) or not repositories:
        raise FamilyGraphError("family graph repositories must be non-empty")
    repository_ids: set[str] = set()
    for index, repository in enumerate(repositories):
        if not isinstance(repository, Mapping):
            raise FamilyGraphError(f"repositories[{index}] must be an object")
        identifier = repository.get("id")
        if not isinstance(identifier, str) or not identifier or identifier in repository_ids:
            raise FamilyGraphError(f"repositories[{index}].id must be unique")
        repository_ids.add(identifier)
        for field in ("repository", "revision", "manifest_identity"):
            if not isinstance(repository.get(field), str) or not repository[field]:
                raise FamilyGraphError(f"repositories[{index}].{field} must be non-empty")
    edges = value.get("edges")
    if not isinstance(edges, list):
        raise FamilyGraphError("family graph edges must be an array")
    normalized: list[dict[str, Any]] = []
    for index, raw in enumerate(edges):
        if not isinstance(raw, Mapping):
            raise FamilyGraphError(f"edges[{index}] must be an object")
        edge = dict(raw)
        for field in ("producer_repository", "consumer_repository", "contract_identity", "contract_revision", "consuming_identity", "provenance"):
            if not isinstance(edge.get(field), str) or not edge[field]:
                raise FamilyGraphError(f"edges[{index}].{field} must be non-empty")
        if edge["producer_repository"] not in repository_ids or edge["consumer_repository"] not in repository_ids:
            raise FamilyGraphError(f"edges[{index}] references an unknown repository")
        fingerprint = edge.get("fingerprint")
        if not isinstance(fingerprint, str) or fingerprint != edge_fingerprint(edge):
            raise FamilyGraphError(f"edges[{index}].fingerprint does not match the edge")
        normalized.append(edge)
    complete = value.get("complete")
    if not isinstance(complete, bool):
        raise FamilyGraphError("family graph complete must be boolean")
    limitations = value.get("limitations")
    if not isinstance(limitations, list) or not all(isinstance(item, str) and item for item in limitations):
        raise FamilyGraphError("family graph limitations must be non-empty strings")
    expected_identity = graph_identity(value)
    declared_identity = value.get("graph_identity")
    if declared_identity != expected_identity:
        raise FamilyGraphError("family graph graph_identity does not match its content")
    return {**dict(value), "repositories": list(repositories), "edges": normalized}


def load_graph(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise FamilyGraphError(f"cannot read family graph {path}: {error}") from error
    return validate_graph(value)


def consumers_for(
    graph: Mapping[str, Any],
    *,
    producer_repository: str,
    contract_identity: str | None = None,
) -> list[dict[str, Any]]:
    """Return only declared consumer edges for one producer/contract."""

    edges = [
        dict(edge)
        for edge in graph.get("edges", [])
        if isinstance(edge, Mapping)
        and edge.get("producer_repository") == producer_repository
        and (contract_identity is None or edge.get("contract_identity") == contract_identity)
    ]
    edges.sort(key=lambda edge: (str(edge["consumer_repository"]), str(edge["consuming_identity"])))
    return edges


__all__ = ["GRAPH_SCHEMA", "FamilyGraphError", "consumers_for", "edge_fingerprint", "graph_identity", "load_graph", "validate_graph"]
