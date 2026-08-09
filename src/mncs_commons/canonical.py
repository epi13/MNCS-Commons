"""Canonical JSON and content-derived identities."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

_UNORDERED_ARRAY_PATHS = {
    ("evidence",),
    ("relationships",),
    ("dependencies",),
    ("affectedContracts",),
    ("scope", "reviewWhen"),
    ("provenance", "sourceRecords"),
    ("provenance", "ancestry"),
}


def _canonicalize(value: Any, path: tuple[str, ...] = ()) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _canonicalize(item, path + (str(key),)) for key, item in value.items()}
    if isinstance(value, list):
        items = [_canonicalize(item, path) for item in value]
        if path in _UNORDERED_ARRAY_PATHS:
            return sorted(items, key=lambda item: _encode(item))
        return items
    if isinstance(value, tuple):
        return _canonicalize(list(value), path)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise TypeError(
        f"unsupported JSON value at {'.'.join(path) or '<root>'}: {type(value).__name__}"
    )


def _encode(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_json(value: Any) -> bytes:
    """Return deterministic UTF-8 JSON bytes, rejecting non-JSON numbers."""

    return _encode(_canonicalize(value))


def identity_projection(value: Mapping[str, Any]) -> dict[str, Any]:
    """Remove only the self-digest field from an envelope before hashing it."""

    projection = _canonicalize(value)
    if not isinstance(projection, dict):
        raise TypeError("identity projection requires an object")
    metadata = projection.get("metadata")
    if isinstance(metadata, dict):
        metadata.pop("contentDigest", None)
    projection.pop("contentDigest", None)
    return projection


def canonical_digest(value: Mapping[str, Any], *, projected: bool = True) -> str:
    payload = identity_projection(value) if projected else _canonicalize(value)
    return "sha256:" + hashlib.sha256(_encode(payload)).hexdigest()
