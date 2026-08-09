"""MNEL boundary: learned-provider findings remain diagnostic observations."""

from typing import Any, Mapping

from ._common import observation_from_external


def from_mnel_observation(
    observation: Mapping[str, Any], *, subject_identity: str
) -> dict[str, Any]:
    identity = str(observation.get("observation_identity", "mnel:observation:unknown"))
    return observation_from_external(
        producer_type="mnel",
        producer_id=str(observation.get("provider_id", "mnel-provider")),
        source_identity=identity,
        subject_type="experiment",
        subject_identity=subject_identity,
        summary="MNEL learned-provider observation preserved as diagnostic evidence",
        evidence_ids=[identity],
        scope_context={
            "provider": observation.get("provider_id", "unknown"),
            "providerVersion": observation.get("provider_version", "unknown"),
        },
        details={"outcome": "UNKNOWN", "diagnostic": dict(observation)},
    )
