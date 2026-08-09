"""Explicit wire-protocol compatibility boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .models import API_VERSION


@dataclass(frozen=True, slots=True)
class ProtocolSpec:
    api_version: str
    canonicalization: str
    migration: str


PROTOCOLS: dict[str, ProtocolSpec] = {
    API_VERSION: ProtocolSpec(
        api_version=API_VERSION,
        canonicalization="canonical-json-v1; contentDigest excluded from identity projection",
        migration="no migration currently defined; reject unknown versions",
    )
}


def protocol_spec(api_version: Any) -> ProtocolSpec | None:
    return PROTOCOLS.get(str(api_version))


def require_protocol(value: Mapping[str, Any]) -> ProtocolSpec:
    api_version = value.get("apiVersion")
    spec = protocol_spec(api_version)
    if spec is None:
        raise ValueError(f"unsupported Commons wire version: {api_version!r}")
    return spec


def supported_versions() -> tuple[str, ...]:
    return tuple(sorted(PROTOCOLS))
