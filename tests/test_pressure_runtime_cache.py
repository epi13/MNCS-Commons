"""The small process-independent policy artifact cache is identity checked."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from mncs_commons.pressure_runtime import (
    _CACHE_SCHEMA,
    _atomic_cache_write,
    _read_cached_artifact,
)


def test_cached_artifact_requires_matching_inputs_and_payload_digest(tmp_path: Path) -> None:
    identity = "sha256:" + "1" * 64
    artifact = json.dumps({"schema_version": "fixture/1"}, sort_keys=True).encode()
    _atomic_cache_write(tmp_path / "backend.json", artifact)
    receipt = {
        "schema_version": _CACHE_SCHEMA,
        "input_identity": identity,
        "artifact_sha256": hashlib.sha256(artifact).hexdigest(),
    }
    _atomic_cache_write(tmp_path / "receipt.json", json.dumps(receipt).encode())
    assert _read_cached_artifact(tmp_path, identity) == artifact
    assert _read_cached_artifact(tmp_path, "sha256:" + "2" * 64) is None

    _atomic_cache_write(tmp_path / "backend.json", b'{"tampered":true}')
    assert _read_cached_artifact(tmp_path, identity) is None


def test_cached_artifact_rejects_invalid_json_even_with_matching_digest(tmp_path: Path) -> None:
    identity = "sha256:" + "3" * 64
    artifact = b"not-json"
    _atomic_cache_write(tmp_path / "backend.json", artifact)
    _atomic_cache_write(tmp_path / "receipt.json", json.dumps({
        "schema_version": _CACHE_SCHEMA,
        "input_identity": identity,
        "artifact_sha256": hashlib.sha256(artifact).hexdigest(),
    }).encode())
    assert _read_cached_artifact(tmp_path, identity) is None
