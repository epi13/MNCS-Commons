from __future__ import annotations

import json
from pathlib import Path

import pytest

from mncs_commons.bootstrap import seed_public
from mncs_commons.http_server import PublicNodeApplication, PublicNodeConfig, PublicNodeLimits
from mncs_commons.remote import RemoteClient
from mncs_commons.visibility import VisibilityPolicy


def test_public_configuration_fails_closed_for_direct_or_plain_public_urls(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="direct public"):
        PublicNodeConfig(
            tmp_path,
            bind="0.0.0.0",
            mode="anonymous-public",
            base_url="https://commons.example",
        ).validate()
    with pytest.raises(ValueError, match="HTTPS"):
        PublicNodeConfig(
            tmp_path,
            mode="anonymous-public",
            base_url="http://commons.example",
        ).validate()


def test_public_descriptor_advertises_limits_and_no_client_auth(tmp_path: Path) -> None:
    from mncs_commons.store import CommonsStore

    CommonsStore(tmp_path).init()
    app = PublicNodeApplication(
        PublicNodeConfig(
            tmp_path,
            mode="anonymous-public",
            base_url="http://127.0.0.1:8090",
            allow_insecure_external_url=True,
            limits=PublicNodeLimits(max_query_results=7),
        )
    )
    descriptor = app._descriptor()
    assert descriptor["participantIdentity"] == {
        "assertion": "SELF_ASSERTED",
        "authenticated": False,
        "technicalAuthority": "NONE_GRANTED",
    }
    assert descriptor["limits"]["maxQueryResults"] == 7
    assert descriptor["serverMode"] == "anonymous-public"


def test_visibility_overlay_is_operator_local_and_atomic(tmp_path: Path) -> None:
    path = tmp_path / "visibility.json"
    policy = VisibilityPolicy(path)
    policy.set_withheld("sha256:" + "a" * 64, "operator review")
    loaded = VisibilityPolicy(path)
    assert not loaded.is_visible("sha256:" + "a" * 64)
    assert loaded.reason("sha256:" + "a" * 64) == "operator review"
    loaded.clear("sha256:" + "a" * 64)
    assert loaded.entries() == {}
    assert json.loads(path.read_text(encoding="utf-8"))["withheld"] == {}


def test_seeded_public_records_remain_proposed_and_bounded(tmp_path: Path) -> None:
    result = seed_public(tmp_path)
    assert result["count"] == 3
    assert all(item["acceptanceStatus"] == "UNCHANGED" for item in result["seeded"])
    assert (
        PublicNodeApplication(
            PublicNodeConfig(
                tmp_path,
                mode="anonymous-public",
                base_url="http://127.0.0.1:8090",
                allow_insecure_external_url=True,
            )
        ).store.storage_usage()["ledgerEntries"]
        == 3
    )


def test_remote_client_requires_explicit_plain_http_and_rejects_url_credentials() -> None:
    with pytest.raises(ValueError, match="HTTPS"):
        RemoteClient("http://127.0.0.1:8090")
    with pytest.raises(ValueError, match="credentials"):
        RemoteClient("https://user:secret@example.test")
