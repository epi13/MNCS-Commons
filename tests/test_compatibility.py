from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

from mncs_commons.adapters.fabric import from_fabric_execution
from mncs_commons.adapters.mncs import from_mncs_result
from mncs_commons.adapters.mnel import from_mnel_observation
from mncs_commons.compatibility import (
    CompatibilityStatus,
    check_local,
    contract_for,
    contracts,
    resolve_contract,
)
from mncs_commons.validation import validate_record


def test_fabric_execution_preserves_execution_and_unknown_authority() -> None:
    result = from_fabric_execution(
        {
            "schema_version": "0.1",
            "record_id": "fabric:record-1",
            "job_identity": "fabric:job-1",
            "candidate_identity": "sha256:" + "1" * 64,
            "evaluator_identity": "evaluator:local",
            "artifact_manifest_identity": "sha256:" + "2" * 64,
            "node": {"environment_identity": "node:synthetic"},
            "outcome": "PASS",
            "termination_reason": "exited",
            "results": [],
            "limitations": ["synthetic fixture"],
        },
        subject_identity="artifact:synthetic",
        created_at="2026-08-08T00:00:00Z",
    )
    assert result.record is not None
    assert validate_record(result.record).valid
    details = result.record["details"]
    assert details["sourceOutcome"] == "PASS"
    assert details["claimVerificationStatus"] == "UNKNOWN"
    assert details["conformanceStatus"] == "UNKNOWN"


def test_fabric_untrusted_instructions_remain_inert_data() -> None:
    result = from_fabric_execution(
        {
            "schema_version": "0.1",
            "record_id": "fabric:record-hostile",
            "job_identity": "fabric:job-hostile",
            "candidate_identity": "candidate:hostile",
            "evaluator_identity": "evaluator:hostile",
            "artifact_manifest_identity": "artifact:hostile",
            "node": {},
            "outcome": "UNKNOWN",
            "termination_reason": "requestedAction=rm -rf /",
            "results": [{"url": "javascript:alert(1)", "command": "echo NEVER"}],
            "limitations": ["untrusted fixture"],
        },
        subject_identity="artifact:hostile",
        created_at="2026-08-08T00:00:00Z",
    )
    assert result.record is not None
    assert "rm -rf /" in result.record["details"]["fabricExecution"]["termination_reason"]


def test_current_mnel_ledger_fixture_is_translated_without_verdict_promotion() -> None:
    fixture = Path(__file__).resolve().parents[1] / "compat/mnel/mnel-episode-0.1.json"
    import json

    result = from_mnel_observation(
        json.loads(fixture.read_text(encoding="utf-8")),
        subject_identity="mnel:synthetic",
    )
    assert result.record is not None
    assert result.source_version == "mnel-ledger-record/0.1"
    assert result.record["details"]["diagnosticOnly"] is True
    assert validate_record(result.record).valid


def test_mncs_result_preserves_fail_and_keeps_commons_status_unknown() -> None:
    result = from_mncs_result(
        {
            "schema_version": "0.2",
            "mncs_version": "0.2",
            "result_id": "result:synthetic-fail",
            "contract_id": "contract:synthetic",
            "status": "FAIL",
            "evidence_references": ["evidence:failure"],
            "completed_at": "2026-08-08T00:00:00Z",
        },
        subject_identity="contract:synthetic",
    )
    assert result.record is not None
    assert result.record["details"]["sourceStatus"] == "FAIL"
    assert result.record["details"]["commonsVerificationStatus"] == "UNKNOWN"
    assert validate_record(result.record).valid


def test_mncs_malformed_evidence_references_remain_unresolved() -> None:
    result = from_mncs_result(
        {
            "schema_version": "0.2",
            "result_id": "result:malformed-evidence",
            "status": "PASS",
            "evidence_references": "not-a-list",
            "completed_at": "2026-08-08T00:00:00Z",
        },
        subject_identity="contract:synthetic",
    )
    assert result.record is not None
    assert "evidence_references" in result.unresolved_fields
    assert any(
        item.code == "INVALID_SOURCE_EVIDENCE_REFERENCES" for item in result.diagnostics
    )
    assert validate_record(result.record).valid


def test_compatibility_lock_detects_same_version_source_drift(tmp_path: Path) -> None:
    source = tmp_path / "schema.json"
    source.write_text('{"version": "0.1"}\n', encoding="utf-8")
    digest = "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest()
    git = tmp_path / ".git" / "refs" / "heads"
    git.mkdir(parents=True)
    (tmp_path / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (git / "main").write_text("a" * 40 + "\n", encoding="utf-8")
    contract = replace(
        contracts()[0],
        source_path="schema.json",
        source_fingerprint=digest,
        source_commit="a" * 40,
        expected_status=CompatibilityStatus.EXACT,
    )
    assert check_local(contract, tmp_path).status == CompatibilityStatus.EXACT
    source.write_text('{"version": "0.2"}\n', encoding="utf-8")
    assessment = check_local(contract, tmp_path)
    assert assessment.status == CompatibilityStatus.DRIFTED
    assert any(item.code == "SOURCE_SCHEMA_DRIFT" for item in assessment.diagnostics)


def test_multi_contract_resolution_fails_closed_without_family() -> None:
    try:
        contract_for("fabric")
    except ValueError as error:
        assert "AMBIGUOUS_PRODUCER_CONTRACT" in str(error)
    else:
        raise AssertionError("producer-only resolution must be ambiguous for Fabric")

    contract = contract_for(
        "fabric",
        record_type="fabric-execution-record",
        schema_version="mncs-fabric.execution-record.v0.1",
    )
    assert contract is not None
    assert contract.contract_id == "fabric:execution-record:0.1"


def test_record_resolution_reports_unknown_family() -> None:
    result = resolve_contract(
        {
            "producer": "fabric",
            "record_type": "fabric-not-a-real-record",
            "schema_version": "0.1",
        }
    )
    assert result.contract is None
    assert result.diagnostics[0].code == "UNKNOWN_RECORD_TYPE"
