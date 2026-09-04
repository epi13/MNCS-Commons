# SPDX-License-Identifier: Apache-2.0

"""ChangeSet promotion evidence: relate genuine promotion claims.

Covers the minimal contract that lets Commons record and relate real
promotion evidence without deciding promotion: the promotes edge only
ever points at an MNCS promotion-boundary result, and scoped references
are correlation-checked against the ChangeSet's named base revisions.

The end-to-end test relates genuine promotion-shaped evidence over real
merged revisions (MNCDS and MNCS main heads at the time of writing) with
honestly recomputed digests: no placeholder hashes anywhere.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from mncs_commons.family import (
    FamilyRecordError,
    make_changeset_record,
    producer_reference,
)
from mncs_commons.validation import validate_record

# Real merged revisions, named as base revisions below.
MNCDS_REPO = "epi13/machine-native-complexity-development-specification"
MNCDS_COMMIT = "faf59ac3ed5beabc1c7ea66bd51e4f71df796c59"
MNCS_REPO = "epi13/machine-native-complexity-standard"
MNCS_COMMIT = "688445783971db9027dc7fc44224bd63acd7a08a"


def _digest(payload: dict) -> str:
    return "sha256:" + hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _promotion_claim() -> dict:
    """A genuine promotion-claim shape: PASS over candidate-bound evidence."""
    return {
        "schema_version": "mncs.check-result/1",
        "id": "promotion-boundary",
        "provider": "mncs-promotion-boundary",
        "verdict": "PASS",
        "contract_revision": "0.1",
        "subject": {"repository": MNCDS_REPO, "commit": MNCDS_COMMIT},
        "summary": "boundary mncds-promotion over 2 required (2 PASS) -> PASS; no blockers",
        "promotion": {
            "boundary_id": "mncds-promotion",
            "required_total": 2,
            "required_passed": 2,
            "blockers": [],
        },
    }


def _scoped(producer: str, kind: str, version: str, stable_id: str,
            payload: dict, repo: str, commit: str) -> dict:
    return producer_reference(
        producer, kind, version, stable_id,
        content_digest=_digest(payload),
        scope={"repository": repo, "commit": commit},
    )


def test_promotes_from_other_producer_is_rejected() -> None:
    ref = producer_reference(
        "project-verifier", "check-result", "0.1",
        "mncs://check-result/project-tests",
        content_digest="sha256:" + "1" * 64,
    )
    with pytest.raises(FamilyRecordError):
        make_changeset_record(
            changeset_id="changeset.bad-promotes",
            created_at="2026-09-04T00:00:00Z",
            base_revisions=[{"repository": MNCDS_REPO, "commit": MNCDS_COMMIT}],
            promotes=[ref],
            summary="component PASS is never a promotion result",
        )


def test_promotes_with_non_result_kind_is_rejected() -> None:
    ref = producer_reference(
        "mncs-promotion-boundary", "DevelopmentRecord", "0.2-alpha.1",
        "mncds://development-record/record.x",
        content_digest="sha256:" + "1" * 64,
    )
    with pytest.raises(FamilyRecordError):
        make_changeset_record(
            changeset_id="changeset.bad-promotes-kind",
            created_at="2026-09-04T00:00:00Z",
            base_revisions=[{"repository": MNCDS_REPO, "commit": MNCDS_COMMIT}],
            promotes=[ref],
            summary="only evaluation results promote",
        )


def test_scoped_reference_to_unnamed_revision_is_rejected() -> None:
    ref = _scoped(
        "mncds", "check-result", "mncds-obligation-record/0.2",
        "mncs://check-result/mncds-obligations",
        {"verdict": "PASS"}, MNCDS_REPO, "0" * 40,
    )
    with pytest.raises(FamilyRecordError):
        make_changeset_record(
            changeset_id="changeset.stale-evidence",
            created_at="2026-09-04T00:00:00Z",
            base_revisions=[{"repository": MNCDS_REPO, "commit": MNCDS_COMMIT}],
            supports=[ref],
            summary="evidence for another revision is not evidence here",
        )


def test_moving_ref_scope_is_rejected() -> None:
    ref = producer_reference(
        "mncds", "check-result", "mncds-obligation-record/0.2",
        "mncs://check-result/mncds-obligations",
        content_digest="sha256:" + "1" * 64,
        scope={"repository": MNCDS_REPO, "commit": "main"},
    )
    with pytest.raises(FamilyRecordError):
        make_changeset_record(
            changeset_id="changeset.moving-scope",
            created_at="2026-09-04T00:00:00Z",
            base_revisions=[{"repository": MNCDS_REPO, "commit": MNCDS_COMMIT}],
            supports=[ref],
            summary="moving refs are observations, never promotable",
        )


def test_scopeless_reference_stays_allowed() -> None:
    ref = producer_reference(
        "mncds", "check-result", "mncds-obligation-record/0.2",
        "mncs://check-result/mncds-obligations",
        content_digest="sha256:" + "1" * 64,
    )
    record = make_changeset_record(
        changeset_id="changeset.scopeless",
        created_at="2026-09-04T00:00:00Z",
        base_revisions=[{"repository": MNCDS_REPO, "commit": MNCDS_COMMIT}],
        supports=[ref],
        summary="producers keep native stores; scope is opt-in",
    )
    assert record["kind"] == "ChangeSet"


def test_promotion_tranche_relates_genuine_evidence() -> None:
    """Relate a real promotion decision: candidate, boundary, evidence,
    obligations, claim, producer revisions, digests, ChangeSet edges."""
    record_evidence = {"record_id": "development.mncds-promotion-integration-2026-09",
                       "computed_status": "PASS"}
    obligation_evidence = {"obligation_key": "pressure.mncds.promotion-integration.required",
                           "status": "resolved"}
    claim = _promotion_claim()

    record = make_changeset_record(
        changeset_id="changeset.mncds-promotion-tranche",
        created_at="2026-09-04T00:00:00Z",
        base_revisions=[
            {"repository": MNCDS_REPO, "commit": MNCDS_COMMIT},
            {"repository": MNCS_REPO, "commit": MNCS_COMMIT},
        ],
        supports=[
            _scoped("mncds", "DevelopmentRecord", "0.2-alpha.1",
                    "mncds://development-record/development.mncds-promotion-integration-2026-09",
                    record_evidence, MNCDS_REPO, MNCDS_COMMIT),
            _scoped("mncds", "check-result", "mncds-obligation-record/0.2",
                    "mncs://check-result/mncds-obligations",
                    obligation_evidence, MNCDS_REPO, MNCDS_COMMIT),
        ],
        promotes=[
            _scoped("mncs-promotion-boundary", "check-result", "0.1",
                    "mncs://check-result/mncds-promotion",
                    claim, MNCDS_REPO, MNCDS_COMMIT),
        ],
        summary="MNCDS candidate faf59ac crosses mncds-promotion; related, not decided, by Commons",
    )
    assert record["kind"] == "ChangeSet"
    edges = {(item["type"], item["target"]) for item in record["relationships"]}
    assert (
        "supports",
        "mncds://development-record/development.mncds-promotion-integration-2026-09",
    ) in edges
    assert ("supports", "mncs://check-result/mncds-obligations") in edges
    assert ("promotion/promotes", "mncs://check-result/mncds-promotion") in edges
    report = validate_record(record)
    assert report.valid, report.diagnostics
