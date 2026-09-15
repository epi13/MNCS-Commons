#!/usr/bin/env python3
"""Generate/check the compact family semantic graph from repo declarations."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from mncs_commons.family_graph import (
    FamilyGraphError,
    bind_declaration_evidence,
    generate_graph,
    validate_generated_provider_metadata,
    validate_declaration,
)
from mncs_commons.family_registry import family_registry


PARTICIPATION_SCHEMA = "commons.mncs.family-participation/v1"


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def load_participation(root: Path, registry: dict[str, Any]) -> tuple[list[str], list[str], list[str], dict[str, Any]]:
    path = root / "family" / "participation-v1.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise FamilyGraphError(f"cannot read family participation metadata {path}: {error}") from error
    if not isinstance(value, dict) or value.get("schema_version") != PARTICIPATION_SCHEMA:
        raise FamilyGraphError(f"family participation metadata must be {PARTICIPATION_SCHEMA}")
    if value.get("registry_id") != registry.get("registryId"):
        raise FamilyGraphError("family participation registry_id does not match the canonical registry")
    projects = value.get("projects")
    registry_projects = {
        item["id"]: item for item in registry.get("projects", []) if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    if not isinstance(projects, list):
        raise FamilyGraphError("family participation projects must be an array")
    rows: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(projects):
        if not isinstance(raw, dict):
            raise FamilyGraphError(f"family participation projects[{index}] must be an object")
        project_id = raw.get("id")
        state = raw.get("state")
        if not isinstance(project_id, str) or project_id not in registry_projects or project_id in rows:
            raise FamilyGraphError(f"family participation projects[{index}].id is invalid")
        if state not in {"participant", "explicit_nonparticipant", "pending", "unknown"}:
            raise FamilyGraphError(f"family participation projects[{index}].state is invalid")
        reason = raw.get("reason")
        if not isinstance(reason, str) or not reason:
            raise FamilyGraphError(f"family participation projects[{index}].reason is required")
        if state == "participant" and raw.get("declaration_path") != "family-semantic-contracts-v1.json":
            raise FamilyGraphError(
                f"family participation participant {project_id} must name the repository declaration path"
            )
        rows[project_id] = raw
    missing = sorted(set(registry_projects) - set(rows))
    if missing:
        raise FamilyGraphError(f"family participation does not classify registry projects: {', '.join(missing)}")
    participants = sorted(project_id for project_id, row in rows.items() if row["state"] == "participant")
    nonparticipants = sorted(
        project_id for project_id, row in rows.items() if row["state"] == "explicit_nonparticipant"
    )
    unclassified = sorted(
        project_id for project_id, row in rows.items() if row["state"] in {"pending", "unknown"}
    )
    registry_identity = hashlib.sha256(canonical_bytes(registry)).hexdigest()
    coverage = {
        "registry_identity": registry_identity,
        "registered_family_project_count": len(registry_projects),
        "classified_project_count": len(participants) + len(nonparticipants),
        "semantic_graph_participant_count": len(participants),
        "explicit_nonparticipant_count": len(nonparticipants),
        "unclassified_project_count": len(unclassified),
        "semantic_graph_participants": participants,
        "explicit_nonparticipants": nonparticipants,
        "unclassified_repositories": unclassified,
        "coverage_status": "complete" if not unclassified else "incomplete",
        "topology_status": "complete_among_declared_participants",
    }
    return participants, nonparticipants, unclassified, coverage


def load_declarations(workspace: Path, *, commons_root: Path | None = None) -> tuple[list[dict], list[dict], dict[str, Any]]:
    registry_document = family_registry()
    registry = {item["id"]: item for item in registry_document["projects"]}
    root = (commons_root or Path(__file__).resolve().parents[1]).resolve()
    participation_path = root / "family" / "participation-v1.json"
    if participation_path.is_file():
        participants, _nonparticipants, _unclassified, coverage = load_participation(root, registry_document)
    else:
        participants = []
        coverage = None
    discovered: dict[str, tuple[Path, dict]] = {}
    for candidate in sorted(workspace.iterdir()):
        path = candidate / "family-semantic-contracts-v1.json"
        if not path.is_file():
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise FamilyGraphError(f"cannot read {path}: {error}") from error
        declaration = validate_declaration(value)
        project_id = declaration["repository_id"]
        if project_id not in registry:
            raise FamilyGraphError(f"{path} declares an unknown family project: {project_id}")
        if participants and project_id not in participants:
            raise FamilyGraphError(
                f"{path} declares {project_id}, but participation metadata classifies it as nonparticipant/unclassified"
            )
        if project_id in discovered:
            raise FamilyGraphError(
                f"multiple checkouts declare family project {project_id}: "
                f"{discovered[project_id][0]} and {path}"
            )
        generated_provider_path = candidate / "family-provider-metadata-v1.json"
        if generated_provider_path.is_file():
            try:
                generated_provider = json.loads(generated_provider_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
                raise FamilyGraphError(
                    f"cannot read generated provider metadata {generated_provider_path}: {error}"
                ) from error
            validate_generated_provider_metadata(
                generated_provider,
                repository_id=project_id,
                declaration=declaration,
                checkout=candidate,
            )
        discovered[project_id] = (candidate, declaration)

    declarations: list[dict] = []
    repositories: list[dict] = []
    missing = sorted(set(participants) - set(discovered)) if participants else []
    if missing:
        raise FamilyGraphError(
            "participant repositories are missing from the synchronization workspace: " + ", ".join(missing)
        )
    for project_id in sorted(discovered):
        checkout, declaration = discovered[project_id]
        path = checkout / "family-semantic-contracts-v1.json"
        if declaration["repository_id"] != project_id:
            raise FamilyGraphError(
                f"{path} declares {declaration['repository_id']}, expected {project_id}"
            )
        declaration = bind_declaration_evidence(checkout, declaration)
        # The graph is a reusable family artifact, so its source path must not
        # depend on whether a checkout directory is named ``RAVEL``, ``ravel``,
        # or another local alias.  Keep the repository-owned identity in the
        # path while retaining the actual checkout only for evidence reads.
        declaration["_path"] = f"{project_id}/family-semantic-contracts-v1.json"
        declarations.append(declaration)
        project = registry[project_id]
        repositories.append(
            {
                "id": project_id,
                "repository": project["repository"],
                "revision": declaration["revision"],
            }
        )
    if coverage is None:
        participant_ids = sorted(discovered)
        coverage = {
            "registry_identity": "unavailable",
            "registered_family_project_count": len(participant_ids),
            "classified_project_count": len(participant_ids),
            "semantic_graph_participant_count": len(participant_ids),
            "explicit_nonparticipant_count": 0,
            "unclassified_project_count": 0,
            "semantic_graph_participants": participant_ids,
            "explicit_nonparticipants": [],
            "unclassified_repositories": [],
            "coverage_status": "complete",
            "topology_status": "complete_among_declared_participants",
        }
    return declarations, repositories, coverage


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path.cwd().parent)
    parser.add_argument(
        "--commons-root",
        type=Path,
        help="override the Commons metadata root (used by isolated declaration fixtures)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "family" / "semantic-edges-v1.json",
    )
    parser.add_argument(
        "--check", action="store_true", help="fail if the checked-in graph is stale"
    )
    args = parser.parse_args()
    declarations, repositories, coverage = load_declarations(
        args.workspace.resolve(),
        commons_root=args.commons_root.resolve() if args.commons_root else None,
    )
    graph = generate_graph(declarations, repositories, coverage=coverage)
    rendered = json.dumps(graph, indent=2, ensure_ascii=False) + "\n"
    if args.check:
        try:
            current = args.output.read_text(encoding="utf-8")
        except OSError as error:
            print(f"stale semantic graph: {error}")
            return 1
        if current != rendered:
            print(f"stale semantic graph: regenerate {args.output}")
            return 1
        print(graph["graph_identity"])
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(graph["graph_identity"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
