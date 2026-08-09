"""MNEL boundary: learned-provider findings remain diagnostic observations."""

from typing import Any, Mapping

from ..models import Diagnostic, ResultStatus
from ._common import observation_from_external
from .contracts import AdapterResult


def from_mnel_observation(
    observation: Mapping[str, Any], *, subject_identity: str, created_at: str | None = None
) -> AdapterResult:
    identity = observation.get("observation_identity")
    provider = observation.get("provider_id")
    diagnostics: list[Diagnostic] = []
    if not provider:
        diagnostics.append(
            Diagnostic(
                "MISSING_PROVIDER_IDENTITY",
                "provider_id",
                "MNEL provider identity is unresolved",
                severity="warning",
            )
        )
    raw_status = observation.get("verdict", observation.get("outcome", "UNKNOWN"))
    status = str(raw_status).upper()
    if status not in {item.value for item in ResultStatus}:
        status = ResultStatus.UNKNOWN.value
        diagnostics.append(
            Diagnostic("UNKNOWN_SOURCE_STATUS", "verdict", "status preserved as UNKNOWN")
        )
    return observation_from_external(
        producer_type="mnel",
        producer_id="machine-native-experimental-learning",
        source_identity=str(identity) if identity else None,
        subject_type="experiment",
        subject_identity=subject_identity,
        summary="MNEL learned-provider observation preserved as diagnostic evidence",
        evidence_ids=[str(identity)] if identity else [],
        scope_context={
            "provider": provider,
            "providerVersion": observation.get("provider_version"),
        },
        created_at=created_at,
        source_version=str(observation.get("schema_version"))
        if observation.get("schema_version")
        else None,
        diagnostics=diagnostics,
        details={"outcome": status, "diagnostic": dict(observation)},
    )
