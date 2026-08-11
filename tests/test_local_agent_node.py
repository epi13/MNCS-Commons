from __future__ import annotations

import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
from threading import Event

from mncs_commons.adapters.fabric import from_fabric_execution
from mncs_commons.application import CommonsApplication
from mncs_commons.canonical import canonical_digest
from mncs_commons.exchange import ParticipantDescriptor
from mncs_commons.store import CommonsStore

ROOT = Path(__file__).parents[1]


def _load(name: str) -> dict[str, object]:
    return json.loads((ROOT / "examples" / name).read_text(encoding="utf-8"))


def test_local_profile_and_operator_workflow_are_machine_readable(tmp_path: Path) -> None:
    store_path = tmp_path / "commons"
    missing = CommonsApplication(CommonsStore(store_path)).local_status()
    assert missing["initialized"] is False
    assert missing["executionAuthority"] == "none"

    store = CommonsStore(store_path)
    store.init()
    application = CommonsApplication(store)
    status = application.local_status(domain="controller:test")
    assert status["verification"]["valid"] is True
    assert status["trustDomain"] == "controller:test"
    assert application.local_doctor()["valid"] is True

    completed = subprocess.run(
        [sys.executable, "-m", "mncs_commons.cli", "local", "doctor", str(store_path)],
        cwd=ROOT,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert completed.returncode == 0
    assert json.loads(completed.stdout)["valid"] is True


def test_descriptor_operations_and_participant_provenance_are_additive() -> None:
    descriptor = CommonsApplication.describe(binding="stdio-mcp")
    assert descriptor["serviceDescriptorVersion"] == "commons.mncs.dev/service/v0alpha1"
    assert descriptor["profile"]["executionAuthority"] == "none"
    assert descriptor["interface"]["binding"] == "stdio-mcp"
    assert "record.publish" in descriptor["interface"]["operations"]
    assert "lifecycle.get" not in descriptor["interface"]["operations"]

    participant = ParticipantDescriptor(
        "agent:a",
        "harness",
        "1.0",
        "provider:a",
        "instance:a",
        ("commons.query",),
        "controller",
        "model:a",
        "session:a",
        "producer:a",
        "environment:a",
    )
    assert participant.as_dict()["identityAssurance"] == "SELF_ASSERTED"
    assert participant.as_dict()["sessionId"] == "session:a"


def test_mcp_module_entrypoint_starts_the_stdio_server(tmp_path: Path) -> None:
    store_path = tmp_path / "commons"
    CommonsStore(store_path).init()
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-11-25",
            "capabilities": {},
            "clientInfo": {"name": "commons-entrypoint-test", "version": "1"},
        },
    }
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "mncs_commons.mcp_server",
            "--store",
            str(store_path),
            "--domain",
            "test",
        ],
        cwd=ROOT,
        input=json.dumps(request) + "\n",
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=5,
    )
    assert completed.returncode == 0
    response = json.loads(completed.stdout.splitlines()[0])
    assert response["result"]["serverInfo"]["name"] == "mncs-commons"


def test_fabric_push_translation_keeps_source_outcome_separate(tmp_path: Path) -> None:
    source = json.loads(
        (ROOT / "compat/fabric/execution-record-v0.1.json").read_text(encoding="utf-8")
    )
    translated = from_fabric_execution(
        source, subject_identity="artifact:test", created_at="2026-08-10T00:00:00Z"
    )
    assert translated.valid
    record = translated.record
    assert record is not None
    assert record["details"]["sourceOutcome"] == "PASS"
    assert record["details"]["claimVerificationStatus"] == "UNKNOWN"

    store = CommonsStore(tmp_path / "store")
    store.init()
    result = CommonsApplication(store).ingest_adapter_result(translated, publish=True)
    assert result["published"] is True
    assert result["receipt"]["acceptanceStatus"] == "UNCHANGED"


def test_fabric_translation_uses_current_execution_start_timestamp() -> None:
    source = json.loads(
        (ROOT / "compat/fabric/execution-record-v0.1.json").read_text(encoding="utf-8")
    )
    source.pop("created_at", None)
    source["started_at"] = "2026-08-10T00:00:00Z"
    translated = from_fabric_execution(source, subject_identity="artifact:test")
    assert translated.valid
    assert translated.record is not None
    assert translated.record["metadata"]["createdAt"] == "2026-08-10T00:00:00Z"


def test_participant_metadata_does_not_enter_record_identity(tmp_path: Path) -> None:
    store = CommonsStore(tmp_path / "store")
    store.init()
    record = _load("work-request.json")
    expected = canonical_digest(record)
    application = CommonsApplication(store)
    receipt = application.publish(
        deepcopy(record),
        participant=ParticipantDescriptor("agent:a", "impl", session_id="session:1"),
    )
    assert receipt["contentDigest"] == expected
    assert (
        application.get_record(expected)["metadata"]["recordId"]
        == record["metadata"]["recordId"]
    )


def test_small_local_concurrency_allows_readers_and_competing_writers(tmp_path: Path) -> None:
    store_path = tmp_path / "store"
    CommonsStore(store_path).init()

    def publish(index: int) -> str:
        record = _load("work-request.json")
        record["metadata"] = dict(record["metadata"])
        record["metadata"]["recordId"] = f"commons:request:concurrent:{index}"
        return CommonsApplication(CommonsStore(store_path)).publish(record)["contentDigest"]

    with ThreadPoolExecutor(max_workers=4) as executor:
        digests = list(executor.map(publish, range(8)))
    assert len(set(digests)) == 8

    def read(_: int) -> int:
        return len(CommonsStore(store_path).records())

    with ThreadPoolExecutor(max_workers=2) as executor:
        counts = list(executor.map(read, range(4)))
    assert counts == [8, 8, 8, 8]
    assert CommonsStore(store_path).verify().valid


def test_reader_during_staged_write_sees_bounded_store_state(
    tmp_path: Path, monkeypatch
) -> None:
    store_path = tmp_path / "store"
    CommonsStore(store_path).init()
    started = Event()
    release = Event()
    original_append = CommonsStore._append_row

    def delayed_append(store: CommonsStore, row: dict[str, object]) -> None:
        started.set()
        if not release.wait(2):
            raise TimeoutError("test writer was not released")
        original_append(store, row)

    monkeypatch.setattr(CommonsStore, "_append_row", delayed_append)
    record = _load("work-request.json")
    record["metadata"] = dict(record["metadata"])
    record["metadata"]["recordId"] = "commons:request:reader-during-write"
    with ThreadPoolExecutor(max_workers=2) as executor:
        writer = executor.submit(CommonsStore(store_path).add_record, record)
        assert started.wait(2)
        assert CommonsStore(store_path).records() == []
        release.set()
        writer.result()
    assert len(CommonsStore(store_path).records()) == 1
