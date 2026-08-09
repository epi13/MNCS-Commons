"""Forge boundary: references Forge evidence; never dispatches Forge work."""

from typing import Any, Mapping

from ._common import observation_from_external


def from_forge_result(
    result: Mapping[str, Any], *, subject_identity: str, scope_context: Mapping[str, Any]
) -> dict[str, Any]:
    identity = str(
        result.get("record_identity") or result.get("result_identity") or "forge:unknown"
    )
    status = str(result.get("status", "UNKNOWN"))
    return observation_from_external(
        producer_type="forge",
        producer_id="forge-adapter",
        source_identity=identity,
        subject_type="artifact",
        subject_identity=subject_identity,
        summary="Forge result imported as untrusted evidence reference",
        evidence_ids=[identity],
        scope_context=scope_context,
        details={"outcome": status, "forgeRecord": identity},
    )


def from_forge_work_request(
    request: Mapping[str, Any], *, subject_identity: str, scope_context: Mapping[str, Any]
) -> dict[str, Any]:
    return observation_from_external(
        producer_type="forge",
        producer_id="forge-adapter",
        source_identity=str(request.get("request_identity", "forge:request:unknown")),
        subject_type="artifact",
        subject_identity=subject_identity,
        summary="Forge work request is available for explicit local review",
        evidence_ids=[],
        scope_context=scope_context,
        details={"outcome": "UNKNOWN", "request": dict(request)},
    )
