"""Semantic-conformance adapter tests."""

from __future__ import annotations

from mncs_commons.adapters.semantic_conformance import (
    conformance_report_summary,
    from_conformance_report,
)


def conformance_report(**overrides) -> dict:
    report = {
        "schema_version": "mncs.conformance-report/1",
        "generator": "mncs-conformance/0.1",
        "subject_module": "examples.semantic.arithmetic",
        "subject_fingerprint": "f" * 64,
        "seed": 1,
        "cases_per_predicate": 2,
        "worker": {"host": "fedora", "os": "linux", "arch": "x86_64"},
        "predicates": [
            {
                "operation": "add",
                "clause": "prop_roundtrip",
                "kind": "property",
                "predicate": "prop_roundtrip",
                "predicate_identity": "mncs:example:predicate",
                "status": "tested",
                "cases": [
                    {
                        "id": "prop_roundtrip-c000",
                        "arguments": [],
                        "reference": {"status": "returned", "observed": [], "verdict": "pass"},
                        "determinism_stable": True,
                        "backends": [
                            {"backend": "mncs-portable-wasm-mvp", "status": "returned", "observed": [], "verdict": "pass"},
                        ],
                    }
                ],
            }
        ],
        "summary": {"pass": 2, "fail": 0, "unknown": 0, "unsupported": 0},
    }
    report.update(overrides)
    return report


def test_clean_report_projects_to_pass_without_authority_promotion() -> None:
    result = from_conformance_report(conformance_report(), subject_identity="f" * 64, created_at="2026-09-06T08:00:00Z")
    record = result.record
    assert record is not None
    assert result.valid
    details = record["details"]
    assert details["outcome"] == "PASS"
    # Commons never claims independent verification from one ingestion.
    assert details["independentVerificationStatus"] == "UNKNOWN"
    # Provenance travels verbatim: worker, seed, fingerprint, backends.
    assert details["worker"] == {"host": "fedora", "os": "linux", "arch": "x86_64"}
    assert details["seed"] == 1
    assert details["subjectFingerprint"] == "f" * 64
    assert details["backendsExercised"] == ["mncs-portable-wasm-mvp"]
    assert details["predicateIdentities"] == ["mncs:example:predicate"]
    assert record["confidence"]["level"] != "verified"


def test_violations_project_to_fail() -> None:
    report = conformance_report(summary={"pass": 1, "fail": 2, "unknown": 0, "unsupported": 0})
    result = from_conformance_report(report, subject_identity="f" * 64, created_at="2026-09-06T08:00:00Z")
    assert result.record is not None
    assert result.record["details"]["outcome"] == "FAIL"


def test_unknown_stays_unknown() -> None:
    report = conformance_report(summary={"pass": 1, "fail": 0, "unknown": 1, "unsupported": 0})
    result = from_conformance_report(report, subject_identity="f" * 64, created_at="2026-09-06T08:00:00Z")
    assert result.record is not None
    assert result.record["details"]["outcome"] == "UNKNOWN"


def test_untested_report_establishes_no_pass() -> None:
    report = conformance_report(predicates=[], summary={"pass": 0, "fail": 0, "unknown": 0, "unsupported": 3})
    result = from_conformance_report(report, subject_identity="f" * 64, created_at="2026-09-06T08:00:00Z")
    assert result.record is not None
    assert result.record["details"]["outcome"] == "UNKNOWN"


def test_unsupported_schema_version_refuses_to_guess() -> None:
    report = conformance_report(schema_version="mncs.conformance-report/9")
    result = from_conformance_report(report, subject_identity="f" * 64, created_at="2026-09-06T08:00:00Z")
    assert result.record is None
    assert any(d.code == "UNKNOWN_CONFORMANCE_SCHEMA_VERSION" for d in result.diagnostics)
    assert "schema_version" in result.unresolved_fields


def test_malformed_report_establishes_no_claim() -> None:
    report = conformance_report()
    del report["summary"]
    result = from_conformance_report(report, subject_identity="f" * 64, created_at="2026-09-06T08:00:00Z")
    assert result.record is None
    assert any(d.code == "MALFORMED_CONFORMANCE_REPORT" for d in result.diagnostics)


def test_summary_projection_ignores_non_integer_counts() -> None:
    assert conformance_report_summary({"summary": {"pass": True, "fail": -1}}) == {
        "pass": 0,
        "fail": 0,
        "unknown": 0,
        "unsupported": 0,
    }
