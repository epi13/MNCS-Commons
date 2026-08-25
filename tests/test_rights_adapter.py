"""Rights & Provenance adapter tests."""

from __future__ import annotations

from mncs_commons.adapters.rights import (
    from_rights_evidence_record,
    rights_finding_summary,
)


def evidence_record() -> dict:
    return {
        "schema_version": "0.2.0",
        "evidence_id": "mncs-fabric://execution/rec-1/rights-evidence",
        "kind": "fabric-execution",
        "producer": {
            "producer": "mncs-fabric",
            "recordKind": "RightsProvenanceEvidence",
            "schemaVersion": "0.2.0",
            "stableId": "mncs-fabric://execution/rec-1/rights-evidence",
        },
        "subject": {"artifact_refs": [{"id": "artifact-9", "role": "output"}]},
        "claims": [
            {
                "claim_type": "unknown-license-state",
                "statement": "No license metadata observed for dependency X.",
                "confidence": "insufficient-evidence",
            }
        ],
        "context": {"timestamp": "2026-08-24T10:00:00Z"},
        "limitations": ["Fabric does not determine licensing."],
        "content_digest": "sha256:" + "0" * 64,
    }


def test_evidence_record_projects_to_inert_observation() -> None:
    result = from_rights_evidence_record(
        evidence_record(),
        subject_identity="artifact-9",
        created_at="2026-08-24T10:00:01Z",
    )
    record = result.record
    assert record is not None
    assert "lack sufficient evidence" in str(record["statement"]["summary"])
    details = record["details"]
    assert details["rightsEvidenceId"] == "mncs-fabric://execution/rec-1/rights-evidence"
    assert details["outcome"] == "UNKNOWN"
    assert details["rightsClaimKinds"] == ["unknown-license-state"]


def test_unsupported_schema_version_refuses_to_guess() -> None:
    record = dict(evidence_record())
    record["schema_version"] = "9.9"
    result = from_rights_evidence_record(record, subject_identity="artifact-9")
    assert result.record is None
    assert any(d.code == "UNKNOWN_RIGHTS_SCHEMA_VERSION" for d in result.diagnostics)
    assert "schema_version" in result.unresolved_fields


def test_insufficient_confidence_stays_unknown() -> None:
    result = from_rights_evidence_record(
        evidence_record(), subject_identity="artifact-9", created_at="2026-08-24T10:00:01Z"
    )
    record = result.record
    assert record is not None
    details = record["details"]
    assert details["rightsInsufficientEvidenceClaims"] == 1
    assert details["claimVerificationStatus"] == "UNKNOWN"
    # The producer type reflects the source system, and confidence stays unreported.
    assert record["confidence"]["level"] == "unreported"


def test_validator_report_summary_is_bounded_and_historical() -> None:
    summary = rights_finding_summary(
        {
            "outcome": "review-required",
            "findings": ["copyright status remains unresolved"],
            "manifest_identity_expected": "ab" * 32,
            "legal_conclusion": "NOT_MADE",
        }
    )
    assert summary["outcome"] == "review-required"
    assert summary["manifestIdentity"] == "ab" * 32
    assert "not current policy by itself" in summary["note"]

    bogus = rights_finding_summary({"outcome": "definitely-fine"})
    assert bogus["outcome"] == "invalid"
