from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from mncs_commons.archive import restore_archive, verify_archive
from mncs_commons.canonical import canonical_digest
from mncs_commons.epochs import make_epoch_record, make_epoch_summary, make_replication_series
from mncs_commons.retention import RetentionController, classify_record
from mncs_commons.store import CommonsStore, StoreError
from mncs_commons.validation import validate_record

from tests.test_commons import make_record


def _dated(record: dict, when: str) -> dict:
    record["metadata"]["createdAt"] = when
    record.pop("contentDigest", None)
    return record


def test_classification_and_pin_protection(tmp_path: Path) -> None:
    claim = make_record("Claim")
    replica_pass = make_record("Replication")
    replica_pass["details"]["outcome"] = "PASS"
    replica_fail = make_record("Replication")
    replica_fail["details"]["outcome"] = "FAIL"
    assert classify_record(claim) == "canonical"
    assert classify_record(replica_pass) == "ephemeral"
    assert classify_record(replica_fail) == "evidence"
    store = CommonsStore(tmp_path)
    store.init()
    stored = store.add_record(replica_pass)
    controller = RetentionController(store)
    controller.pin(stored.content_digest, reason="operator keep")
    plan = controller.plan(now="2026-12-01T00:00:00Z")
    assert stored.content_digest in controller.pins()
    assert all(item["contentDigest"] != stored.content_digest for item in plan["candidates"])


def test_ttl_eligibility_and_reference_protection(tmp_path: Path) -> None:
    store = CommonsStore(tmp_path)
    store.init()
    old = _dated(make_record("Replication"), "2026-01-01T00:00:00Z")
    old["details"]["outcome"] = "PASS"
    stored_old = store.add_record(old)
    claim = make_record("Claim")
    claim["relationships"] = [{"type": "derived_from", "target": stored_old.content_digest}]
    store.add_record(claim)
    lone = _dated(make_record("Observation"), "2026-01-01T00:00:00Z")
    lone["details"]["outcome"] = "PASS"
    stored_lone = store.add_record(lone)
    plan = RetentionController(store).plan(now="2026-08-01T00:00:00Z")
    eligible = {item["contentDigest"] for item in plan["candidates"]}
    assert stored_lone.content_digest in eligible
    assert stored_old.content_digest not in eligible


def test_archive_verify_corrupt_and_restore(tmp_path: Path) -> None:
    store = CommonsStore(tmp_path / "hot")
    store.init()
    record = store.add_record(_dated(make_record("Observation"), "2026-01-01T00:00:00Z"))
    from mncs_commons.archive import create_archive, inspect_archive

    archive = create_archive(store, records=store.records(), events=[], now="2026-08-13T00:00:00Z")
    verified = verify_archive(store, archive["archiveId"])
    assert verified["valid"] is True
    inspected = inspect_archive(store, archive["archiveId"])
    assert inspected["recordCount"] == 1
    bundle = Path(inspected["path"]) / "bundle.tar.zst"
    bundle.write_bytes(bundle.read_bytes() + b"tamper")
    with pytest.raises(StoreError, match="ARCHIVE_CORRUPT"):
        verify_archive(store, archive["archiveId"])
    bundle.write_bytes(bundle.read_bytes()[: -len(b"tamper")])
    restored = restore_archive(store, archive["archiveId"], tmp_path / "restored")
    assert restored["valid"] is True
    recovered = CommonsStore(tmp_path / "restored").get(record.content_digest)
    assert recovered is not None
    assert recovered["kind"] == "Observation"


def test_dry_run_does_not_mutate(tmp_path: Path) -> None:
    store = CommonsStore(tmp_path)
    store.init()
    store.add_record(_dated(make_record("Observation"), "2026-01-01T00:00:00Z"))
    before = store.storage_usage()["ledgerEntries"]
    result = RetentionController(store).compact(dry_run=True, confirm=False, now="2026-08-01T00:00:00Z")
    assert result["applied"] is False
    assert store.storage_usage()["ledgerEntries"] == before


def test_compaction_requires_confirm_and_preserves_canonical(tmp_path: Path) -> None:
    store = CommonsStore(tmp_path)
    store.init()
    old = store.add_record(_dated(make_record("Observation"), "2026-01-01T00:00:00Z"))
    claim = make_record("Claim")
    stored_claim = store.add_record(claim)
    result = RetentionController(store).compact(dry_run=False, confirm=True, now="2026-08-01T00:00:00Z")
    assert result["applied"] is True
    assert store.get(stored_claim.content_digest) is not None
    assert store.get(old.content_digest) is not None  # archived but resolvable
    hot = {item["contentDigest"] for item in store.records()}
    assert stored_claim.content_digest in hot
    assert old.content_digest not in hot
    assert store.verify().valid


def test_epoch_and_series_are_valid_knowledge() -> None:
    epoch = make_epoch_record(started_at="2026-08-13T06:00:00Z", workers=["fabric-worker-01"])
    assert validate_record(epoch).valid
    summary = make_epoch_summary(
        {"contentDigest": "sha256:" + "a" * 64},
        attempted=["work-1"],
        changed=["claim-1"],
        discoveries=[],
        failures=[],
        claims=[],
        unresolved=["blocked-1"],
        continuation=["retry-review"],
        source_identities=["sha256:" + "a" * 64],
    )
    series = make_replication_series(
        target="sha256:" + "a" * 64,
        passes=437,
        failures=2,
        workers=["fabric-worker-01"],
        models=["granite3.3:2b"],
        first_observed="2026-01-01T00:00:00Z",
        last_observed="2026-08-13T00:00:00Z",
        source_identities=["sha256:" + "b" * 64],
        notable_failures=["sha256:" + "c" * 64],
    )
    assert validate_record({**summary, "contentDigest": canonical_digest(summary)}).valid
    assert validate_record({**series, "contentDigest": canonical_digest(series)}).valid


def test_synthetic_workload_reduces_hot_set_and_deduplicates(tmp_path: Path) -> None:
    store = CommonsStore(tmp_path)
    store.init()
    claim = store.add_record(make_record("Claim"))
    for index in range(80):
        replica = _dated(make_record("Replication"), "2026-01-01T00:00:00Z")
        replica["details"]["outcome"] = "PASS"
        replica["metadata"]["recordId"] = f"test:Replication:{index}"
        replica["statement"]["details"] = f"attempt {index}"
        stored = store.add_record(replica)
        if index == 0:
            first = stored
    store.add_record(make_replication_series(
        target=claim.content_digest,
        passes=80,
        failures=0,
        workers=["fabric-worker-01"],
        models=["granite3.3:2b"],
        first_observed="2026-01-01T00:00:00Z",
        last_observed="2026-01-02T00:00:00Z",
        source_identities=[first.content_digest],
        notable_failures=[],
    ))
    before = store.storage_usage()
    result = RetentionController(store).compact(dry_run=False, confirm=True, now="2026-08-01T00:00:00Z")
    after = store.storage_usage()
    assert after["ledgerEntries"] < before["ledgerEntries"]
    assert after["contentFiles"] < before["contentFiles"]
    assert store.get(claim.content_digest) is not None
    assert result["archiveVerification"]["valid"] is True
    # identical content-addressed re-add is a no-op
    again = store.add_record(claim.data)
    assert again.content_digest == claim.content_digest
    assert store.verify().valid
