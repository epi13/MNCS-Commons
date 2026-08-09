from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from mncs_commons.adapters.mnel import from_mnel_observation
from mncs_commons.canonical import canonical_digest, canonical_json
from mncs_commons.lifecycle import derive_lifecycle, validate_transition
from mncs_commons.models import RecordKind
from mncs_commons.query import QueryFilter, ScopeAssessment, assess_scope, unresolved_relationships
from mncs_commons.store import CommonsStore, StoreError
from mncs_commons.validation import validate_record


def make_record(kind: str = "Observation") -> dict:
    details = {
        "Observation": {"outcome": "UNKNOWN", "measurements": {"vrAM": 12.4}},
        "Claim": {"outcome": "UNKNOWN", "falsifier": "a bounded counterexample"},
        "WorkRequest": {
            "objective": "replicate the observation",
            "requestedKind": "Replication",
            "authorityBoundary": "verification-only; no repository mutation",
        },
        "Replication": {
            "targetRecord": "sha256:" + "a" * 64,
            "outcome": "FAIL",
            "independence": {
                "modelFamily": "same-family",
                "promptSource": "sha256:" + "b" * 64,
                "harness": "sha256:" + "c" * 64,
                "compiler": "clang-18",
                "machine": "machine:test-a",
                "provider": "provider:test",
                "artifactAncestry": ["sha256:" + "d" * 64],
            },
        },
        "Advisory": {"severity": "correctness", "concern": "scope is narrow"},
        "Decision": {
            "domain": "commons:test",
            "rationale": "bounded evidence",
            "authorityScope": "local",
        },
    }[kind]
    return {
        "apiVersion": "commons.mncs.dev/v0alpha1",
        "kind": kind,
        "metadata": {
            "recordId": f"test:{kind}",
            "createdAt": "2026-08-08T00:00:00Z",
            "author": {"type": "test", "id": "test:writer"},
            "labels": ["synthetic"],
        },
        "subject": {
            "type": "artifact",
            "identity": "sha256:" + "e" * 64,
            "repository": "test/repo",
            "revision": "sha256:" + "f" * 64,
            "contracts": ["mncs:contract:test"],
        },
        "scope": {
            "context": {
                "sourceRevision": "sha256:" + "f" * 64,
                "compiler": {"name": "clang", "version": "18"},
                "target": {"os": "linux", "architecture": "x86_64"},
            },
            "limitations": ["not generalized beyond this target"],
            "reviewAt": "2027-01-01T00:00:00Z",
        },
        "statement": {
            "summary": f"Synthetic {kind} for deterministic tests.",
            "details": "Data only.",
        },
        "evidence": [{"id": "forge:result:test", "relation": "supports", "status": "UNKNOWN"}],
        "reproduction": {
            "prerequisites": ["isolated verifier environment"],
            "procedure": [
                {"command": "echo SHOULD_NEVER_EXECUTE", "authorityRequired": "verification-only"}
            ],
            "expected": ["record result without changing authority"],
        },
        "dependencies": ["mncs:contract:test"],
        "affectedContracts": ["mncs:contract:test"],
        "provenance": {
            "producer": {"type": "test", "id": "test:writer"},
            "sourceRecords": ["run:test"],
            "environment": {"machineIdentity": "machine:test-a"},
            "ancestry": ["run:test"],
        },
        "confidence": {"level": "medium", "rationale": "fixture is intentionally bounded"},
        "security": {
            "sensitivity": "public",
            "executableAttachments": False,
            "instructionsAreUntrusted": True,
            "requiredExternalAuthority": False,
        },
        "lifecycle": {"initialState": "proposed", "reviewWhen": ["source revision changes"]},
        "relationships": [],
        "details": details,
    }


def make_event(target: str, source: str, destination: str) -> dict:
    return {
        "apiVersion": "commons.mncs.dev/v0alpha1",
        "kind": "LifecycleEvent",
        "metadata": {
            "createdAt": "2026-08-08T00:01:00Z",
            "author": {"type": "reviewer", "id": "reviewer:test"},
        },
        "target": {"contentDigest": target},
        "transition": {"from": source, "to": destination},
        "authority": {
            "domain": "commons:test-domain",
            "actor": "reviewer:test",
            "rationale": "explicit synthetic lifecycle evidence",
        },
        "evidence": [{"id": "review:test", "relation": "supports", "status": "PASS"}],
    }


@pytest.mark.parametrize("kind", [item.value for item in RecordKind])
def test_all_record_kinds_validate(kind: str) -> None:
    assert validate_record(make_record(kind)).valid


def test_unknown_and_missing_fields_fail_closed() -> None:
    value = make_record()
    value["unexpected"] = True
    value["details"].pop("outcome")
    report = validate_record(value)
    codes = {item.code for item in report.diagnostics}
    assert {"UNKNOWN_FIELD", "REQUIRED_DETAIL"} <= codes


def test_unknown_kind_and_version_fail_closed() -> None:
    value = make_record()
    value["kind"] = "Speculation"
    value["apiVersion"] = "commons.mncs.dev/v9"
    codes = {item.code for item in validate_record(value).diagnostics}
    assert {"UNKNOWN_RECORD_KIND", "UNSUPPORTED_API_VERSION"} <= codes


def test_canonical_json_and_digest_ignore_object_and_declared_set_order() -> None:
    first = make_record()
    second = copy.deepcopy(first)
    second["relationships"] = [
        {"type": "supports", "target": "z"},
        {"type": "contradicts", "target": "a"},
    ]
    first["relationships"] = list(reversed(second["relationships"]))
    second["metadata"] = dict(reversed(list(second["metadata"].items())))
    assert canonical_json(first) == canonical_json(second)
    assert canonical_digest(first) == canonical_digest(second)


def test_digest_mismatch_and_nan_are_rejected() -> None:
    value = make_record()
    value["contentDigest"] = "sha256:" + "0" * 64
    report = validate_record(value)
    assert any(item.code == "DIGEST_MISMATCH" for item in report.diagnostics)
    with pytest.raises(ValueError):
        canonical_json({"bad": float("nan")})
    value.pop("contentDigest")
    value["contentDigest"] = "sha256:" + "z" * 64
    assert any(item.code == "INVALID_DIGEST" for item in validate_record(value).diagnostics)


def test_nested_unknown_security_field_fails_closed() -> None:
    value = make_record()
    value["security"]["trustScore"] = 0.9
    assert any(item.code == "UNKNOWN_FIELD" for item in validate_record(value).diagnostics)


def test_lifecycle_legal_and_illegal_transitions() -> None:
    record = make_record()
    digest = canonical_digest(record)
    events = [
        make_event(digest, "proposed", "reproduced"),
        make_event(digest, "reproduced", "verified"),
        make_event(digest, "verified", "accepted"),
    ]
    view = derive_lifecycle({**record, "contentDigest": digest}, events)
    assert view.valid and view.current_state == "accepted"
    forbidden = validate_transition("accepted", "verified", events[-1])
    assert not forbidden.valid


@pytest.mark.parametrize(
    ("source", "destination"),
    [
        ("verified", "superseded"),
        ("proposed", "expired"),
        ("reproduced", "rejected"),
        ("proposed", "withdrawn"),
    ],
)
def test_lifecycle_terminal_and_negative_paths(source: str, destination: str) -> None:
    record = make_record()
    digest = canonical_digest(record)
    event = make_event(digest, source, destination)
    assert validate_transition(source, destination, event).valid


def test_store_append_query_tamper_and_duplicate(tmp_path: Path) -> None:
    store = CommonsStore(tmp_path / "commons")
    store.init()
    record = store.add_record(make_record())
    assert store.add_record(make_record()).content_digest == record.content_digest
    event = make_event(record.content_digest, "proposed", "disputed")
    store.add_event(event)
    store.add_event(event)
    assert store.query(QueryFilter(state="disputed"))[0]["kind"] == "Observation"
    assert store.verify().valid
    path = store.records_path / f"{record.content_digest.removeprefix('sha256:')}.json"
    tampered = json.loads(path.read_text())
    tampered["statement"]["summary"] = "tampered"
    path.write_text(json.dumps(tampered), encoding="utf-8")
    assert not store.verify().valid


def test_store_rejects_invalid_event_and_unresolved_target(tmp_path: Path) -> None:
    store = CommonsStore(tmp_path / "commons")
    store.init()
    event = make_event("sha256:" + "0" * 64, "proposed", "verified")
    with pytest.raises(StoreError):
        store.add_event(event)


def test_store_detects_corrupt_ledger_and_orphans(tmp_path: Path) -> None:
    store = CommonsStore(tmp_path / "commons")
    store.init()
    record = store.add_record(make_record())
    orphan = store.records_path / ("f" * 64 + ".json")
    orphan.write_text("{}", encoding="utf-8")
    assert any(item.code == "ORPHAN_RECORD" for item in store.verify().diagnostics)
    store.ledger_path.write_bytes(store.ledger_path.read_bytes() + b'{"partial":')
    result = store.verify()
    assert not result.valid
    assert any(item.code == "LEDGER_READ_FAILED" for item in result.diagnostics)
    assert record.content_digest


def test_scope_staleness_and_unknown() -> None:
    record = make_record()
    context = record["scope"]["context"]
    assert (
        assess_scope(record, context, now=datetime(2026, 9, 1, tzinfo=timezone.utc))
        == ScopeAssessment.COMPATIBLE
    )
    changed = copy.deepcopy(context)
    changed["compiler"]["version"] = "19"
    assert assess_scope(record, changed) == ScopeAssessment.INCOMPATIBLE
    assert assess_scope(record, {}) == ScopeAssessment.UNKNOWN
    expired = copy.deepcopy(record)
    expired["scope"]["reviewAt"] = "2020-01-01T00:00:00Z"
    assert (
        assess_scope(expired, context, now=datetime.now(timezone.utc))
        == ScopeAssessment.REVIEW_REQUIRED
    )


def test_replication_preserves_correlation_and_reproduction_is_inert() -> None:
    replication = make_record("Replication")
    assert validate_record(replication).valid
    assert replication["details"]["independence"]["modelFamily"] == "same-family"
    assert "SHOULD_NEVER_EXECUTE" in json.dumps(make_record())


def test_unresolved_relationships_are_reported_separately() -> None:
    record = make_record()
    record["relationships"] = [{"type": "supports", "target": "external:missing"}]
    assert validate_record(record).valid
    assert unresolved_relationships(record, set()) == record["relationships"]


def test_pass_metadata_does_not_promote_lifecycle_state() -> None:
    record = make_record()
    record["details"]["outcome"] = "PASS"
    assert derive_lifecycle(record, []).current_state == "proposed"


def test_schema_snapshot_has_all_protocol_kinds() -> None:
    schema = json.loads(
        (
            Path(__file__).resolve().parents[1] / "schemas/mncs-commons-v0alpha1.schema.json"
        ).read_text()
    )
    assert "record" in schema["$defs"] and "event" in schema["$defs"]
    assert set(schema["$defs"]["record"]["properties"]["kind"]["enum"]) == {
        "Observation",
        "Claim",
        "WorkRequest",
        "Replication",
        "Advisory",
        "Decision",
    }


def test_mnel_adapter_is_valid_observation() -> None:
    value = from_mnel_observation(
        {
            "observation_identity": "sha256:" + "1" * 64,
            "provider_id": "provider:test",
            "provider_version": "1",
        },
        subject_identity="experiment:test",
    )
    assert validate_record(value).valid
