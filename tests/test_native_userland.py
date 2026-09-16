from __future__ import annotations

import json

import pytest

from mncs_commons.native_userland import (
    NativeUserlandStatusError,
    aggregate_native_userland_status,
)


def _write_status(root, repository_id: str, status: str) -> None:
    path = root / repository_id
    path.mkdir(parents=True)
    (path / "native-userland-status.json").write_text(
        json.dumps(
            {
                "schema_version": "mncs.native-userland-status/1",
                "repository_id": repository_id,
                "status": status,
                "canonical_entrypoint": f"{repository_id} entrypoint",
                "native_sources": {},
            }
        ),
        encoding="utf-8",
    )


def test_aggregate_exposes_lifecycle_buckets(tmp_path) -> None:
    _write_status(tmp_path, "mncs-test", "native_canonical")
    _write_status(tmp_path, "mncs-actions", "native_shadow")
    summary = aggregate_native_userland_status(
        tmp_path, repositories=("mncs-test", "mncs-actions")
    )
    assert summary["by_lifecycle"]["native_canonical"] == ["mncs-test"]
    assert summary["by_lifecycle"]["native_shadow"] == ["mncs-actions"]


def test_invalid_lifecycle_fails_closed(tmp_path) -> None:
    _write_status(tmp_path, "mncs-test", "unknown")
    with pytest.raises(NativeUserlandStatusError):
        aggregate_native_userland_status(tmp_path, repositories=("mncs-test",))
