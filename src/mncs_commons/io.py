"""Bounded document loading at the file boundary."""

from __future__ import annotations

import json
from importlib import import_module
from pathlib import Path
from typing import Any

MAX_DOCUMENT_BYTES = 4 * 1024 * 1024


def _unique_object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def load_document(path: Path) -> Any:
    raw = path.read_bytes()
    if len(raw) > MAX_DOCUMENT_BYTES:
        raise ValueError(f"document exceeds {MAX_DOCUMENT_BYTES} byte limit")
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as json_error:
        if path.suffix.lower() not in {".yaml", ".yml"}:
            raise ValueError(f"invalid JSON: {json_error}") from json_error
        try:
            yaml_module: Any = import_module("yaml")
        except ImportError as yaml_error:
            raise ValueError("YAML input requires the optional 'yaml' dependency") from yaml_error
        value = yaml_module.safe_load(raw)
        if value is None:
            raise ValueError("document is empty") from None
        return value
