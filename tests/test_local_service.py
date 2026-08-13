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
        assert consumer.descriptor()["operatorOperations"] == [
            "commons.publish",
            "store.recover",
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
    assert stat.S_IMODE(os.lstat(actual).st_mode) == 0o755


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
