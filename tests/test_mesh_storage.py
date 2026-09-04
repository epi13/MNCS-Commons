"""Storage economics: execution volume must not drive distributed growth."""

from __future__ import annotations

from mncs_commons.canonical import canonical_json
from mncs_commons.mesh import (
    CommonsNode,
    DirectCarrier,
    InterestFilter,
    account_node,
    check_budgets,
    synchronize,
)
from tests.test_commons import make_record
from tests.test_mesh_node import claim_record


def make_node(tmp_path, name):
    node = CommonsNode(tmp_path / name, node_id=name, domain="project-a")
    node.init()
    return node


def exhaust_observation(index: int) -> dict:
    record = make_record("Observation")
    record["metadata"]["recordId"] = f"test:exhaust:{index}"
    record["scope"]["context"]["project"] = "proj-fleet"
    record["details"] = {
        "outcome": "UNKNOWN",
        "measurements": {"iteration": index, "logBytes": 4096},
    }
    record["statement"] = {
        "summary": f"Routine execution exhaust {index}.",
        "details": "Disposable by default; promotion makes knowledge.",
    }
    return record


def test_large_execution_volume_stays_local(tmp_path):
    """200 routine observations + 3 findings: only findings are exchanged."""

    node_a = make_node(tmp_path, "node-a")
    node_b = make_node(tmp_path, "node-b")

    generated_bytes = 0
    for index in range(200):
        record = exhaust_observation(index)
        generated_bytes += len(canonical_json(record))
        node_a.publish_local(record)
    finding_digests = []
    for index in range(3):
        finding = make_record("Finding")
        finding["metadata"]["recordId"] = f"test:finding:{index}"
        finding["scope"]["context"]["project"] = "proj-fleet"
        finding_digests.append(node_a.publish_local(finding).content_digest)

    assert len(node_a.frontier()) == 203

    # B subscribes to knowledge (findings/claims), not exhaust.
    interest = InterestFilter.from_mapping({"kinds": ["Finding", "Claim"]})
    result = synchronize(node_b, DirectCarrier(node_a), interest=interest, push=False)

    assert result["pull"]["received"] == 3
    assert result["pull"]["skippedByInterest"] == 200
    for digest in finding_digests:
        assert digest in node_b.frontier()

    exchanged = result["pull"]["bytesReceived"]
    # The network moved ~3 compact records, not ~203 generated records.
    assert exchanged < generated_bytes // 10

    account_a = account_node(node_a)
    account_b = account_node(node_b, exchanged_bytes=exchanged)
    assert account_a.content_files == 203
    assert account_b.content_files == 3
    assert dict(account_b.records_by_kind) == {"Finding": 3}

    budgets = check_budgets(node_b, account_b)
    assert budgets["withinBudgets"] is True


def test_evidence_bytes_stay_source_local_until_requested(tmp_path):
    """A 5 MB evidence blob is referenced by 3 nodes but stored once."""

    node_a = make_node(tmp_path, "node-a")
    node_b = make_node(tmp_path, "node-b")
    node_c = make_node(tmp_path, "node-c")
    blob = b"V" * (5 * 1024 * 1024)
    digest = node_a.cas_put(blob, media_type="application/x-verify")

    finding = make_record("Finding")
    finding["metadata"]["recordId"] = "test:big-evidence"
    finding["evidence"] = [
        {
            "id": digest,
            "relation": "supports",
            "status": "PASS",
            "availability": "SOURCE_AVAILABLE",
            "sizeBytes": len(blob),
            "mediaType": "application/x-verify",
        }
    ]
    receipt = node_a.publish_local(finding)
    synchronize(node_b, DirectCarrier(node_a), push=False)
    synchronize(node_c, DirectCarrier(node_b), push=False)

    assert receipt.content_digest in node_c.frontier()
    assert node_a.cas_has(digest)
    assert not node_b.cas_has(digest)
    assert not node_c.cas_has(digest)
    total_cas = (
        account_node(node_a).cas_bytes
        + account_node(node_b).cas_bytes
        + account_node(node_c).cas_bytes
    )
    assert total_cas == len(blob)


def test_hot_budget_violation_is_reported_not_hidden(tmp_path):
    from mncs_commons.mesh import MeshPolicy

    tiny = MeshPolicy(hot_byte_budget=1024)
    node = CommonsNode(tmp_path / "node-a", node_id="node-a", policy=tiny)
    node.init()
    node.publish_local(claim_record("over-budget"))
    report = check_budgets(node, account_node(node))
    assert report["withinBudgets"] is False
    assert report["budgets"]["hotByteBudget"] is False
