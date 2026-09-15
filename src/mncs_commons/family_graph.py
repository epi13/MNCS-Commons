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
DECLARATION_SCHEMA = "commons.mncs.semantic-contract-declarations/v1"


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


def declaration_identity(value: Mapping[str, Any]) -> str:
    """Return the identity of one repository-owned contract declaration."""

    projection = deepcopy(dict(value))
    projection.pop("declaration_identity", None)
    projection.pop("_path", None)
    return hashlib.sha256(_canonical(projection)).hexdigest()


def validate_declaration(value: Any) -> dict[str, Any]:
    """Validate a repository-owned semantic contract declaration."""

    if not isinstance(value, Mapping) or value.get("schema_version") != DECLARATION_SCHEMA:
        raise FamilyGraphError(f"contract declaration must be {DECLARATION_SCHEMA}")
    repository_id = value.get("repository_id")
    revision = value.get("revision")
    if not isinstance(repository_id, str) or not repository_id:
        raise FamilyGraphError("contract declaration repository_id must be non-empty")
    if not isinstance(revision, str) or not revision:
        raise FamilyGraphError("contract declaration revision must be non-empty")
    normalized = dict(value)
    for kind, required in (
        ("provides", ("contract_identity", "contract_revision", "exported_identity", "evidence")),
        ("consumes", ("contract_identity", "contract_revision", "consumer_identity", "evidence")),
    ):
        entries = value.get(kind)
        if not isinstance(entries, list):
            raise FamilyGraphError(f"contract declaration {kind} must be an array")
        identities: set[str] = set()
        checked: list[dict[str, Any]] = []
        for index, raw in enumerate(entries):
            if not isinstance(raw, Mapping):
                raise FamilyGraphError(f"contract declaration {kind}[{index}] must be an object")
            entry = dict(raw)
            for field in required:
                if not isinstance(entry.get(field), str) or not entry[field]:
                    raise FamilyGraphError(f"contract declaration {kind}[{index}].{field} must be non-empty")
            identity = entry["contract_identity"]
            if identity in identities:
                raise FamilyGraphError(f"contract declaration {kind} repeats {identity}")
            identities.add(identity)
            checked.append(entry)
        normalized[kind] = checked
    return normalized


def generate_graph(
    declarations: Sequence[Mapping[str, Any]],
    repositories: Sequence[Mapping[str, str]],
    *,
    revision: str = "generated-from-repository-declarations-v1",
) -> dict[str, Any]:
    """Generate the compact family graph from producer/consumer declarations.

    The graph is an immutable routing artifact.  Its inputs remain owned by
    each repository; generation fails closed when a contract is unprovided or
    a consumer's requested revision disagrees with its producer.
    """

    checked = [validate_declaration(item) for item in declarations]
    by_id = {item["repository_id"]: item for item in checked}
    if len(by_id) != len(checked):
        raise FamilyGraphError("contract declarations must have unique repositories")
    repository_rows = [dict(item) for item in repositories]
    repository_ids = {item.get("id") for item in repository_rows}
    if repository_ids != set(by_id):
        raise FamilyGraphError("repository metadata and contract declarations must cover the same repositories")
    for item in repository_rows:
        if not all(isinstance(item.get(field), str) and item[field] for field in ("id", "repository")):
            raise FamilyGraphError("generated repository metadata requires id and repository")
        declaration = by_id[item["id"]]
        item.setdefault("revision", declaration["revision"])
        item["manifest_identity"] = declaration_identity(declaration)
        item.setdefault("declaration_path", declaration.get("_path", "family-semantic-contracts-v1.json"))

    providers: dict[str, tuple[str, dict[str, Any]]] = {}
    for declaration in checked:
        for provided in declaration["provides"]:
            identity = provided["contract_identity"]
            if identity in providers:
                raise FamilyGraphError(f"multiple producers declare {identity}")
            providers[identity] = (declaration["repository_id"], provided)

    edges: list[dict[str, Any]] = []
    for declaration in checked:
        for consumed in declaration["consumes"]:
            identity = consumed["contract_identity"]
            provider = providers.get(identity)
            if provider is None:
                raise FamilyGraphError(f"no producer declares consumed contract {identity}")
            producer_id, provided = provider
            if consumed["contract_revision"] != provided["contract_revision"]:
                raise FamilyGraphError(
                    f"consumer {declaration['repository_id']} requests {identity} revision "
                    f"{consumed['contract_revision']}, producer declares {provided['contract_revision']}"
                )
            edge = {
                "producer_repository": producer_id,
                "consumer_repository": declaration["repository_id"],
                "contract_identity": identity,
                "contract_revision": provided["contract_revision"],
                "consuming_identity": consumed["consumer_identity"],
                "provenance": f"{declaration['repository_id']}:{consumed['evidence']}",
            }
            edge["fingerprint"] = edge_fingerprint(edge)
            edges.append(edge)
    edges.sort(key=lambda item: (item["producer_repository"], item["consumer_repository"], item["contract_identity"]))
    source_declarations = [
        {
            "repository_id": item["repository_id"],
            "path": item.get("_path", "family-semantic-contracts-v1.json"),
            "identity": declaration_identity(item),
        }
        for item in sorted(checked, key=lambda value: value["repository_id"])
    ]
    graph: dict[str, Any] = {
        "schema_version": GRAPH_SCHEMA,
        "revision": revision,
        "complete": True,
        "limitations": [
            "Edges are generated from repository-owned declarations joined by Commons; they do not replace compiler semantic graph truth.",
            "Undeclared or profile-wide contracts must escalate to a wider family boundary.",
        ],
        "source": {
            "kind": "repository_contract_declarations",
            "schema_version": DECLARATION_SCHEMA,
            "declarations": source_declarations,
        },
        "repositories": sorted(repository_rows, key=lambda item: item["id"]),
        "edges": edges,
    }
    graph["graph_identity"] = graph_identity(graph)
    return validate_graph(graph)


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
