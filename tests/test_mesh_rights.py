"""Rights-backed distributed identity: provenance without promotion."""

from __future__ import annotations

import pytest

from mncs_commons.adapters.rights import independence_from_participant_assertion
from mncs_commons.mesh import DirectCarrier, compose_capsule, synchronize
from tests.test_commons import make_record
from tests.test_mesh_node import make_node, replication_record


def rights_assertion() -> dict:
    # Mirrors mncs-rights-provenance participant assertion v0.1; Commons
    # consumes the shape without importing the rights package.
    return {
        "assertionVersion": "mncs.rights.participant-assertion/v0.1",
        "evidenceId": "mncs-fabric://execution/rec-1",
        "evidenceDigest": "sha256:" + "a" * 64,
        "expectedDigest": "sha256:" + "a" * 64,
        "bindingOk": True,
        "producer": {
            "id": "mncs-fabric://execution/rec-1",
            "type": "mncs-fabric",
            "recordKind": "ExecutionEvidence",
            "schemaVersion": "0.1",
        },
        "subjectRefs": ["example/project#artifact"],
        "claimKinds": ["unknown-license-state"],
        "authority": "assertion-only; identity evidence, never permission or correctness",
    }


def test_independence_preserves_rights_assertion_verbatim():
    independence = independence_from_participant_assertion(
        rights_assertion(),
        mesh_native={"modelFamily": "family-b", "machine": "machine:b"},
    )
    assert independence["rightsAssertion"]["producerId"] == "mncs-fabric://execution/rec-1"
    assert independence["rightsAssertion"]["bindingOk"] is True
    assert independence["modelFamily"] == "family-b"
    # Commons invents no mesh-native dimensions from rights data.
    assert "provider" not in independence
    with pytest.raises(ValueError):
        independence_from_participant_assertion({"assertionVersion": "v9"})


def test_rights_backed_replication_syncs_without_promotion(tmp_path):
    """A rights-backed Replication crosses nodes; acceptance stays local."""

    node_a = make_node(tmp_path, "node-a")
    node_b = make_node(tmp_path, "node-b")
    claim = make_record("Claim")
    claim["metadata"]["recordId"] = "test:rights-claim"
    target = node_a.publish_local(claim).content_digest

    replication = replication_record(target, "PASS", "rights-b")
    replication["details"]["independence"] = independence_from_participant_assertion(
        rights_assertion(), mesh_native={"modelFamily": "family-b", "machine": "machine:b"}
    )
    replication["provenance"]["producer"] = {"type": "signed-agent", "id": "agent:node-b"}
    receipt = node_a.publish_local(replication)

    synchronize(node_b, DirectCarrier(node_a), push=False)
    stored = node_b.get_record(receipt.content_digest)
    assert stored is not None
    assert (
        stored["details"]["independence"]["rightsAssertion"]["evidenceId"]
        == "mncs-fabric://execution/rec-1"
    )
    # Rights-backed provenance is preserved AND acceptance is unchanged.
    assert node_b.store.lifecycle(receipt.content_digest, "project-a").current_state == "proposed"
    capsule = compose_capsule(stored)
    assert capsule["producer"]["id"] == "agent:node-b"
