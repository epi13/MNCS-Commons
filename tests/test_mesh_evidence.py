"""Mesh scenarios E-F: lazy evidence and explicit availability."""

from __future__ import annotations

from mncs_commons.mesh import (
    BundleCarrier,
    CommonsNode,
    DirectCarrier,
    EvidenceAvailability,
    EvidenceReference,
    InterestFilter,
    annotation_from_evidence_entry,
    assess_capsule,
    compose_capsule,
    merge_availability,
    synchronize,
)
from mncs_commons.models import RecordKind, RelationType
from tests.test_commons import make_record


def make_node(tmp_path, name):
    node = CommonsNode(tmp_path / name, node_id=name, domain="project-a")
    node.init()
    return node


def claim_with_evidence(suffix, evidence_id, *, size=250_000_000):
    record = make_record("Finding")
    record["metadata"]["recordId"] = f"test:finding:{suffix}"
    record["scope"]["context"]["project"] = "proj-ptx"
    record["evidence"] = [
        {
            "id": evidence_id,
            "relation": "supports",
            "status": "PASS",
            "availability": "SOURCE_AVAILABLE",
            "sizeBytes": size,
            "mediaType": "application/x-test-evidence",
        }
    ]
    return record


def test_scenario_e_lazy_evidence(tmp_path):
    """B receives the small claim without downloading the large evidence."""

    node_a = make_node(tmp_path, "node-a")
    node_b = make_node(tmp_path, "node-b")
    blob = b"E" * 4096
    evidence_digest = node_a.cas_put(blob, media_type="application/x-test-evidence")
    receipt = node_a.publish_local(claim_with_evidence("lazy", evidence_digest))

    result = synchronize(node_b, DirectCarrier(node_a), push=False)
    assert receipt.content_digest in node_b.frontier()
    # The claim moved; the evidence bytes did not.
    assert not node_b.cas_has(evidence_digest)
    assert result["pull"]["bytesReceived"] < 100_000

    # B can still triage the capsule deterministically.
    record = node_b.get_record(receipt.content_digest)
    capsule = compose_capsule(
        record,
        availability={
            evidence_digest: EvidenceReference(
                evidence_digest, EvidenceAvailability.SOURCE_AVAILABLE, size_bytes=4096
            )
        },
    )
    assessment = assess_capsule(
        capsule,
        known_digests=set(),
        retained_evidence=set(),
        supported_kinds={item.value for item in RecordKind},
        supported_relationships={item.value for item in RelationType},
    )
    assert assessment["understood"] is True
    assert assessment["alreadyHave"] is False
    assert assessment["evidenceMissing"] == [evidence_digest]
    assert assessment["evidenceLocations"][evidence_digest] == "SOURCE_AVAILABLE"
    assert assessment["retainCandidate"] is True

    # Explicit on-demand fetch resolves the evidence afterwards.
    fetched = node_a.cas_get(evidence_digest)
    assert fetched == blob
    node_b.cas_put(fetched)
    assert node_b.evidence_availability(evidence_digest) == EvidenceAvailability.LOCAL


def test_scenario_f_evidence_unavailable_stays_auditable(tmp_path):
    """A record remains useful when referenced evidence is unavailable."""

    node_a = make_node(tmp_path, "node-a")
    node_b = make_node(tmp_path, "node-b")
    ghost = "sha256:" + "9" * 64
    receipt = node_a.publish_local(claim_with_evidence("ghost", ghost))
    synchronize(node_b, DirectCarrier(node_a), push=False)

    record = node_b.get_record(receipt.content_digest)
    capsule = compose_capsule(record)
    assessment = assess_capsule(
        capsule,
        known_digests={receipt.content_digest},
        retained_evidence=set(),
        supported_kinds={item.value for item in RecordKind},
        supported_relationships={item.value for item in RelationType},
    )
    # Availability is not validity: the record is understood, retained, and
    # auditable even though its evidence is UNAVAILABLE.
    assert assessment["evidenceLocations"][ghost] == "UNAVAILABLE"
    assert assessment["understood"] is True
    assert record["statement"]["summary"].startswith("Synthetic")
    assert node_b.evidence_availability(ghost) == EvidenceAvailability.UNAVAILABLE


def test_offline_bundle_carries_claims_not_evidence(tmp_path):
    """Bundle/file transfer moves knowledge; evidence resolves separately."""

    node_a = make_node(tmp_path, "node-a")
    node_b = make_node(tmp_path, "node-b")
    blob = b"B" * 1024
    evidence_digest = node_a.cas_put(blob)
    receipt = node_a.publish_local(claim_with_evidence("bundle", evidence_digest, size=1024))

    bundle_path = tmp_path / "transfer.bundle.zip"
    BundleCarrier.export(node_a, [receipt.content_digest], bundle_path)
    result = synchronize(
        node_b, BundleCarrier(bundle_path), interest=InterestFilter.match_all(), push=False
    )
    assert receipt.content_digest in node_b.frontier()
    assert not node_b.cas_has(evidence_digest)
    assert result["pull"]["received"] == 1


def test_availability_merge_and_annotations():
    assert (
        merge_availability(EvidenceAvailability.LOCAL, EvidenceAvailability.MIRRORED)
        == EvidenceAvailability.MIRRORED
    )
    assert (
        merge_availability(EvidenceAvailability.UNAVAILABLE, EvidenceAvailability.SOURCE_AVAILABLE)
        == EvidenceAvailability.SOURCE_AVAILABLE
    )
    ref = annotation_from_evidence_entry(
        {"id": "x", "availability": "DURABLE", "sizeBytes": 12, "mediaType": "text/plain"}
    )
    assert ref is not None and ref.availability == EvidenceAvailability.DURABLE
    assert ref.size_bytes == 12
    # Unknown tokens stay inert, never executable.
    assert annotation_from_evidence_entry({"id": "x", "availability": "TELEPATHY"}) is None
    assert annotation_from_evidence_entry({"id": "x", "status": "PASS"}) is None
    reference = EvidenceReference.from_mapping(
        {"digest": "sha256:" + "a" * 64, "availability": "CANONICAL", "sizeBytes": 8}
    )
    assert reference.availability == EvidenceAvailability.CANONICAL
