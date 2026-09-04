"""Mesh scenarios A-D: two nodes, disagreement, offline, selective sync."""

from __future__ import annotations

import pytest

from mncs_commons.mesh import (
    CommonsNode,
    DirectCarrier,
    InterestFilter,
    MeshError,
    negotiate,
    synchronize,
)
from tests.test_commons import make_event, make_record


def make_node(tmp_path, name, domain="project-a"):
    node = CommonsNode(tmp_path / name, node_id=name, domain=domain)
    node.init()
    return node


def claim_record(suffix="x", project="proj-ptx"):
    record = make_record("Claim")
    record["metadata"]["recordId"] = f"test:claim:{suffix}"
    record["scope"]["context"]["project"] = project
    record["details"] = {"outcome": "UNKNOWN", "falsifier": f"counterexample {suffix}"}
    return record


def replication_record(target, outcome, identity):
    record = make_record("Replication")
    record["metadata"]["recordId"] = f"test:replication:{identity}"
    record["scope"]["context"]["project"] = "proj-ptx"
    record["details"] = {
        "targetRecord": target,
        "outcome": outcome,
        "independence": {
            "modelFamily": f"family-{identity}",
            "promptSource": "sha256:" + "b" * 64,
            "harness": "sha256:" + "c" * 64,
            "compiler": "clang-18",
            "machine": f"machine:{identity}",
            "provider": "provider:test",
            "artifactAncestry": ["sha256:" + "d" * 64],
        },
    }
    record["relationships"] = [{"type": "replicates", "target": target}]
    return record


def test_scenario_a_two_independent_nodes(tmp_path):
    """A publishes Claim X; B learns X via sync and gains no authority."""

    node_a = make_node(tmp_path, "node-a")
    node_b = make_node(tmp_path, "node-b")
    receipt = node_a.publish_local(claim_record("x"))
    assert receipt.origin == "local"
    assert receipt.content_digest not in node_b.frontier()

    result = synchronize(node_b, DirectCarrier(node_a), push=False)
    assert result["pull"]["received"] == 1
    assert receipt.content_digest in node_b.frontier()

    # B knows X exists; B's lifecycle view is untouched (still proposed),
    # and no authority leaked across the transfer.
    assert node_b.origin_of(receipt.content_digest) == "foreign:node-a"
    view = node_b.store.lifecycle(receipt.content_digest, "project-a")
    assert view.current_state == "proposed"
    assert result["pull"]["peer"] == "node-a"


def test_scenario_b_independent_replication_coexists(tmp_path):
    """PASS and FAIL replications of one claim coexist; nothing deletes."""

    node_a = make_node(tmp_path, "node-a")
    node_b = make_node(tmp_path, "node-b")
    node_c = make_node(tmp_path, "node-c")
    claim = claim_record("x")
    claim_receipt = node_a.publish_local(claim)
    target = claim_receipt.content_digest

    synchronize(node_b, DirectCarrier(node_a), push=False)
    synchronize(node_c, DirectCarrier(node_a), push=False)
    receipt_b = node_b.publish_local(replication_record(target, "PASS", "b"))
    receipt_c = node_c.publish_local(replication_record(target, "FAIL", "c"))

    synchronize(node_a, DirectCarrier(node_b), push=False)
    synchronize(node_a, DirectCarrier(node_c), push=False)

    assert target in node_a.frontier()
    assert receipt_b.content_digest in node_a.frontier()
    assert receipt_c.content_digest in node_a.frontier()

    # Local projections may differ per domain while the record set converges.
    # (make_event carries authority domain "commons:test-domain".)
    node_a.store.add_event(make_event(target, "proposed", "reproduced"))
    node_a.store.add_event(make_event(target, "reproduced", "verified"))
    assert node_a.store.lifecycle(target, "commons:test-domain").current_state == "verified"
    assert node_a.store.lifecycle(target, "project-a").current_state == "proposed"
    assert node_b.store.lifecycle(target, "commons:test-domain").current_state == "proposed"


def test_scenario_c_offline_work_converges_without_ordering(tmp_path):
    """Disconnected nodes create records, reconnect, and converge."""

    node_a = make_node(tmp_path, "node-a")
    node_b = make_node(tmp_path, "node-b")
    receipt_a = node_a.publish_local(claim_record("offline-a"))
    receipt_b = node_b.publish_local(claim_record("offline-b"))

    # No global sequence number exists anywhere in the mesh protocol.
    assert "sequence" not in node_a.describe()
    assert "GLOBAL_SEQUENCE" not in repr(node_a.describe())

    synchronize(node_a, DirectCarrier(node_b))
    synchronize(node_b, DirectCarrier(node_a))
    assert node_a.frontier() == node_b.frontier()
    assert receipt_a.content_digest in node_b.frontier()
    assert receipt_b.content_digest in node_a.frontier()


def test_scenario_d_selective_replication(tmp_path):
    """B subscribes to one project and never receives unrelated records."""

    node_a = make_node(tmp_path, "node-a")
    node_b = make_node(tmp_path, "node-b")
    wanted = node_a.publish_local(claim_record("wanted", project="proj-ptx"))
    other = node_a.publish_local(claim_record("other", project="proj-unrelated"))

    interest = InterestFilter.from_mapping({"projects": ["proj-ptx"]})
    result = synchronize(node_b, DirectCarrier(node_a), interest=interest, push=False)
    assert wanted.content_digest in node_b.frontier()
    assert other.content_digest not in node_b.frontier()
    assert result["pull"]["skippedByInterest"] == 1

    # An explicit digest allowlist still reaches through the filter.
    rescue = InterestFilter.from_mapping(
        {"projects": ["proj-ptx"], "recordIds": [other.content_digest]}
    )
    result = synchronize(node_b, DirectCarrier(node_a), interest=rescue, push=False)
    assert other.content_digest in node_b.frontier()


def test_negotiation_is_bounded_and_inert(tmp_path):
    node_a = make_node(tmp_path, "node-a")
    agreement = negotiate(
        __import__("mncs_commons.mesh", fromlist=["NodeDescriptor"]).NodeDescriptor.from_mapping(
            node_a.describe()
        ),
        node_a.describe(),
    )
    assert agreement["canExchange"] is True
    assert "direct" in agreement["agreedSyncModes"]

    hostile = dict(node_a.describe())
    hostile["relationshipVocabulary"] = ["supports", "mind-control"]
    hostile["syncModes"] = ["telepathy"]
    with pytest.raises(MeshError):
        negotiate(
            __import__(
                "mncs_commons.mesh", fromlist=["NodeDescriptor"]
            ).NodeDescriptor.from_mapping(node_a.describe()),
            hostile,
        )


def test_push_path_shares_local_records(tmp_path):
    node_a = make_node(tmp_path, "node-a")
    node_b = make_node(tmp_path, "node-b")
    receipt = node_b.publish_local(claim_record("push"))
    result = synchronize(node_b, DirectCarrier(node_a), push=True)
    assert result["push"]["sent"] == 1
    assert receipt.content_digest in node_a.frontier()
    assert node_a.origin_of(receipt.content_digest) == "foreign:node-b"
