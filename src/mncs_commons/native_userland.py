"""Family-visible lifecycle summaries for native MNCS applications."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable


LIFECYCLE_STATES = frozenset(
    {
        "host_bootstrap",
        "hybrid",
        "native_shadow",
        "native_canonical",
        "host_deprecated",
        "host_removed",
    }
)

DEFAULT_REPOSITORIES = (
    "mncs-test",
    "mncs-actions",
    "mncs-debug",
    "mncs-doctor",
    "RAVEL",
    "MNCS-Commons",
    "mncs-forge",
)


class NativeUserlandStatusError(ValueError):
    """A repository status declaration is missing or structurally invalid."""


def load_native_userland_status(path: Path, repository_id: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise NativeUserlandStatusError(f"{repository_id} status is unreadable: {error}") from error
    if not isinstance(value, dict):
        raise NativeUserlandStatusError(f"{repository_id} status must be an object")
    if value.get("schema_version") != "mncs.native-userland-status/1":
        raise NativeUserlandStatusError(f"{repository_id} status schema is unsupported")
    declared = value.get("repository_id") or value.get("repository")
    if declared != repository_id:
        raise NativeUserlandStatusError(
            f"{repository_id} status declares repository {declared!r}"
        )
    lifecycle = value.get("status")
    if lifecycle not in LIFECYCLE_STATES:
        raise NativeUserlandStatusError(
            f"{repository_id} status has unsupported lifecycle {lifecycle!r}"
        )
    if not isinstance(value.get("canonical_entrypoint"), str):
        raise NativeUserlandStatusError(f"{repository_id} status has no canonical_entrypoint")
    return value


def aggregate_native_userland_status(
    workspace_root: Path,
    repositories: Iterable[str] = DEFAULT_REPOSITORIES,
) -> dict[str, Any]:
    applications = []
    for repository_id in repositories:
        path = workspace_root / repository_id / "native-userland-status.json"
        value = load_native_userland_status(path, repository_id)
        applications.append(
            {
                "repository_id": repository_id,
                "status": value["status"],
                "canonical_entrypoint": value["canonical_entrypoint"],
                "native_sources": value.get("native_sources", {}),
                "native_application_descriptor": value.get("native_application_descriptor"),
                "native_application_descriptors": value.get(
                    "native_application_descriptors", {}
                ),
                "native_provider_descriptors": value.get(
                    "native_provider_descriptors", {}
                ),
                "host_paths": value.get("host_paths", []),
                "blocker": value.get(
                    "blocker", value.get("next_migration_slice")
                ),
                "next_migration_slice": value.get("next_migration_slice"),
            }
        )
    applications.sort(key=lambda item: item["repository_id"].casefold())
    return {
        "schema_version": "mncs.native-userland-summary/1",
        "applications": applications,
        "by_lifecycle": {
            lifecycle: [
                item["repository_id"]
                for item in applications
                if item["status"] == lifecycle
            ]
            for lifecycle in sorted(LIFECYCLE_STATES)
        },
    }
