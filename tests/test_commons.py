from __future__ import annotations

import copy
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import pytest

from mncs_commons.adapters.forge import from_forge_result
from mncs_commons.adapters.language import from_language_identity
from mncs_commons.adapters.mnel import from_mnel_observation
from mncs_commons.bundle import BundleError, create_bundle, import_bundle, verify_bundle
from mncs_commons.canonical import canonical_digest, canonical_json
from mncs_commons.io import load_document
from mncs_commons.lifecycle import derive_lifecycle, validate_transition
from mncs_commons.models import RecordKind
from mncs_commons.protocol import protocol_spec, supported_versions
from mncs_commons.query import (
    QueryFilter,
    ScopeAssessment,
    assess_scope,
    bounded_graph,
    replication_correlation,
    unresolved_relationships,
)
from mncs_commons.store import CommonsStore, StoreError
from mncs_commons.validation import validate_event, validate_record


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
        "Epoch": {"windowStart": "2026-08-13T00:00:00Z", "workAttempted": []},
        "EpochSummary": {
            "epochId": "sha256:" + "a" * 64,
            "sourceIdentities": ["sha256:" + "a" * 64],
        },
        "ReplicationSeries": {
            "target": "sha256:" + "a" * 64,
            "passes": 3,
            "failures": 1,
            "sourceIdentities": ["sha256:" + "a" * 64],
        },
        "ObservationSeries": {"sourceIdentities": ["sha256:" + "a" * 64]},
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


def test_protocol_registry_and_golden_digest_vector() -> None:
    vector = json.loads(
        (
            Path(__file__).resolve().parents[1] / "compat/commons-v0alpha1/canonical-digests.json"
        ).read_text(encoding="utf-8")
    )["canonicalJsonV1"]
    assert canonical_json(vector["value"]).decode("utf-8") == vector["canonical"]
    assert canonical_digest(vector["value"], projected=False) == vector["sha256"]
    assert protocol_spec("commons.mncs.dev/v0alpha1") is not None
    assert "commons.mncs.dev/v0alpha1" in supported_versions()
    assert protocol_spec("commons.mncs.dev/v9") is None


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
    view = derive_lifecycle(
        {**record, "contentDigest": digest}, events, domain="commons:test-domain"
    )
    assert view.valid and view.current_state == "accepted"
    assert (
        derive_lifecycle({**record, "contentDigest": digest}, events).current_state
        == "domain-scoped"
    )
    forbidden = validate_transition("accepted", "verified", events[-1])
    assert not forbidden.valid


def test_lifecycle_event_target_identity_is_strict() -> None:
    event = make_event("not-a-digest", "proposed", "reproduced")
    assert any(item.code == "INVALID_DIGEST" for item in validate_event(event).diagnostics)


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


def test_lifecycle_acceptance_is_independent_per_domain(tmp_path: Path) -> None:
    store = CommonsStore(tmp_path / "commons")
    store.init()
    record = store.add_record(make_record())
    accepted = make_event(record.content_digest, "proposed", "reproduced")
    accepted["authority"]["domain"] = "project:a"
    store.add_event(accepted)
    accepted = make_event(record.content_digest, "reproduced", "verified")
    accepted["authority"]["domain"] = "project:a"
    store.add_event(accepted)
    accepted = make_event(record.content_digest, "verified", "accepted")
    accepted["authority"]["domain"] = "project:a"
    store.add_event(accepted)
    disputed = make_event(record.content_digest, "proposed", "disputed")
    disputed["authority"]["domain"] = "project:b"
    store.add_event(disputed)

    assert store.lifecycle(record.content_digest, domain="project:a").current_state == "accepted"
    assert store.lifecycle(record.content_digest, domain="project:b").current_state == "disputed"
    assert store.lifecycle(record.content_digest, domain="project:c").current_state == "proposed"
    assert {
        domain: view.current_state
        for domain, view in store.domain_views(record.content_digest).items()
    } == {"project:a": "accepted", "project:b": "disputed"}
    assert store.lifecycle(record.content_digest).current_state == "domain-scoped"
    assert len(store.query(QueryFilter(state="disputed"))) == 1
    assert len(store.query(QueryFilter(state="accepted", domain="project:a"))) == 1


def test_store_rejects_invalid_event_and_unresolved_target(tmp_path: Path) -> None:
    store = CommonsStore(tmp_path / "commons")
    store.init()
    event = make_event("sha256:" + "0" * 64, "proposed", "verified")
    with pytest.raises(StoreError):
        store.add_event(event)


def test_store_transaction_recovery_is_explicit_and_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = CommonsStore(tmp_path / "commons")
    store.init()

    def interrupted(_: object) -> None:
        raise OSError("simulated interruption")

    monkeypatch.setattr(store, "_append_row", interrupted)
    with pytest.raises(OSError, match="simulated interruption"):
        store.add_record(make_record())
    assert any(item.code == "PENDING_TRANSACTION" for item in store.verify().diagnostics)
    monkeypatch.undo()
    assert store.recover().valid
    assert store.recover().valid
    assert len(store.records()) == 1
    assert store.verify().valid


def test_corrupt_transaction_journal_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = CommonsStore(tmp_path / "commons")
    store.init()

    def interrupted(_: object) -> None:
        raise OSError("simulated interruption")

    monkeypatch.setattr(store, "_append_row", interrupted)
    with pytest.raises(OSError):
        store.add_record(make_record())
    monkeypatch.undo()
    transaction = next(store.transactions_path.iterdir())
    journal = json.loads((transaction / "journal.json").read_text(encoding="utf-8"))
    journal["contentPath"] = "../outside.json"
    (transaction / "journal.json").write_text(json.dumps(journal), encoding="utf-8")
    recovery = store.recover()
    assert not recovery.valid
    assert any(item.code == "RECOVERY_FAILED" for item in recovery.diagnostics)
    assert not (tmp_path / "outside.json").exists()


def test_store_concurrent_duplicate_inserts_are_idempotent(tmp_path: Path) -> None:
    root = tmp_path / "commons"
    CommonsStore(root).init()
    value = make_record()

    def insert(_: int) -> str:
        return CommonsStore(root).add_record(value).content_digest

    with ThreadPoolExecutor(max_workers=4) as executor:
        digests = list(executor.map(insert, range(8)))
    assert len(set(digests)) == 1
    assert len(CommonsStore(root).records()) == 1
    assert CommonsStore(root).verify().valid


def test_logical_record_revision_requires_lineage(tmp_path: Path) -> None:
    store = CommonsStore(tmp_path / "commons")
    store.init()
    first = store.add_record(make_record())
    changed = make_record()
    changed["statement"]["summary"] = "A deliberately revised bounded observation."
    with pytest.raises(StoreError, match="changed logical record"):
        store.add_record(changed)
    changed["metadata"]["revision"] = 2
    changed["metadata"]["previousDigest"] = first.content_digest
    second = store.add_record(changed)
    assert second.content_digest != first.content_digest


def test_store_rejects_relationship_cycles(tmp_path: Path) -> None:
    store = CommonsStore(tmp_path / "commons")
    store.init()
    first = make_record()
    first["metadata"]["recordId"] = "record:a"
    first["relationships"] = [{"type": "depends_on", "target": "record:b"}]
    store.add_record(first)
    second = make_record()
    second["metadata"]["recordId"] = "record:b"
    second["relationships"] = [{"type": "depends_on", "target": "record:a"}]
    with pytest.raises(StoreError, match="acyclic"):
        store.add_record(second)


def test_bundle_is_deterministic_bounded_and_idempotently_importable(tmp_path: Path) -> None:
    source = CommonsStore(tmp_path / "source")
    source.init()
    record = source.add_record(make_record())
    source.add_event(make_event(record.content_digest, "proposed", "disputed"))
    first_path = tmp_path / "first.zip"
    second_path = tmp_path / "second.zip"
    first_manifest = create_bundle(source, first_path)
    second_manifest = create_bundle(source, second_path)
    assert first_manifest == second_manifest
    assert first_path.read_bytes() == second_path.read_bytes()
    assert verify_bundle(first_path).valid

    imported = CommonsStore(tmp_path / "imported")
    imported.init()
    assert import_bundle(first_path, imported).valid
    assert import_bundle(first_path, imported).valid
    assert imported.verify().valid
    assert len(imported.records()) == 1 and len(imported.events()) == 1

    with pytest.raises(BundleError):
        create_bundle(source, first_path)


def test_bundle_rejects_path_traversal(tmp_path: Path) -> None:
    import zipfile

    malicious = tmp_path / "malicious.zip"
    with zipfile.ZipFile(malicious, "w") as archive:
        archive.writestr("../outside", b"never execute")
    verification = verify_bundle(malicious)
    assert not verification.valid
    assert any(item.code == "BUNDLE_INVALID" for item in verification.diagnostics)


def test_graph_traversal_is_bounded_and_replication_analysis_preserves_correlation() -> None:
    root = make_record()
    root["metadata"]["recordId"] = "record:root"
    root["contentDigest"] = canonical_digest(root)
    child = make_record()
    child["metadata"]["recordId"] = "record:child"
    child["relationships"] = [{"type": "derived_from", "target": root["contentDigest"]}]
    child["contentDigest"] = canonical_digest(child)
    graph = bounded_graph([root, child], [root["contentDigest"]], max_depth=1, max_nodes=2)
    assert len(graph.records) == 2
    assert not graph.truncated

    replications = []
    for suffix in ("a", "b"):
        replication = make_record("Replication")
        replication["metadata"]["recordId"] = f"replication:{suffix}"
        replication["details"]["targetRecord"] = "claim:placement"
        replication["contentDigest"] = canonical_digest(replication)
        replications.append(replication)
    analysis = replication_correlation(replications, "claim:placement")
    assert analysis.outcomes == {"FAIL": 2}
    assert "harness" in analysis.shared_dimensions
    assert not any("score" in key.lower() for key in analysis.as_dict())


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
    assert assess_scope(record, context) == ScopeAssessment.UNKNOWN
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


def test_review_query_requires_explicit_core_clock(tmp_path: Path) -> None:
    store = CommonsStore(tmp_path / "commons")
    store.init()
    record = make_record()
    record["scope"]["reviewAt"] = "2026-01-01T00:00:00Z"
    store.add_record(record)
    assert store.query(QueryFilter(needs_review=True)) == []
    assert len(
        store.query(
            QueryFilter(
                needs_review=True,
                now=datetime(2026, 8, 8, tzinfo=timezone.utc),
            )
        )
    ) == 1


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
        "Epoch",
        "EpochSummary",
        "ReplicationSeries",
        "ObservationSeries",
    }


def test_yaml_dependency_is_optional_and_failure_is_inert(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    document = tmp_path / "record.yaml"
    document.write_text("kind: Observation\n", encoding="utf-8")

    def missing_yaml(name: str) -> object:
        if name == "yaml":
            raise ImportError("PyYAML unavailable")
        raise AssertionError(f"unexpected optional import: {name}")

    monkeypatch.setattr("mncs_commons.io.import_module", missing_yaml)
    with pytest.raises(ValueError, match="optional 'yaml' dependency"):
        load_document(document)


def test_mnel_adapter_is_valid_observation() -> None:
    result = from_mnel_observation(
        {
            "observation_identity": "sha256:" + "1" * 64,
            "provider_id": "provider:test",
            "provider_version": "1",
        },
        subject_identity="experiment:test",
        created_at="2026-08-08T00:00:00Z",
    )
    assert result.valid and result.record is not None
    assert validate_record(result.record).valid


def test_adapter_compatibility_fixtures_preserve_source_limits() -> None:
    root = Path(__file__).resolve().parents[1]
    forge_fixture = json.loads(
        (root / "compat/forge/forge-cell-execution-0.1.json").read_text(encoding="utf-8")
    )
    forge = from_forge_result(
        forge_fixture,
        subject_identity="candidate:synthetic",
        scope_context={"environment": forge_fixture["identities"]["environment"]},
    )
    assert forge.recognized and forge.record is not None
    assert validate_record(forge.record).valid
    assert forge.record["details"]["outcome"] == "PASS"
    assert any(item.code == "MISSING_SOURCE_IDENTITY" for item in forge.diagnostics)

    language_fixture = json.loads(
        (root / "compat/mncs-language/semantic-identity-boundary.json").read_text(encoding="utf-8")
    )
    language = from_language_identity(
        language_fixture,
        subject_identity="mncs-language:graph",
        created_at="2026-08-08T00:00:00Z",
    )
    assert language.valid and language.record is not None
    assert (
        language.record["details"]["semanticGraphIdentity"]
        == language_fixture["semantic_graph_identity"]
    )


def test_adapter_missing_timestamp_or_version_does_not_fabricate_provenance() -> None:
    missing_time = from_mnel_observation(
        {"observation_identity": "mnel:obs", "provider_id": "provider:test"},
        subject_identity="experiment:test",
    )
    assert missing_time.record is None
    assert not any(
        item.get("metadata", {}).get("createdAt") == "1970-01-01T00:00:00Z"
        for item in [missing_time.record or {}]
    )
    unsupported = from_forge_result(
        {"schema_version": "999", "record_type": "future"},
        subject_identity="candidate:test",
        scope_context={},
        created_at="2026-08-08T00:00:00Z",
    )
    assert not unsupported.recognized
    assert unsupported.record is None


def test_synthetic_execution_placement_chain_preserves_domain_disagreement(tmp_path: Path) -> None:
    store = CommonsStore(tmp_path / "commons")
    store.init()
    observation = make_record("Observation")
    observation["metadata"]["recordId"] = "mnel:placement-observation"
    observation["scope"]["context"] = {
        "machine": "machine:synthetic-a",
        "provider": "provider:synthetic",
        "placement": "sequential-cpu-offload",
        "vramReserveBytes": 4294967296,
    }
    observation["statement"]["summary"] = (
        "Synthetic bounded observation: sequential CPU offload reduced persistent VRAM "
        "at a measured transfer cost."
    )
    observed = store.add_record(observation)

    request = make_record("WorkRequest")
    request["metadata"]["recordId"] = "forge:placement-replication-request"
    request["details"]["requestState"] = "open"
    request["relationships"] = [{"type": "requests", "target": observed.content_digest}]
    store.add_record(request)

    claim = make_record("Claim")
    claim["metadata"]["recordId"] = "claim:placement-narrowed"
    claim["details"]["falsifier"] = "the same result fails on the named machine and provider"
    claim["relationships"] = [{"type": "narrows", "target": observed.content_digest}]
    claimed = store.add_record(claim)
    failed = make_record("Replication")
    failed["metadata"]["recordId"] = "replication:placement-counterexample"
    failed["details"]["targetRecord"] = claimed.content_digest
    failed["relationships"] = [{"type": "failed_to_replicate", "target": claimed.content_digest}]
    failed_record = store.add_record(failed)
    assert failed_record.data["details"]["outcome"] == "FAIL"

    event = make_event(claimed.content_digest, "proposed", "reproduced")
    event["authority"]["domain"] = "project:accepting"
    store.add_event(event)
    event = make_event(claimed.content_digest, "reproduced", "verified")
    event["authority"]["domain"] = "project:accepting"
    store.add_event(event)
    event = make_event(claimed.content_digest, "verified", "accepted")
    event["authority"]["domain"] = "project:accepting"
    store.add_event(event)
    event = make_event(claimed.content_digest, "proposed", "disputed")
    event["authority"]["domain"] = "project:reviewing"
    store.add_event(event)
    assert (
        store.lifecycle(claimed.content_digest, domain="project:accepting").current_state
        == "accepted"
    )
    assert (
        store.lifecycle(claimed.content_digest, domain="project:reviewing").current_state
        == "disputed"
    )
    assert store.lifecycle(claimed.content_digest).current_state == "domain-scoped"


def test_synthetic_language_identity_supersession_chain(tmp_path: Path) -> None:
    fixture = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "compat/mncs-language/semantic-identity-boundary.json"
        ).read_text(encoding="utf-8")
    )
    store = CommonsStore(tmp_path / "commons")
    store.init()
    first_result = from_language_identity(
        fixture,
        subject_identity="mncs-language:graph",
        created_at="2026-08-08T00:00:00Z",
    )
    assert first_result.record is not None
    first = dict(first_result.record)
    first["metadata"]["recordId"] = "language:lowering-claim"
    original = store.add_record(first)
    revised_fixture = dict(fixture)
    revised_fixture["semantic_graph_identity"] = fixture["semantic_graph_identity"] + ":revision-2"
    second_result = from_language_identity(
        revised_fixture,
        subject_identity="mncs-language:graph",
        created_at="2026-08-08T00:01:00Z",
    )
    assert second_result.record is not None
    revised = dict(second_result.record)
    revised["metadata"]["recordId"] = "language:lowering-claim-revision-2"
    revised["relationships"] = [{"type": "supersedes", "target": original.content_digest}]
    replacement = store.add_record(revised)
    assert replacement.content_digest != original.content_digest
    event = make_event(original.content_digest, "proposed", "superseded")
    event["transition"] = {"from": "verified", "to": "superseded"}
    # The source record is intentionally not verified: Commons rejects the stale event.
    with pytest.raises(StoreError):
        store.add_event(event)
