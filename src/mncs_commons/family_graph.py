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
VERIFICATION_MANIFEST_SCHEMA = "commons.mncs.family-verification-checks/v1"


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


def validate_verification_manifest(value: Any, *, repository_id: str) -> dict[str, Any]:
    """Validate a repository-owned, command-free verification surface map."""

    if not isinstance(value, Mapping) or value.get("schema_version") != VERIFICATION_MANIFEST_SCHEMA:
        raise FamilyGraphError(f"verification manifest must be {VERIFICATION_MANIFEST_SCHEMA}")
    if value.get("repository_id") != repository_id:
        raise FamilyGraphError("verification manifest repository_id does not match its declaration")
    checks = value.get("checks")
    if not isinstance(checks, list) or not checks:
        raise FamilyGraphError("verification manifest checks must be a non-empty array")
    identities: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for index, raw in enumerate(checks):
        if not isinstance(raw, Mapping):
            raise FamilyGraphError(f"verification manifest checks[{index}] must be an object")
        check = dict(raw)
        for field in ("identity", "contract_identity", "runner", "surface"):
            if not isinstance(check.get(field), str) or not check[field]:
                raise FamilyGraphError(
                    f"verification manifest checks[{index}].{field} must be non-empty"
                )
        if check["runner"] != "declaration":
            raise FamilyGraphError(
                f"verification manifest checks[{index}].runner must be declaration"
            )
        if check["identity"] in identities:
            raise FamilyGraphError(
                f"verification manifest repeats check identity {check['identity']}"
            )
        identities.add(check["identity"])
        normalized.append(check)
    return {**dict(value), "checks": normalized}


def bind_declaration_evidence(checkout: Path, value: Mapping[str, Any]) -> dict[str, Any]:
    """Bind declared evidence files to a declaration without changing its file.

    Repository declarations intentionally stay small and reviewable.  The
    generated graph carries the content identities of the files they name so
    a declaration cannot remain graph-fresh merely because its JSON file was
    unchanged while the represented implementation moved.
    """

    declaration = validate_declaration(value)
    manifests: dict[Path, dict[str, Any]] = {}
    evidence_digests: dict[str, dict[str, str]] = {}
    for kind in ("provides", "consumes"):
        digests: dict[str, str] = {}
        for index, entry in enumerate(declaration[kind]):
            evidence = entry["evidence"]
            evidence_path = checkout / evidence
            if Path(evidence).is_absolute() or not evidence_path.is_file():
                raise FamilyGraphError(
                    f"{checkout / 'family-semantic-contracts-v1.json'} "
                    f"{kind}[{index}] evidence does not exist: {evidence}"
                )
            digest = hashlib.sha256()
            try:
                with evidence_path.open("rb") as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(chunk)
            except OSError as error:
                raise FamilyGraphError(
                    f"cannot read declared evidence {evidence_path}: {error}"
                ) from error
            digests[evidence] = "sha256:" + digest.hexdigest()
        evidence_digests[kind] = digests
    verification_digests: dict[str, str] = {}
    for kind in ("provides", "consumes"):
        for entry in declaration[kind]:
            verification = entry.get("verification")
            if not isinstance(verification, Mapping):
                continue
            evidence = verification["evidence"]
            evidence_path = checkout / evidence
            if Path(evidence).is_absolute() or not evidence_path.is_file():
                raise FamilyGraphError(
                    f"{checkout / 'family-semantic-contracts-v1.json'} "
                    f"{kind} verification evidence does not exist: {evidence}"
                )
            manifest = manifests.get(evidence_path)
            if manifest is None:
                try:
                    manifest_value = json.loads(evidence_path.read_text(encoding="utf-8"))
                except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
                    raise FamilyGraphError(
                        f"cannot read verification manifest {evidence_path}: {error}"
                    ) from error
                manifest = validate_verification_manifest(
                    manifest_value, repository_id=declaration["repository_id"]
                )
                manifests[evidence_path] = manifest
            if not any(
                check["identity"] == verification["check_identity"]
                and check["contract_identity"] == entry["contract_identity"]
                for check in manifest["checks"]
            ):
                raise FamilyGraphError(
                    f"verification manifest {evidence_path} does not declare "
                    f"{verification['check_identity']} for {entry['contract_identity']}"
                )
            digest = hashlib.sha256()
            try:
                with evidence_path.open("rb") as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(chunk)
            except OSError as error:
                raise FamilyGraphError(
                    f"cannot read verification evidence {evidence_path}: {error}"
                ) from error
            verification_digests[evidence] = "sha256:" + digest.hexdigest()
    evidence_digests["verification"] = verification_digests
    declaration["_evidence_digests"] = evidence_digests
    return declaration


def _evidence_digest(declaration: Mapping[str, Any], kind: str, evidence: str) -> str | None:
    values = declaration.get("_evidence_digests")
    if not isinstance(values, Mapping):
        return None
    kind_values = values.get(kind)
    if not isinstance(kind_values, Mapping):
        return None
    digest = kind_values.get(evidence)
    return digest if isinstance(digest, str) else None


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
            verification = entry.get("verification")
            if verification is not None:
                if kind != "consumes" or not isinstance(verification, Mapping):
                    raise FamilyGraphError(
                        f"contract declaration {kind}[{index}].verification is invalid"
                    )
                for field in ("check_identity", "executor", "surface", "evidence"):
                    if not isinstance(verification.get(field), str) or not verification[field]:
                        raise FamilyGraphError(
                            f"contract declaration {kind}[{index}].verification.{field} "
                            "must be non-empty"
                        )
                if verification["executor"] != repository_id:
                    raise FamilyGraphError(
                        f"contract declaration {kind}[{index}].verification.executor "
                        "must match repository_id"
                    )
                entry["verification"] = dict(verification)
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
                "producer_manifest_identity": declaration_identity(by_id[producer_id]),
                "consumer_manifest_identity": declaration_identity(declaration),
                "provider_identity": provided["exported_identity"],
            }
            if isinstance(consumed.get("verification"), Mapping):
                edge["verification"] = dict(consumed["verification"])
                verification_digest = _evidence_digest(
                    declaration,
                    "verification",
                    consumed["verification"]["evidence"],
                )
                if verification_digest is not None:
                    edge["verification_evidence_sha256"] = verification_digest
            provider_digest = _evidence_digest(
                by_id[producer_id], "provides", provided["evidence"]
            )
            consumer_digest = _evidence_digest(
                declaration, "consumes", consumed["evidence"]
            )
            if provider_digest is not None:
                edge["provider_evidence_sha256"] = provider_digest
            if consumer_digest is not None:
                edge["consumer_evidence_sha256"] = consumer_digest
            edge["fingerprint"] = edge_fingerprint(edge)
            edges.append(edge)
    edges.sort(key=lambda item: (item["producer_repository"], item["consumer_repository"], item["contract_identity"]))
    source_declarations = [
        {
            "repository_id": item["repository_id"],
            "path": item.get("_path", "family-semantic-contracts-v1.json"),
            "identity": declaration_identity(item),
            "evidence_digests": item.get("_evidence_digests", {}),
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
    source = value.get("source")
    if not isinstance(source, Mapping):
        raise FamilyGraphError("family graph source must be an object")
    if source.get("kind") != "repository_contract_declarations":
        raise FamilyGraphError("family graph source kind is invalid")
    source_declarations = source.get("declarations")
    if not isinstance(source_declarations, list):
        raise FamilyGraphError("family graph source declarations must be an array")
    source_ids: set[str] = set()
    for index, declaration in enumerate(source_declarations):
        if not isinstance(declaration, Mapping):
            raise FamilyGraphError(f"source.declarations[{index}] must be an object")
        repository_id = declaration.get("repository_id")
        identity = declaration.get("identity")
        path = declaration.get("path")
        if (
            not isinstance(repository_id, str)
            or not repository_id
            or repository_id in source_ids
            or not isinstance(identity, str)
            or not identity
            or not isinstance(path, str)
            or not path
        ):
            raise FamilyGraphError(f"source.declarations[{index}] is invalid")
        source_ids.add(repository_id)
        evidence_digests = declaration.get("evidence_digests", {})
        if not isinstance(evidence_digests, Mapping):
            raise FamilyGraphError(
                f"source.declarations[{index}].evidence_digests must be an object"
            )
        for kind, values in evidence_digests.items():
            if kind not in ("provides", "consumes", "verification") or not isinstance(values, Mapping):
                raise FamilyGraphError(
                    f"source.declarations[{index}].evidence_digests is invalid"
                )
            for evidence, digest in values.items():
                if (
                    not isinstance(evidence, str)
                    or not evidence
                    or not isinstance(digest, str)
                    or not digest.startswith("sha256:")
                    or len(digest) != len("sha256:") + 64
                ):
                    raise FamilyGraphError(
                        f"source.declarations[{index}].evidence_digests is invalid"
                    )
    if source_ids != repository_ids:
        raise FamilyGraphError("family graph source declarations must cover repositories")
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
        for field in (
            "producer_manifest_identity",
            "consumer_manifest_identity",
            "provider_identity",
        ):
            if not isinstance(edge.get(field), str) or not edge[field]:
                raise FamilyGraphError(f"edges[{index}].{field} must be non-empty")
        verification = edge.get("verification")
        if verification is None or not isinstance(verification, Mapping):
            raise FamilyGraphError(f"edges[{index}].verification is required")
        for field in ("check_identity", "executor", "surface", "evidence"):
            if not isinstance(verification.get(field), str) or not verification[field]:
                raise FamilyGraphError(f"edges[{index}].verification.{field} must be non-empty")
        verification_digest = edge.get("verification_evidence_sha256")
        if (
            not isinstance(verification_digest, str)
            or not verification_digest.startswith("sha256:")
            or len(verification_digest) != len("sha256:") + 64
        ):
            raise FamilyGraphError(
                f"edges[{index}].verification_evidence_sha256 is invalid"
            )
        for field in ("provider_evidence_sha256", "consumer_evidence_sha256"):
            if field in edge and (
                not isinstance(edge[field], str)
                or not edge[field].startswith("sha256:")
                or len(edge[field]) != len("sha256:") + 64
            ):
                raise FamilyGraphError(f"edges[{index}].{field} is invalid")
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


__all__ = [
    "GRAPH_SCHEMA",
    "FamilyGraphError",
    "VERIFICATION_MANIFEST_SCHEMA",
    "bind_declaration_evidence",
    "consumers_for",
    "edge_fingerprint",
    "graph_identity",
    "load_graph",
    "validate_graph",
    "validate_verification_manifest",
]
