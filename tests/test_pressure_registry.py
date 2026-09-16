"""End-to-end tests for the family-wide pressure exchange."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from mncs_commons.pressure import (
    PressureError,
    PressureRegistry,
    _validate_transition_shape,
    extract_pressure_markers,
    known_repositories,
    pressure_id,
)

WHEN = "2026-09-12T00:00:00Z"


def pressure_spec(
    *, signature: str = "fs.atomic-publish.v1", repository: str = "mncs-store"
) -> dict:
    return {
        "target": "language",
        "domain": "io.filesystem",
        "capability": "atomic_publish",
        "title": "Atomic publication is not expressible",
        "severity": "blocking",
        "discoveredBy": repository,
        "discoveredAt": WHEN,
        "summary": "A consumer must publish a staged file atomically.",
        "requiredBehavior": "Capability-authorized same-filesystem rename with explicit failure.",
        "reproducer": {"signature": signature, "path": "tests/reproducer.mncs"},
        "observation": {
            "repository": repository,
            "observedAt": WHEN,
            "sourceRef": {"commit": "abc123", "path": "tests/reproducer.mncs"},
            "languageProfile": "0.13",
            "compiler": {"revision": "compiler-abc"},
            "summary": "The source cannot name atomic rename.",
            "reproduction": {"status": "PASS", "instructions": "run the minimal reproducer"},
            "evidence": [
                {
                    "id": "mncs-store:reproducer:atomic-publish",
                    "kind": "test",
                    "status": "PASS",
                    "ref": "tests/reproducer.mncs",
                    "summary": "Compiler rejects the required effect.",
                }
            ],
            "workaround": {
                "description": "Host driver calls os.replace.",
                "locations": ["tests/store_phase1a.py"],
                "active": True,
            },
        },
    }


def test_new_pressure_has_global_id_and_deterministic_projection(tmp_path: Path) -> None:
    registry = PressureRegistry(tmp_path / "pressures")
    created = registry.add(pressure_spec())
    expected = pressure_id("language", "io.filesystem", "atomic_publish", "fs.atomic-publish.v1")
    assert created["id"] == expected
    assert registry.validate().valid
    listed = registry.query(target="language", unresolved=True)
    assert listed[0]["id"] == expected
    assert listed[0]["affectedRepositories"] == ["mncs-store"]
    # The declaration identity does not depend on wording or checkout paths.
    changed = pressure_spec()
    changed["title"] = "Different wording"
    changed["sourceRef"] = {"path": "/another/checkout/tests/reproducer.mncs"}
    assert (
        pressure_id(
            "language", changed["domain"], changed["capability"], changed["reproducer"]["signature"]
        )
        == expected
    )


def test_uninitialized_registry_fails_closed(tmp_path: Path) -> None:
    report = PressureRegistry(tmp_path / "pressures").validate()
    assert not report.valid
    assert report.diagnostics[0].code == "REGISTRY_INCOMPLETE"


def test_existing_pressure_accumulates_another_repository_and_candidates(tmp_path: Path) -> None:
    registry = PressureRegistry(tmp_path / "pressures")
    created = registry.add(pressure_spec())
    extra = {
        "repository": "mncs-ingest",
        "observedAt": WHEN,
        "sourceRef": {"commit": "ingest456", "path": "language/reproducer.mncs"},
        "summary": "Ingest independently reaches the same missing primitive.",
        "reproduction": {"status": "PASS", "instructions": "run the same semantic case"},
        "evidence": [
            {
                "id": "mncs-ingest:test:atomic-publish",
                "kind": "test",
                "status": "PASS",
                "ref": "tests/atomic_publish.rs",
                "summary": "The required source spelling is rejected.",
            }
        ],
        "workaround": {"description": "Host-side publication shim.", "active": True},
    }
    observed = registry.observe(created["id"], extra)
    projection = registry.show(created["id"])
    assert observed["repository"] == "mncs-ingest"
    assert projection.data["affectedRepositories"] == ["mncs-ingest", "mncs-store"]
    candidates = registry.candidates(
        target="language",
        domain="io.filesystem",
        capability="atomic_publish",
        exclude=created["id"],
    )
    assert candidates == []
    assert registry.validate().valid


def test_alias_and_canonical_verifications_share_one_current_repository_state(
    tmp_path: Path,
) -> None:
    registry = PressureRegistry(tmp_path / "pressures")
    created = registry.add(pressure_spec(repository="mncs-forge-mcp"))
    pressure = created["id"]

    registry.verify(
        pressure,
        repository="mncs-forge-mcp",
        status="PASS",
        workaround_removed=True,
        summary="historical alias verification",
        observed_at="2026-09-14T00:00:00Z",
    )
    registry.verify(
        pressure,
        repository="mncs-forge",
        status="PASS",
        workaround_removed=True,
        summary="current canonical verification",
        observed_at="2026-09-14T00:00:01Z",
    )

    projection = registry.show(pressure)
    assert len(projection.data["verification"]) == 2
    assert len(projection.data["verificationCurrent"]) == 1
    assert projection.data["verificationCurrent"][0]["repository"] == "mncs-forge"
    assert projection.data["verificationSummary"] == {
        "affected": 1,
        "pass": 1,
        "fail": 0,
        "unknown": 0,
    }
    result = registry.query(repository="mncs-forge")
    assert result[0]["verificationState"] == "ready"


def test_lifecycle_keeps_available_distinct_from_resolved_and_requires_all_consumers(
    tmp_path: Path,
) -> None:
    registry = PressureRegistry(tmp_path / "pressures")
    created = registry.add(pressure_spec())
    pressure = created["id"]
    first_observation = created["observation"]["id"]
    registry.observe(
        pressure,
        {
            "repository": "mncs-ingest",
            "observedAt": WHEN,
            "summary": "Second consumer reproduces the pressure.",
            "reproduction": {"status": "PASS", "instructions": "run ingest case"},
            "evidence": [
                {
                    "id": "ingest-evidence",
                    "status": "PASS",
                    "ref": "ingest/test",
                    "summary": "reproduced",
                }
            ],
            "workaround": {"description": "retained shim", "active": True},
        },
    )
    registry.transition(
        pressure, "confirmed", actor="mncs-store", evidence_refs=[first_observation]
    )
    registry.transition(
        pressure,
        "accepted",
        actor="mncs-language",
        reason="shared language pressure",
        evidence_refs=[first_observation],
    )
    registry.transition(
        pressure, "implementing", actor="mncs-language", reason="implement atomic publication"
    )
    implementation_event = registry.transition(
        pressure,
        "available",
        actor="mncs-language",
        evidence_refs=[first_observation],
        implementation={"ref": "mncs-language:commit:atomic-publish", "profile": "0.16"},
        occurred_at="2026-09-13T00:00:00Z",
    )
    assert registry.show(pressure).status == "available"
    assert (
        registry.show(pressure).data["implementation"]["ref"]
        == "mncs-language:commit:atomic-publish"
    )
    assert implementation_event["to"] == "available"
    registry.transition(pressure, "verifying", actor="mncs-store")
    store_verification = registry.verify(
        pressure,
        repository="mncs-store",
        status="PASS",
        workaround_removed=True,
        summary="Store removed os.replace shim and the original case passes.",
        observed_at="2026-09-14T00:00:00Z",
        evidence=[
            {
                "id": "store-closure",
                "status": "PASS",
                "ref": "store/tests",
                "summary": "original case passes",
            }
        ],
    )
    with pytest.raises(PressureError, match="every affected repository"):
        registry.transition(
            pressure, "resolved", actor="mncs-store", evidence_refs=[store_verification["id"]]
        )
    ingest_verification = registry.verify(
        pressure,
        repository="mncs-ingest",
        status="PASS",
        workaround_removed=True,
        summary="Ingest removed its shim and the original case passes.",
        observed_at="2026-09-14T00:00:01Z",
        evidence=[
            {
                "id": "ingest-closure",
                "status": "PASS",
                "ref": "ingest/tests",
                "summary": "original case passes",
            }
        ],
    )
    registry.verify(
        pressure,
        repository="mncs-store",
        status="FAIL",
        workaround_removed=False,
        summary="A later store run still exercises the old path.",
        observed_at="2026-09-14T00:00:00.500Z",
    )
    with pytest.raises(PressureError, match="PASS verification from mncs-store"):
        registry.transition(
            pressure,
            "resolved",
            actor="mncs-store",
            evidence_refs=[store_verification["id"], ingest_verification["id"]],
        )
    store_retry = registry.verify(
        pressure,
        repository="mncs-store",
        status="PASS",
        workaround_removed=True,
        summary="Store rerun passes after the transient failure.",
        observed_at="2026-09-14T00:00:01Z",
    )
    registry.transition(
        pressure,
        "resolved",
        actor="mncs-store",
        evidence_refs=[store_verification["id"], ingest_verification["id"], store_retry["id"]],
    )
    projection = registry.show(pressure)
    assert projection.status == "resolved"
    assert projection.data["unresolved"] is False
    assert registry.validate().valid


def test_duplicate_preserves_both_records_and_requires_explicit_relationship(
    tmp_path: Path,
) -> None:
    registry = PressureRegistry(tmp_path / "pressures")
    first = registry.add(pressure_spec(signature="store.atomic-publish.v1"))["id"]
    second = registry.add(
        pressure_spec(signature="ingest.atomic-publish.v1", repository="mncs-ingest")
    )["id"]
    assert first != second
    with pytest.raises(PressureError, match="duplicate_of"):
        registry.transition(second, "duplicate", actor="mncs-commons", reason="candidate only")
    relation = registry.relate(second, "duplicate_of", first, actor="mncs-commons")
    registry.transition(second, "duplicate", actor="mncs-commons", reason="same root cause")
    assert relation["relation"] == "duplicate_of"
    assert registry.show(second).status == "duplicate"
    assert registry.show(first).status == "discovered"
    assert registry.validate().valid


def test_invalid_transition_and_stale_head_are_rejected(tmp_path: Path) -> None:
    registry = PressureRegistry(tmp_path / "pressures")
    created = registry.add(pressure_spec())
    pressure = created["id"]
    with pytest.raises(PressureError, match="discovered -> resolved"):
        registry.transition(pressure, "resolved", actor="mncs-store")
    event = registry.transition(
        pressure, "confirmed", actor="mncs-store", evidence_refs=[created["observation"]["id"]]
    )
    with pytest.raises(PressureError, match="stale pressure head"):
        registry.transition(
            pressure,
            "accepted",
            actor="mncs-language",
            reason="accept",
            evidence_refs=[created["observation"]["id"]],
            expected_previous="EVT-0000000000000000",
        )
    assert registry.show(pressure).events[-1]["id"] == event["id"]


def test_concurrent_transition_heads_fail_validation(tmp_path: Path) -> None:
    root = tmp_path / "pressures"
    base = PressureRegistry(root)
    created = base.add(pressure_spec())
    branch_a = tmp_path / "branch-a"
    branch_b = tmp_path / "branch-b"
    shutil.copytree(root, branch_a)
    shutil.copytree(root, branch_b)
    a_event = PressureRegistry(branch_a).transition(
        created["id"],
        "confirmed",
        actor="mncs-store",
        evidence_refs=[created["observation"]["id"]],
        reason="a",
    )
    b_event = PressureRegistry(branch_b).transition(
        created["id"],
        "confirmed",
        actor="mncs-ingest",
        evidence_refs=[created["observation"]["id"]],
        reason="b",
    )
    shutil.copy2(branch_a / "events" / f"{a_event['id']}.json", root / "events")
    shutil.copy2(branch_b / "events" / f"{b_event['id']}.json", root / "events")
    report = base.validate()
    assert not report.valid
    assert any(item.code == "CONCURRENT_TRANSITIONS" for item in report.diagnostics)
    assert a_event["id"] != b_event["id"]


def test_migration_preserves_legacy_text_and_markers(tmp_path: Path) -> None:
    source = tmp_path / "legacy"
    source.mkdir()
    legacy = source / "P1-003-atomic-rename.md"
    original = (
        "# P1-003 — No atomic rename\n\n"
        "## Minimal reproducer\n\n"
        "`os.replace` has no MNCS spelling.\n\n"
        "## Required semantics\n\n"
        "Atomic publication with explicit failure.\n\n"
        "## Workaround used\n\n"
        "Host driver calls `os.replace`.\n\n"
        "Status: workaround\n"
    )
    legacy.write_text(original, encoding="utf-8")
    registry = PressureRegistry(tmp_path / "pressures")
    result = registry.migrate_legacy("mncs-store", source)
    assert len(result["imported"]) == 1
    pressure = registry.show(result["imported"][0]["id"])
    assert pressure.data["legacy"]["sourceText"] == original
    assert pressure.data["legacy"]["historicalStatus"] == "workaround"
    assert pressure.data["status"] == "discovered"
    assert registry.validate().valid
    assert extract_pressure_markers("// mncs-pressure: " + pressure.id) == (pressure.id,)
    legacy.write_text(original.replace("No atomic rename", "Changed wording"), encoding="utf-8")
    refreshed = registry.migrate_legacy("mncs-store", source, refresh=True)
    assert refreshed["imported"] == []
    assert refreshed["skipped"]
    assert registry.show(pressure.id).data["legacy"]["sourceText"] == original
    assert registry.validate().valid


def test_generated_views_are_deterministic_and_repositories_are_descriptive(tmp_path: Path) -> None:
    registry = PressureRegistry(tmp_path / "pressures")
    registry.add(pressure_spec())
    generated = registry.generate_views()
    assert generated["views"] == [
        "awaiting-verification",
        "blocking",
        "by-domain",
        "by-repository",
        "multi-repository",
        "needs-revalidation",
        "python-fallback",
        "recently-resolved",
        "rust-fallback",
        "unresolved-language",
    ]
    index = json.loads((registry.views_dir / "index.json").read_text(encoding="utf-8"))
    assert index["views"] == generated["views"]
    first = (registry.views_dir / "unresolved-language.json").read_bytes()
    registry.generate_views()
    assert first == (registry.views_dir / "unresolved-language.json").read_bytes()
    assert any(item["id"] == "mncs-store" for item in known_repositories())


def test_migration_reads_nested_and_multi_entry_ledgers_without_alias_collisions(
    tmp_path: Path,
) -> None:
    source = tmp_path / "legacy"
    nested = source / "repros" / "P-001"
    nested.mkdir(parents=True)
    (nested / "README.md").write_text(
        "# P-001 — A bounded parser gap\n\n"
        "## Minimal reproducer\n\n`probe.mncs`\n\n"
        "## Current workaround\n\nPython adapter.\n\nSeverity: high\n",
        encoding="utf-8",
    )
    (source / "ledger.md").write_text(
        "# Local ledger\n\n"
        "## INGEST-P-002 — A second gap\n\n"
        "## Reproducer\n\n`second.mncs`\n\n"
        "## Desired behavior\n\nA typed view.\n\n"
        "## INGEST-P-003 — A third gap\n\n"
        "## Reproducer\n\n`third.mncs`\n",
        encoding="utf-8",
    )
    registry = PressureRegistry(tmp_path / "pressures")
    result = registry.migrate_legacy("mncs-ingest", source, target="language")
    assert [item["legacyId"] for item in result["imported"]] == [
        "INGEST-P-002",
        "INGEST-P-003",
        "P-001",
    ]
    assert len(registry.projections()) == 3
    migrated = registry.show(result["imported"][2]["id"])
    assert migrated.data["legacyIds"] == ["mncs-ingest:P-001"]
    assert migrated.data["signals"]["fallbackLanguage"] == "python"
    assert migrated.data["legacy"]["sourcePath"].endswith("repros/P-001/README.md")
    assert migrated.data["legacy"]["sourceText"].startswith("# P-001")
    assert registry.validate().valid


def test_mncs_lifecycle_mirror_has_same_transition_cells() -> None:
    allowed = {
        0: {1, 7, 8, 10, 11},
        1: {2, 7, 8, 10, 9, 11},
        2: {3, 10, 7, 9, 11},
        3: {4, 10, 9, 11},
        4: {5, 3, 10, 9, 11},
        5: {6, 4, 10, 9, 11},
        8: {9, 11},
        10: {1, 2, 3, 11, 9},
    }
    for current in range(12):
        for target in range(12):
            expected = target in allowed.get(current, set())
            current_name = [
                "discovered",
                "confirmed",
                "accepted",
                "implementing",
                "available",
                "verifying",
                "resolved",
                "duplicate",
                "rejected",
                "superseded",
                "deferred",
                "obsolete",
            ][current]
            target_name = [
                "discovered",
                "confirmed",
                "accepted",
                "implementing",
                "available",
                "verifying",
                "resolved",
                "duplicate",
                "rejected",
                "superseded",
                "deferred",
                "obsolete",
            ][target]
            assert (_validate_transition_shape(current_name, target_name) is None) == expected
