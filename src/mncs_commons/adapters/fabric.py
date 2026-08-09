"""Fabric boundary: preserve execution/environment references as evidence."""

from typing import Any, Mapping

from ._common import observation_from_external


def from_fabric_execution(execution: Mapping[str, Any], *, subject_identity: str) -> dict[str, Any]:
    identity = str(execution.get("execution_identity", "fabric:execution:unknown"))
    return observation_from_external(
        producer_type="fabric",
        producer_id="fabric-adapter",
        source_identity=identity,
        subject_type="artifact",
        subject_identity=subject_identity,
        summary="Fabric execution record referenced without granting transport authority",
        evidence_ids=[identity],
        scope_context={"environmentIdentity": execution.get("environment_identity", "unknown")},
        details={"outcome": str(execution.get("status", "UNKNOWN")), "execution": dict(execution)},
    )
