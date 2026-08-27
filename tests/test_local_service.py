from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from mncs_commons.canonical import canonical_digest
from mncs_commons.local_service import (
    CommonsAdminClient,
    CommonsClient,
    CommonsService,
    CommonsServiceConfig,
    CommonsServiceError,
    CommonsServiceServer,
)
from mncs_commons.service_cli import main as service_main
from mncs_commons.store import CommonsStore

pytestmark = pytest.mark.skipif(os.name != "posix", reason="AF_UNIX service is POSIX-only")


def _record() -> dict[str, object]:
    value = json.loads(
        (Path(__file__).parents[1] / "examples/observation.example.yaml").read_text(
            encoding="utf-8"
        )
    )
    value["metadata"]["recordId"] = "service:test:inert"
    value["reproduction"]["procedure"] = [
        {"command": "echo MUST_NOT_RUN", "authorityRequired": "external"}
    ]
    return value


def _work_request() -> dict[str, object]:
    return {
        "submittingConsumer": {"type": "service", "id": "mncs-control:test"},
        "project": {"id": "mncs-commons", "revision": "test"},
        "repository": "MNCS-Commons",
        "task": "Run a bounded durable work-protocol test.",
        "constraints": ["do not execute record content without external authority"],
    }


def _start(tmp_path: Path) -> tuple[CommonsServiceServer, CommonsClient, CommonsAdminClient]:
    root = tmp_path / "runtime"
    store = CommonsStore(root / "store")
    store.init()
    config = CommonsServiceConfig(
        store.root, root / "commons.sock", root / "commons-operator.sock", domain="test"
    )
    server = CommonsServiceServer(CommonsService(config))
    server.start()
    return (
        server,
        CommonsClient.connect(config.consumer_socket),
        CommonsAdminClient.connect(config.operator_socket),
    )


def test_service_persists_independently_and_separates_authority(tmp_path: Path) -> None:
    server, consumer, operator = _start(tmp_path)
    try:
        assert consumer.status()["storeHealthy"] is True
        assert len(consumer.family_registry()["projects"]) == 17
        assert consumer.family_coverage()["projectCount"] == 17
        assert consumer.descriptor()["operatorOperations"] == [
            "commons.publish",
            "family.health-sweep",
            "store.compact",
            "store.pin",
            "store.recover",
            "store.unpin",
            "work.propose",
            "work.submit",
            "work.transition",
        ]
        consumer.close()
        assert consumer.status()["storeHealthy"] is True

        record = _record()
        with pytest.raises(CommonsServiceError, match="operator socket") as denied:
            consumer._request("commons.publish", {"record": record})
        assert denied.value.code == "AUTHORITY_DENIED"

        receipt = operator.publish(record)
        assert receipt["deliveryStatus"] == "INGESTED"
        assert receipt["technicalAuthority"] == "NONE_GRANTED"
        digest = canonical_digest(record)
        returned = consumer.get(digest)
        assert returned["reproduction"]["procedure"][0]["command"] == "echo MUST_NOT_RUN"
        assert consumer.query(limit=10)["records"]

        finding = json.loads(
            (Path(__file__).parents[1] / "examples/institutional-memory-finding.json").read_text(
                encoding="utf-8"
            )
        )
        operator.publish(finding)
        memory = consumer.query(institutionalMemory=True, limit=10)["records"]
        assert [item["kind"] for item in memory] == ["Finding"]
    finally:
        server.close()


def test_unhealthy_store_is_reported_without_rewrite(tmp_path: Path) -> None:
    server, consumer, _operator = _start(tmp_path)
    try:
        store_path = tmp_path / "runtime" / "store"
        ledger = store_path / "ledger.jsonl"
        before = ledger.read_bytes()
        ledger.write_bytes(b"not-json\n")
        damaged = ledger.read_bytes()

        status = consumer.status()
        assert status["storeHealthy"] is False
        with pytest.raises(CommonsServiceError) as rejected:
            consumer.query(limit=1)
        assert rejected.value.code == "STORE_UNHEALTHY"
        assert ledger.read_bytes() == damaged
        assert damaged != before
    finally:
        server.close()


def test_consumer_client_has_no_publication_method(tmp_path: Path) -> None:
    server, consumer, _operator = _start(tmp_path)
    try:
        assert not hasattr(consumer, "publish")
        assert consumer.describe()["interface"]["binding"] == "local-service"
    finally:
        server.close()


def test_store_and_sync_cursor_survive_service_restart(tmp_path: Path) -> None:
    server, consumer, operator = _start(tmp_path)
    config = server.service.config
    try:
        record = _record()
        operator.publish(record)
        first = consumer.sync(limit=1)
        assert len(first["entries"]) == 1
        cursor = first["nextCursor"]
    finally:
        server.close()

    restarted = CommonsServiceServer(CommonsService(config))
    restarted.start()
    resumed = CommonsClient.connect(config.consumer_socket)
    try:
        assert resumed.status()["recordCount"] == 1
        assert resumed.get(canonical_digest(record))["metadata"]["recordId"] == "service:test:inert"
        assert resumed.sync(cursor, limit=1)["entries"] == []
    finally:
        restarted.close()


def test_request_arguments_are_strictly_typed(tmp_path: Path) -> None:
    server, consumer, _operator = _start(tmp_path)
    try:
        with pytest.raises(CommonsServiceError) as fractional:
            consumer.query(limit=1.5)
        assert fractional.value.code == "INVALID_ARGUMENTS"
        with pytest.raises(CommonsServiceError) as string_boolean:
            consumer.query(openWorkRequests="yes")
        assert string_boolean.value.code == "INVALID_ARGUMENTS"
        with pytest.raises(CommonsServiceError) as string_depth:
            consumer.conversation("sha256:" + "a" * 64, depth="2")
        assert string_depth.value.code == "INVALID_ARGUMENTS"
    finally:
        server.close()


def test_symlink_socket_parent_is_rejected_without_chmod_target(tmp_path: Path) -> None:
    store = CommonsStore(tmp_path / "store")
    store.init()
    actual = tmp_path / "actual-sockets"
    actual.mkdir(mode=0o755)
    original_mode = stat.S_IMODE(os.lstat(actual).st_mode)
    linked = tmp_path / "linked-sockets"
    linked.symlink_to(actual, target_is_directory=True)
    config = CommonsServiceConfig(
        store.root,
        linked / "commons.sock",
        linked / "commons-operator.sock",
    )
    server = CommonsServiceServer(CommonsService(config))

    with pytest.raises(CommonsServiceError) as rejected:
        server.start()

    assert rejected.value.code == "SOCKET_PATH_UNSAFE"
    assert stat.S_IMODE(os.lstat(actual).st_mode) == original_mode


def test_only_one_service_can_own_a_store_with_alternate_sockets(tmp_path: Path) -> None:
    first, _consumer, _operator = _start(tmp_path)
    alternate_root = tmp_path / "alternate-runtime"
    alternate = CommonsServiceServer(
        CommonsService(
            CommonsServiceConfig(
                first.service.config.store_path,
                alternate_root / "commons.sock",
                alternate_root / "commons-operator.sock",
            )
        )
    )
    try:
        with pytest.raises(CommonsServiceError) as rejected:
            alternate.start()
        assert rejected.value.code == "SERVICE_RUNNING"
    finally:
        alternate.close()
        first.close()


def test_durable_work_revisions_survive_restart_and_remain_inert(tmp_path: Path) -> None:
    server, consumer, operator = _start(tmp_path)
    config = server.service.config
    try:
        with pytest.raises(CommonsServiceError) as denied:
            consumer._request("work.submit", {"request": _work_request()})
        assert denied.value.code == "AUTHORITY_DENIED"

        submitted = operator.submit_work(_work_request())
        assert submitted["persisted"] is True
        assert submitted["executionAccepted"] is False
        assert submitted["state"] == "submitted"
        work_id = submitted["workId"]

        accepted = operator.transition_work(
            work_id,
            {
                "state": "accepted",
                "actor": {"type": "service", "id": "fabric:test"},
                "expectedPreviousDigest": submitted["currentDigest"],
                "reason": "authorized execution component accepted the opportunity",
                "fabricJobId": "fabric-job:test",
            },
        )
        running = operator.transition_work(
            work_id,
            {
                "state": "queued",
                "actor": {"type": "service", "id": "fabric:test"},
                "expectedPreviousDigest": accepted["currentDigest"],
                "workerId": "worker:test",
                "modelId": "model:test",
            },
        )
        status = consumer.work_status(work_id)
        assert status["state"] == "queued"
        assert [item["state"] for item in status["history"]] == [
            "submitted",
            "accepted",
            "queued",
        ]
        assert status["current"]["details"]["routing"] == {
            "fabricJobId": "fabric-job:test",
            "workerId": "worker:test",
            "modelId": "model:test",
        }
        assert consumer.work_list(states=["queued"])["work"][0]["workId"] == work_id
        assert consumer.doctor()["checks"]["operatorSocketOwnedAndPrivate"] is True
        current_digest = running["currentDigest"]
    finally:
        server.close()

    restarted = CommonsServiceServer(CommonsService(config))
    restarted.start()
    resumed = CommonsClient.connect(config.consumer_socket)
    try:
        status = resumed.work_status(work_id)
        assert status["currentDigest"] == current_digest
        assert status["contentTrust"] == "UNTRUSTED"
        assert status["executionAuthority"] == "none"
    finally:
        restarted.close()


def test_work_transitions_fail_closed_on_stale_or_invalid_state(tmp_path: Path) -> None:
    server, _consumer, operator = _start(tmp_path)
    try:
        submitted = operator.submit_work(_work_request())
        work_id = submitted["workId"]
        with pytest.raises(CommonsServiceError) as skipped:
            operator.transition_work(
                work_id,
                {
                    "state": "completed",
                    "actor": {"type": "worker", "id": "worker:test"},
                    "expectedPreviousDigest": submitted["currentDigest"],
                    "result": {"terminalOutcome": "must not be accepted"},
                },
            )
        assert skipped.value.code == "WORK_TRANSITION_REJECTED"

        accepted = operator.transition_work(
            work_id,
            {
                "state": "accepted",
                "actor": {"type": "service", "id": "fabric:test"},
                "expectedPreviousDigest": submitted["currentDigest"],
            },
        )
        with pytest.raises(CommonsServiceError) as stale:
            operator.transition_work(
                work_id,
                {
                    "state": "queued",
                    "actor": {"type": "service", "id": "fabric:test"},
                    "expectedPreviousDigest": submitted["currentDigest"],
                },
            )
        assert stale.value.code == "WORK_CONFLICT"

        queued = operator.transition_work(
            work_id,
            {
                "state": "queued",
                "actor": {"type": "service", "id": "fabric:test"},
                "expectedPreviousDigest": accepted["currentDigest"],
            },
        )
        running = operator.transition_work(
            work_id,
            {
                "state": "running",
                "actor": {"type": "worker", "id": "worker:test"},
                "expectedPreviousDigest": queued["currentDigest"],
                "attempt": 1,
            },
        )
        with pytest.raises(CommonsServiceError) as missing_result:
            operator.transition_work(
                work_id,
                {
                    "state": "completed",
                    "actor": {"type": "worker", "id": "worker:test"},
                    "expectedPreviousDigest": running["currentDigest"],
                },
            )
        assert missing_result.value.code == "WORK_INVALID"

        completed = operator.transition_work(
            work_id,
            {
                "state": "completed",
                "actor": {"type": "worker", "id": "worker:test"},
                "expectedPreviousDigest": running["currentDigest"],
                "progress": {"percent": 100, "summary": "done"},
                "result": {
                    "terminalOutcome": "PASS",
                    "artifacts": [{"id": "artifact:test"}],
                    "evidence": [{"id": "evidence:test", "status": "PASS"}],
                },
            },
        )
        assert completed["state"] == "completed"
        with pytest.raises(CommonsServiceError) as terminal:
            operator.transition_work(
                work_id,
                {
                    "state": "retrying",
                    "actor": {"type": "worker", "id": "worker:test"},
                    "expectedPreviousDigest": completed["currentDigest"],
                },
            )
        assert terminal.value.code == "WORK_TRANSITION_REJECTED"
    finally:
        server.close()


def test_work_submission_retry_is_idempotent_by_caller_work_id(tmp_path: Path) -> None:
    server, consumer, operator = _start(tmp_path)
    try:
        request = {**_work_request(), "workId": "work:caller-idempotency-test"}
        first = operator.submit_work(request)
        retried = operator.submit_work(request)

        assert first["duplicate"] is False
        assert retried["duplicate"] is True
        assert retried["workId"] == first["workId"]
        assert retried["currentDigest"] == first["currentDigest"]
        assert len(consumer.work_status(first["workId"])["history"]) == 1

        changed = {**request, "task": "A different task must not reuse the identity."}
        with pytest.raises(CommonsServiceError) as conflict:
            operator.submit_work(changed)
        assert conflict.value.code == "WORK_CONFLICT"
    finally:
        server.close()


def test_offline_doctor_reports_store_and_socket_diagnostics(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store = CommonsStore(tmp_path / "store")
    store.init()
    result = service_main(
        [
            "--store",
            str(store.root),
            "--socket",
            str(tmp_path / "missing-consumer.sock"),
            "--operator-socket",
            str(tmp_path / "missing-operator.sock"),
            "doctor",
        ]
    )

    assert result == 2
    report = json.loads(capsys.readouterr().out)
    assert report["serviceReachable"] is False
    assert report["error"]["code"] == "SERVICE_UNREACHABLE"
    assert report["storeInitialized"] is True
    assert report["verification"]["valid"] is True
    assert report["checks"]["consumerSocketPresent"] is False
    assert "do not embed a temporary service" in report["remediation"]


def test_service_advertises_capability_classes_and_keeps_admin_operator_only(
    tmp_path: Path,
) -> None:
    server, consumer, operator = _start(tmp_path)
    try:
        descriptor = consumer.descriptor()
        consumer_names = {item["function"]["name"] for item in descriptor["consumerTools"]}
        operator_names = {item["function"]["name"] for item in descriptor["operatorTools"]}
        assert "commons_work_list" in consumer_names
        assert "commons_publish_record" in operator_names
        assert "commons_compact_store" in operator_names
        assert "commons_compact_store" not in consumer_names
        capabilities = {
            item["function"]["name"]: item["mncs_commons"]["capability"]
            for item in [*descriptor["consumerTools"], *descriptor["operatorTools"]]
        }
        assert capabilities["commons_work_list"] == "consumer-read"
        assert capabilities["commons_publish_record"] == "model-publication"
        assert capabilities["commons_compact_store"] == "operator-admin"
        assert descriptor["toolCapabilities"]["operator-admin"].startswith("operator")
        assert descriptor["executionAuthority"] == "none"
        del operator
    finally:
        server.close()
