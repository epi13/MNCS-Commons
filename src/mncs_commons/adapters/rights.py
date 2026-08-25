"""Rights & Provenance adapters: retain findings without inventing policy.

These adapters project mncs-rights-provenance artifacts (v0.2 evidence
records, validator reports) into inert Commons records so institutional
reasoning about rights/provenance can be retained, related, and superseded
using the standard family-record machinery.

Boundary preserved: a Commons record about a rights finding is *memory*, not
current policy. Superseded or historical findings must not be reinterpreted as
active release decisions; use ``RelationType.SUPERSEDES`` and lifecycle states.
"""

from __future__ import annotations

from typing import Any, Mapping

from ..models import Diagnostic
from ._common import observation_from_external
from .contracts import AdapterResult

RIGHTS_EVIDENCE_SCHEMA_VERSIONS = frozenset({"0.2.0"})
RIGHTS_VALIDATOR_OUTCOMES = frozenset(
    {"pass", "pass-with-findings", "review-required", "blocked", "invalid"}
)


def from_rights_evidence_record(
    record: Mapping[str, Any],
    *,
    subject_identity: str,
    created_at: str | None = None,
    scope_context: Mapping[str, Any] | None = None,
    artifact_id: str | None = None,
) -> AdapterResult:
    """Project an mncs-rights-provenance evidence record into an Observation.

    The observation summary names the producer and claim kinds; claim content
    is preserved in details verbatim. No confidence is upgraded: a claim with
    ``insufficient-evidence`` stays unknown in Commons terms.
    """

    diagnostics: list[Diagnostic] = []
    schema_version = str(record.get("schema_version") or "")
    if schema_version not in RIGHTS_EVIDENCE_SCHEMA_VERSIONS:
        diagnostics.append(
            Diagnostic(
                "UNKNOWN_RIGHTS_SCHEMA_VERSION",
                "schema_version",
                f"unsupported rights evidence schema_version {schema_version!r}; refusing to guess",
            )
        )
        return AdapterResult(
            None,
            tuple(diagnostics),
            schema_version or None,
            recognized=True,
            unresolved_fields=("schema_version",),
        )

    evidence_id = record.get("evidence_id")
    if not isinstance(evidence_id, str) or not evidence_id:
        diagnostics.append(
            Diagnostic(
                "MISSING_SOURCE_IDENTITY",
                "evidence_id",
                "rights evidence record has no evidence_id",
            )
        )
        return AdapterResult(
            None,
            tuple(diagnostics),
            schema_version,
            recognized=True,
            unresolved_fields=("evidence_id",),
        )

    kind = str(record.get("kind", "other"))
    claims = record.get("claims")
    claim_kinds = sorted(
        {
            str(claim.get("claim_type", "other"))
            for claim in (claims if isinstance(claims, list) else [])
            if isinstance(claim, Mapping)
        }
    )
    insufficient = sum(
        1
        for claim in (claims if isinstance(claims, list) else [])
        if isinstance(claim, Mapping) and claim.get("confidence") == "insufficient-evidence"
    )
    summary = (
        f"Rights & provenance evidence ({kind}) from "
        f"{record.get('producer', {}).get('producer', 'unknown-producer')}: "
        f"claim kinds {claim_kinds or ['none']}"
        + (f"; {insufficient} claim(s) explicitly lack sufficient evidence" if insufficient else "")
    )

    details = {
        "outcome": "UNKNOWN",
        "claimVerificationStatus": "UNKNOWN",
        "conformanceStatus": "UNKNOWN",
        "protectedCustodyStatus": "UNKNOWN",
        "rightsEvidenceId": evidence_id,
        "rightsClaimKinds": claim_kinds,
        "rightsInsufficientEvidenceClaims": insufficient,
    }
    if isinstance(record.get("limitations"), list):
        details["rightsLimitations"] = [str(item) for item in record["limitations"]]

    return observation_from_external(
        producer_type=str(record.get("producer", {}).get("producer", "mncs-rights-provenance")),
        producer_id=str(record.get("producer", {}).get("producer", "mncs-rights-provenance")),
        source_identity=evidence_id,
        subject_type="artifact",
        subject_identity=subject_identity,
        summary=summary,
        evidence_ids=[artifact_id] if artifact_id else [],
        scope_context=dict(scope_context or {}),
        created_at=created_at or record.get("context", {}).get("timestamp"),
        source_version=schema_version,
        details=details,
        unresolved_fields=(
            ["rights_confidence"] if insufficient else []
        ),
    )


def rights_finding_summary(report: Mapping[str, Any]) -> dict[str, Any]:
    """Extract the bounded summary of a validator rights report for retention.

    Accepts an mncs-validator-rs / mncs-rp validation report. The outcome is
    retained as recorded at evaluation time; later evaluations supersede via
    relations, never by mutation.
    """

    outcome = str(report.get("outcome", ""))
    return {
        "outcome": outcome if outcome in RIGHTS_VALIDATOR_OUTCOMES else "invalid",
        "findings": [str(item) for item in report.get("findings") or ()],
        "manifestIdentity": report.get("manifest_identity_expected"),
        "legalConclusion": "NOT_MADE",
        "note": report.get("note")
        or "Historical evaluation result; not current policy by itself.",
    }


__all__ = [
    "RIGHTS_EVIDENCE_SCHEMA_VERSIONS",
    "from_rights_evidence_record",
    "rights_finding_summary",
]
