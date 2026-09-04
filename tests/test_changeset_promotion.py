# SPDX-License-Identifier: Apache-2.0
"""ChangeSet promotion graph: the profile as machine-readable records."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from mncs_commons.family import FamilyRecordError, producer_references
from mncs_commons.validation import validate_record

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "changeset-promotion-graph.json"


def _load() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _edges(record: dict) -> set[tuple[str, str]]:
    return {(item["type"], item["target"]) for item in record["relationships"]}


def test_fixture_validates_cleanly() -> None:
    report = validate_record(_load())
    assert report.valid, report.diagnostics


def test_graph_covers_the_promotion_profile() -> None:
    record = _load()
    assert record["kind"] == "ChangeSet"
    assert [rev["repository"] for rev in record["details"]["baseRevisions"]] == [
        "epi13/mncs-actions",
        "epi13/mncs-language",
    ]
    edges = _edges(record)
    assert ("supports", "mncds://development-record/record.gate-1") in edges
    assert ("supports", "rights://lineage/record.gate-1") in edges
    assert ("supports", "mncs://check-result/mncs-validation") in edges
    assert ("pressure/supports-pressure", "mncds://obligation/pressure.gate.open-gap") in edges
    assert ("contradicts", "mncds://obligation/pressure.gate.blocking-gap") in edges
    assert ("promotion/promotes", "mncs://check-result/promotion-boundary") in edges
    assert len(record["relationships"]) == 6


def test_carried_references_are_digest_bound() -> None:
    refs = producer_references(_load())
    assert len(refs) == 6
    for ref in refs:
        assert ref["contentDigest"].startswith("sha256:"), ref


def test_moving_revision_is_rejected() -> None:
    from mncs_commons.family import make_changeset_record

    with pytest.raises(FamilyRecordError):
        make_changeset_record(
            changeset_id="changeset.bad",
            created_at="2026-09-04T00:00:00Z",
            base_revisions=[{"repository": "epi13/mncs-actions", "commit": "main"}],
            summary="moving refs are observations, never promotable",
        )


def test_second_promotion_result_is_rejected() -> None:
    from mncs_commons.family import make_changeset_record, producer_reference

    promotion = producer_reference(
        "mncs-promotion-boundary",
        "check-result",
        "0.1",
        "mncs://check-result/promotion-boundary",
        content_digest="sha256:" + "1" * 64,
    )
    with pytest.raises(FamilyRecordError):
        make_changeset_record(
            changeset_id="changeset.bad",
            created_at="2026-09-04T00:00:00Z",
            base_revisions=[{"repository": "epi13/mncs-actions", "commit": "a" * 40}],
            promotes=[promotion, promotion],
            summary="at most one promotion result",
        )


def test_tampered_edge_target_breaks_the_graph() -> None:
    record = _load()
    tampered = copy.deepcopy(record)
    for edge in tampered["relationships"]:
        if edge["type"] == "promotion/promotes":
            edge["target"] = "mncs://check-result/promotion-boundary-ATTACKER"
    assert _edges(tampered) != _edges(record)
    assert ("promotion/promotes", "mncs://check-result/promotion-boundary") not in _edges(
        tampered
    )
