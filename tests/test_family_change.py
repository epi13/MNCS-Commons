from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LANGUAGE_ROOT = ROOT.parent / "mncs-language"

sys.path.insert(0, str(ROOT / "src"))

from mncs_commons.family_change import (  # noqa: E402
    FamilyChangeError,
    change_core,
    change_identity,
    validate_contributor,
    validate_family_change,
    validate_family_generation,
    validate_reconciliation,
)


def _change(**overrides):
    record = {
        "schema_version": "mncs.family-change/1",
        "producer": {"repository": "mncs-language", "checkout_kind": "worktree",
                    "session": "ses_producer", "consumer": "agent-a",
                    "claim_id": "clm-1"},
        "base": {"head": "a" * 40, "generation": 7},
        "state": "draft",
        "supersedes": [],
        "subjects": [{"identity": "mncs.std.sha256",
                      "kind": "module",
                      "paths": ["library/std/sha256.mncs"]}],
        "contracts_changed": [{"contract": "mncs.std.sha256.v1",
                               "from": "rev-1", "to": "rev-2"}],
        "operations": [{"op": "set_json_field",
                        "params": {"field": "revision", "to": "rev-2"},
                        "paths": [".mncs/project.json"],
                        "preimage": {".mncs/project.json": "sha256:old"}}],
        "evidence_refs": {"diff": "ev:diff-1", "coordination_changesets": []},
        "verification": {"state": "unknown", "obligations": ["ob-1"]},
        "intent": {"summary": "move sha256 ownership", "migration_id": "m-1"},
    }
    record.update(overrides)
    validated_shape = dict(record)
    validated_shape["producer"] = {
        "repository": "mncs-language", "checkout_kind": "worktree",
        "session": "ses_producer", "consumer": "agent-a", "claim_id": "clm-1"}
    record["identity"] = change_identity(change_core(validated_shape))
    return record


def test_valid_change_passes_and_binds_identity() -> None:
    validated = validate_family_change(_change())
    assert validated["identity"].startswith("fc:")
    assert validated["state"] == "draft"


def test_identity_mismatch_refuses() -> None:
    record = _change()
    record["intent"] = {"summary": "tampered", "migration_id": "m-1"}
    with pytest.raises(FamilyChangeError):
        validate_family_change(record)


def test_unknown_state_refuses() -> None:
    record = _change(state="published-by-wish")
    with pytest.raises(FamilyChangeError):
        validate_family_change(record)


def test_unknown_operation_refuses() -> None:
    record = _change()
    record["operations"] = [{"op": "rewrite_everything", "params": {},
                             "paths": [], "preimage": {}}]
    with pytest.raises(FamilyChangeError):
        validate_family_change(record)


def test_bounds_refuse() -> None:
    record = _change()
    record["subjects"] = [{"identity": f"s-{i}", "kind": "k", "paths": []}
                          for i in range(33)]
    with pytest.raises(FamilyChangeError):
        validate_family_change(record)


def test_contributor_generation_and_reconciliation_shapes() -> None:
    contributor = validate_contributor({
        "schema_version": "mncs.family-contributor/1",
        "session": "ses-a", "consumer": "agent-a", "workspaces": ["w"],
        "active_changes": [], "claims": [], "generation": 3,
        "updated_at": "2026-10-02T00:00:00+00:00"})
    assert contributor["generation"] == 3
    generation = validate_family_generation({
        "schema_version": "mncs.family-generation/1",
        "projects": {"mncs-language": {"generation": 9, "head": "b" * 40,
                                      "change": "fc:x"}},
        "cursor": 12})
    assert generation["projects"]["mncs-language"]["generation"] == 9
    row = validate_reconciliation({
        "schema_version": "mncs.family-reconciliation/1",
        "change": "fc:x", "consumer": "mncs-test",
        "consumer_class": "reconcilable", "observed_generation": 7,
        "canonical_generation": 9, "repair_state": "no_repair",
        "attempts": 0, "detail": "", "evidence_ref": ""})
    assert row["consumer_class"] == "reconcilable"


def test_reconciliation_rejects_unknown_class() -> None:
    with pytest.raises(FamilyChangeError):
        validate_reconciliation({
            "schema_version": "mncs.family-reconciliation/1",
            "change": "fc:x", "consumer": "mncs-test",
            "consumer_class": "eventually-consistent"})


def test_native_family_change_laws_are_executable() -> None:
    mncs = Path(os.environ.get("MNCS_BINARY", LANGUAGE_ROOT / "target/debug/mncs"))
    if not mncs.is_file():
        pytest.skip("mncs toolchain binary unavailable")
    library = Path(os.environ.get("MNCS_LIBRARY_ROOT", LANGUAGE_ROOT / "library"))
    if not library.is_dir():
        pytest.skip("mncs language library unavailable")
    environment = dict(os.environ)
    environment["MNCS_LIBRARY_PATH"] = ":".join(
        [str(library), str(ROOT / "src/mncs_commons/mesh")]
    )
    completed = subprocess.run(
        [str(mncs), "call",
         str(ROOT / "tests/fixtures/native-family-change-probe.mncs"),
         "--module", "tests.native_family_change_probe",
         "--function", "all", "--args-json", "[]",
         "--library", str(library),
         "--library", str(ROOT / "src/mncs_commons/mesh")],
        cwd=ROOT, env=environment, capture_output=True, text=True,
        check=False, timeout=180)
    assert completed.returncode == 0, completed.stderr or completed.stdout
    report = json.loads(completed.stdout)
    fields = dict(report["call"]["returned"][0]["record"]["fields"])
    failed = [name for name, value in sorted(fields.items())
              if value != {"boolean": {"value": True}}]
    assert not failed, failed
    assert len(fields) == 44


def test_native_family_classification_batch_preserves_order_and_scalar_law():
    mncs = Path(os.environ.get("MNCS_BINARY", LANGUAGE_ROOT / "target/debug/mncs"))
    if not mncs.is_file():
        pytest.skip("mncs toolchain unavailable")
    rows = [[0, 1, 0, 0, 0, 1, 1, 1], [1, 0, 0, 0, 0, 1, 1, 1],
            [1, 1, 0, 0, 0, 1, 1, 1], [1, 1, 0, 1, 0, 1, 1, 1]]
    args = [{"sequence": {"values": [{"sequence": {"values": [
        {"integer": {"value": value}} for value in row]}} for row in rows]}}]
    result = subprocess.run([str(mncs), "call", str(ROOT / "src/mncs_commons/mesh/mncs/commons/family/change.mncs"),
        "--module", "mncs.commons.family.change.v1", "--function", "classify_consumers",
        "--args-json", json.dumps(args)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    values = json.loads(result.stdout)["call"]["returned"][0]["sequence"]["values"]
    assert [item["integer"]["value"] for item in values] == [0, 7, 1, 3]
