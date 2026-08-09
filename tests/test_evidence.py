from __future__ import annotations

import json
from pathlib import Path

from mncs_commons.evidence import evidence_lineage
from mncs_commons.store import CommonsStore


def _observation(record_id: str, summary: str) -> dict[str, object]:
    root = json.loads(
        (Path(__file__).parents[1] / "examples/observation.example.yaml").read_text(
            encoding="utf-8"
        )
    )
    root["metadata"]["recordId"] = record_id
    root["statement"]["summary"] = summary
    root["relationships"] = []
    return root


def test_evidence_trace_preserves_bundle_receipt_lineage(tmp_path: Path) -> None:
    store = CommonsStore(tmp_path / "store")
    store.init()
    bundle = _observation("bundle-record", "synthetic execution bundle")
    bundle["subject"] = {"type": "execution-bundle", "identity": "bundle-record"}
    bundle["details"] = {
        "outcome": "UNKNOWN",
        "executionBundle": {"bundle_identity": "bundle-record"},
    }
    store.add_record(bundle)
    receipt = _observation("receipt-record", "synthetic execution receipt")
    receipt["subject"] = {"type": "execution-receipt", "identity": "receipt-record"}
    receipt["relationships"] = [{"type": "references_artifact", "target": "bundle-record"}]
    receipt["details"] = {
        "outcome": "UNKNOWN",
        "executionReceipt": {
            "bundle": {"test_bundle_identity": "bundle-record"},
        },
    }
    added = store.add_record(receipt)

    trace = evidence_lineage(store.records(), [added.content_digest], max_depth=2)
    assert [item["metadata"]["recordId"] for item in trace.records] == [
        "bundle-record",
        "receipt-record",
    ]
    assert not trace.diagnostics
    assert not trace.unresolved


def test_evidence_trace_reports_unresolved_binding_without_inference(tmp_path: Path) -> None:
    store = CommonsStore(tmp_path / "store")
    store.init()
    receipt = _observation("receipt-record", "synthetic mismatch")
    receipt["subject"] = {"type": "execution-receipt", "identity": "receipt-record"}
    receipt["details"] = {
        "outcome": "UNKNOWN",
        "executionReceipt": {
            "bundle": {"test_bundle_identity": "missing-bundle"},
        },
    }
    added = store.add_record(receipt)

    trace = evidence_lineage(store.records(), [added.content_digest], max_depth=1)
    assert "missing-bundle" in trace.unresolved
    assert any(item.code == "UNRESOLVED_EVIDENCE_REFERENCE" for item in trace.diagnostics)
    assert all(item["details"]["outcome"] == "UNKNOWN" for item in trace.records)
