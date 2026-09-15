#!/usr/bin/env python3
"""Generate/check the compact family semantic graph from repo declarations."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from mncs_commons.family_graph import (
    FamilyGraphError,
    bind_declaration_evidence,
    generate_graph,
    validate_declaration,
)
from mncs_commons.family_registry import family_registry


def load_declarations(workspace: Path) -> tuple[list[dict], list[dict]]:
    registry = {item["id"]: item for item in family_registry()["projects"]}
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
        if project_id in discovered:
            raise FamilyGraphError(
                f"multiple checkouts declare family project {project_id}: "
                f"{discovered[project_id][0]} and {path}"
            )
        discovered[project_id] = (candidate, declaration)

    declarations: list[dict] = []
    repositories: list[dict] = []
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
    return declarations, repositories


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path.cwd().parent)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "family" / "semantic-edges-v1.json",
    )
    parser.add_argument(
        "--check", action="store_true", help="fail if the checked-in graph is stale"
    )
    args = parser.parse_args()
    declarations, repositories = load_declarations(args.workspace.resolve())
    graph = generate_graph(declarations, repositories)
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
