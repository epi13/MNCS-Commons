# mypy: ignore-errors
"""Micro-correctness: REPO_HYGIENE repo-local for all states except NEEDS_RECONCILIATION."""

from __future__ import annotations

import copy

import pytest

from mncs_commons.application import CommonsApplication
from mncs_commons.store import CommonsStore
from mncs_commons.validation import validate_record
from mncs_commons.work import (
    WORK_HYGIENE_SCOPE_CODE,
    WorkProtocolError,
    new_work_record,
    validate_work_record,
)


def _app(tmp_path) -> CommonsApplication:
    store = CommonsStore(tmp_path / "store")
    store.init()
    return CommonsApplication(store)


def _hygiene_proposal(work_id: str, **over) -> dict:
    base = {
        "workId": work_id,
        "submittingConsumer": {"type": "worker", "id": work_id},
        "project": {"id": "mncs-family", "revision": "test"},
        "repository": "mncs-language",
        "affectedRepositories": ["mncs-language"],
        "task": f"Hygiene {work_id}",
        "lane": "REPO_HYGIENE",
        "evidenceLinks": [f"ev:{work_id}"],
        "proposalSource": "worker-discovery",
        "priority": 20,
    }
    base.update(over)
    return base


def test_1_multi_repo_needs_reconciliation_is_allowed_as_audit(tmp_path) -> None:
    app = _app(tmp_path)
    res = app.propose_work(
        _hygiene_proposal(
            "work:micro-needs-audit",
            affectedRepositories=["mncs-language", "mncs-language-service"],
        )
    )
    assert res["proposal"] == "NEEDS_RECONCILIATION"
    status = app.work_status(res["workId"])
    assert status["coordinationState"] == "NEEDS_RECONCILIATION"
    details = status["current"]["details"]
    assert WORK_HYGIENE_SCOPE_CODE in details.get("proposalReason", "")
    # Also via direct new_work_record audit trail is allowed
    rec = new_work_record(
        {
            "workId": "work:direct-needs-audit",
            "submittingConsumer": {"type": "agent", "id": "a"},
            "project": {"id": "mncs-family", "revision": "test"},
            "repository": "mncs-language",
            "affectedRepositories": ["mncs-language", "mncs-language-service"],
            "task": "audit",
            "lane": "REPO_HYGIENE",
            "priority": 10,
            "coordinationState": "NEEDS_RECONCILIATION",
            "proposalStatus": "NEEDS_RECONCILIATION",
            "proposalReason": WORK_HYGIENE_SCOPE_CODE,
        }
    )
    assert rec["details"]["coordinationState"] == "NEEDS_RECONCILIATION"
    # validate must NOT flag NEEDS_RECONCILIATION as hygiene violation
    diags = validate_work_record(rec)
    assert not any(d.code == WORK_HYGIENE_SCOPE_CODE for d in diags)
    # store.add_record for NEEDS audit should succeed (no hygiene diagnostic)
    # Use a fresh store to avoid duplicate workId conflict
    app2 = _app(tmp_path / "store2")
    added = app2.require_store().add_record(rec)
    assert added.content_digest.startswith("sha256:")


def test_2_multi_repo_needs_to_claimed_is_rejected(tmp_path) -> None:
    app = _app(tmp_path)
    res = app.propose_work(
        _hygiene_proposal(
            "work:micro-needs-claim",
            affectedRepositories=["mncs-language", "mncs-language-service"],
        )
    )
    assert res["proposal"] == "NEEDS_RECONCILIATION"
    status = app.work_status(res["workId"])
    with pytest.raises(WorkProtocolError) as exc:
        app.transition_work(
            res["workId"],
            {
                "state": "assigned",
                "coordinationState": "CLAIMED",
                "actor": {"type": "worker", "id": "w1"},
                "expectedPreviousDigest": status["currentDigest"],
                "claim": {"actor": {"type": "worker", "id": "w1"}, "claimedAt": "2026-08-27T00:00:00Z"},  # noqa: E501
            },
        )
    assert exc.value.code == WORK_HYGIENE_SCOPE_CODE


def test_3_multi_repo_needs_to_in_progress_is_rejected_at_lowest_layer(tmp_path) -> None:
    # NEEDS_RECONCILIATION -> IN_PROGRESS via coordination is allowed in
    # state machine, but work state submitted->running is not allowed, so
    # application layer would reject with WORK_TRANSITION_REJECTED before
    # hygiene. Prove invariant at lowest validation layer.
    base = new_work_record(
        {
            "workId": "work:micro-craft-base",
            "submittingConsumer": {"type": "agent", "id": "a"},
            "project": {"id": "mncs-family", "revision": "test"},
            "repository": "mncs-language",
            "affectedRepositories": ["mncs-language"],
            "task": "base",
            "lane": "REPO_HYGIENE",
            "priority": 10,
            "coordinationState": "AVAILABLE",
        }
    )
    crafted = copy.deepcopy(base)
    crafted["details"]["affectedRepositories"] = ["mncs-language", "mncs-language-service"]
    crafted["details"]["canonicalAffectedRepositories"] = [
        "epi13/mncs-language",
        "epi13/mncs-language-service",
    ]
    crafted["details"]["canonicalRepository"] = "epi13/mncs-language"
    crafted["details"]["coordinationState"] = "IN_PROGRESS"
    crafted["details"]["claim"] = {  # noqa: E501
        "actor": {"type": "worker", "id": "w1"},
        "claimedAt": "2026-08-27T00:00:00Z",
    }
    diags = validate_work_record(crafted)
    assert any(d.code == WORK_HYGIENE_SCOPE_CODE for d in diags)


def test_4_crafted_multi_claimed_rejected_by_validate(tmp_path) -> None:
    base = new_work_record(
        {
            "workId": "work:crafted-validate-base",
            "submittingConsumer": {"type": "agent", "id": "a"},
            "project": {"id": "mncs-family", "revision": "test"},
            "repository": "mncs-language",
            "affectedRepositories": ["mncs-language"],
            "task": "base",
            "lane": "REPO_HYGIENE",
            "priority": 10,
            "coordinationState": "AVAILABLE",
        }
    )
    for coord in ["CLAIMED", "IN_PROGRESS", "BLOCKED", "VERIFYING", "COMPLETE", "ABANDONED", "SUPERSEDED", "AVAILABLE"]:  # noqa: E501
        crafted = copy.deepcopy(base)
        crafted["details"]["affectedRepositories"] = ["mncs-language", "mncs-language-service"]
        crafted["details"]["canonicalAffectedRepositories"] = [
            "epi13/mncs-language",
            "epi13/mncs-language-service",
        ]
        crafted["details"]["canonicalRepository"] = "epi13/mncs-language"
        crafted["details"]["coordinationState"] = coord
        if coord in {"CLAIMED", "IN_PROGRESS", "VERIFYING"}:
            crafted["details"]["claim"] = {"actor": {"type": "worker", "id": "w1"}, "claimedAt": "2026-08-27T00:00:00Z"}  # noqa: E501
        if coord == "BLOCKED":
            crafted["details"]["blockers"] = ["blocked"]
        if coord == "COMPLETE":
            crafted["details"]["result"] = {"terminalOutcome": "PASS", "evidence": [{"id": "ev", "status": "PASS"}]}  # noqa: E501
            crafted["details"]["claim"] = {"actor": {"type": "worker", "id": "w1"}, "claimedAt": "2026-08-27T00:00:00Z"}  # noqa: E501
        diags = validate_work_record(crafted)
        assert any(d.code == WORK_HYGIENE_SCOPE_CODE for d in diags), f"{coord} multi should be rejected"  # noqa: E501
        # Also via full record validation
        rec_diags = validate_record(crafted)
        assert any(d.code == WORK_HYGIENE_SCOPE_CODE for d in rec_diags.diagnostics)

    # NEEDS_RECONCILIATION multi must NOT be flagged
    crafted_needs = copy.deepcopy(base)
    crafted_needs["details"]["affectedRepositories"] = ["mncs-language", "mncs-language-service"]
    crafted_needs["details"]["canonicalAffectedRepositories"] = [
        "epi13/mncs-language",
        "epi13/mncs-language-service",
    ]
    crafted_needs["details"]["canonicalRepository"] = "epi13/mncs-language"
    crafted_needs["details"]["coordinationState"] = "NEEDS_RECONCILIATION"
    crafted_needs["details"]["proposalStatus"] = "NEEDS_RECONCILIATION"
    crafted_needs["details"]["proposalReason"] = WORK_HYGIENE_SCOPE_CODE
    if "claim" in crafted_needs["details"]:
        del crafted_needs["details"]["claim"]
    diags_needs = validate_work_record(crafted_needs)
    assert not any(d.code == WORK_HYGIENE_SCOPE_CODE for d in diags_needs)


def test_5_crafted_active_rejected_by_store_add_record(tmp_path) -> None:
    app = _app(tmp_path)
    base = new_work_record(
        {
            "workId": "work:store-base",
            "submittingConsumer": {"type": "agent", "id": "a"},
            "project": {"id": "mncs-family", "revision": "test"},
            "repository": "mncs-language",
            "affectedRepositories": ["mncs-language"],
            "task": "base",
            "lane": "REPO_HYGIENE",
            "priority": 10,
            "coordinationState": "AVAILABLE",
        }
    )
    crafted = copy.deepcopy(base)
    crafted["details"]["affectedRepositories"] = ["mncs-language", "mncs-language-service"]
    crafted["details"]["canonicalAffectedRepositories"] = [
        "epi13/mncs-language",
        "epi13/mncs-language-service",
    ]
    crafted["details"]["canonicalRepository"] = "epi13/mncs-language"
    crafted["details"]["coordinationState"] = "CLAIMED"
    crafted["details"]["claim"] = {"actor": {"type": "worker", "id": "w1"}, "claimedAt": "2026-08-27T00:00:00Z"}  # noqa: E501
    # Direct store publish must fail
    with pytest.raises(Exception) as exc:
        app.require_store().add_record(crafted)
    # Error should contain hygiene code via StoreError
    msg = str(exc.value)
    assert WORK_HYGIENE_SCOPE_CODE in msg or "REPO_HYGIENE" in msg

    # Also test raw publish via application.publish path (exchange) - same validation
    crafted["metadata"]["recordId"] = "work:store-base2"  # avoid duplicate
    crafted["details"]["workId"] = "work:store-base2"
    # Need to recompute? add_record will compute digest, but validation will still catch hygiene before store  # noqa: E501
    from mncs_commons.validation import validate_record

    report = validate_record(crafted)
    assert any(d.code == WORK_HYGIENE_SCOPE_CODE for d in report.diagnostics)


def test_6_single_repo_hygiene_can_transition_normally(tmp_path) -> None:
    app = _app(tmp_path)
    res = app.propose_work(
        _hygiene_proposal("work:single-transitions", affectedRepositories=["mncs-language"])
    )
    assert res["proposal"] == "ACCEPTED"
    s = app.work_status(res["workId"])
    # AVAILABLE -> CLAIMED
    c1 = app.transition_work(
        res["workId"],
        {
            "state": "assigned",
            "coordinationState": "CLAIMED",
            "actor": {"type": "worker", "id": "w1"},
            "expectedPreviousDigest": s["currentDigest"],
            "claim": {"actor": {"type": "worker", "id": "w1"}, "claimedAt": "2026-08-27T00:00:00Z"},
        },
    )
    assert c1["state"] == "assigned"
    # CLAIMED -> IN_PROGRESS
    c2 = app.transition_work(
        res["workId"],
        {
            "state": "running",
            "coordinationState": "IN_PROGRESS",
            "actor": {"type": "worker", "id": "w1"},
            "expectedPreviousDigest": c1["currentDigest"],
        },
    )
    assert c2["state"] == "running"
    # IN_PROGRESS -> BLOCKED
    c3 = app.transition_work(
        res["workId"],
        {
            "state": "blocked",
            "coordinationState": "BLOCKED",
            "actor": {"type": "worker", "id": "w1"},
            "expectedPreviousDigest": c2["currentDigest"],
            "blockers": ["waiting"],
        },
    )
    assert c3["state"] == "blocked"
    # BLOCKED -> IN_PROGRESS
    c4 = app.transition_work(
        res["workId"],
        {
            "state": "running",
            "coordinationState": "IN_PROGRESS",
            "actor": {"type": "worker", "id": "w1"},
            "expectedPreviousDigest": c3["currentDigest"],
        },
    )
    assert c4["state"] == "running"
    # IN_PROGRESS -> VERIFYING
    c5 = app.transition_work(
        res["workId"],
        {
            "state": "checkpointed",
            "coordinationState": "VERIFYING",
            "actor": {"type": "worker", "id": "w1"},
            "expectedPreviousDigest": c4["currentDigest"],
            "progress": {"percent": 100},
        },
    )
    assert c5["state"] == "checkpointed"
    # VERIFYING -> COMPLETE
    c6 = app.transition_work(
        res["workId"],
        {
            "state": "completed",
            "coordinationState": "COMPLETE",
            "actor": {"type": "worker", "id": "w1"},
            "expectedPreviousDigest": c5["currentDigest"],
            "result": {"terminalOutcome": "PASS", "evidence": [{"id": "ev", "status": "PASS"}]},
        },
    )
    assert c6["state"] == "completed"
    # Also ABANDONED and SUPERSEDED from AVAILABLE should be allowed for single
    for term_coord, term_state in [("ABANDONED", "failed"), ("SUPERSEDED", "cancelled")]:
        app_single = _app(tmp_path / f"store-{term_coord}")
        res_t = app_single.propose_work(
            _hygiene_proposal(f"work:single-{term_coord}", affectedRepositories=["mncs-language"])
        )
        s_t = app_single.work_status(res_t["workId"])
        t = app_single.transition_work(
            res_t["workId"],
            {
                "state": term_state,
                "coordinationState": term_coord,
                "actor": {"type": "worker", "id": "w1"},
                "expectedPreviousDigest": s_t["currentDigest"],
                "result": {"terminalOutcome": "PASS", "evidence": [{"id": "ev", "status": "PASS"}]}
                if term_state in {"failed", "cancelled"} and term_coord in {"ABANDONED", "SUPERSEDED"}  # noqa: E501
                else {},
            },
        )
        # For ABANDONED/SUPERSEDED from AVAILABLE, the transition is allowed in coordination machine
        assert t["state"] == term_state or t["state"] == "cancelled" or t["state"] == "failed"


def test_7_propose_multi_remains_needs_reconciliation(tmp_path) -> None:
    app = _app(tmp_path)
    res = app.propose_work(
        _hygiene_proposal(
            "work:propose-multi-remains",
            affectedRepositories=["mncs-language", "mncs-language-service"],
        )
    )
    assert res["proposal"] == "NEEDS_RECONCILIATION"
    assert app.work_status(res["workId"])["coordinationState"] == "NEEDS_RECONCILIATION"


def test_8_health_sweep_remains_valid_repo_local(tmp_path) -> None:
    app = _app(tmp_path)
    obs = [
        {
            "repository": "mncs-forge-mcp",
            "outcome": "FAIL",
            "observedAt": "2026-08-27T01:00:00Z",
            "source": "janitor",
            "sourceIdentity": "id1",
            "findingIdentity": "forge:ci:health",
            "finding": "fail",
            "categories": ["ci"],
        }
    ]
    sweep = app.family_health_sweep(obs)
    assert sweep["proposals"][0]["proposal"] == "ACCEPTED"
    details = app.work_status(sweep["proposals"][0]["workId"])["current"]["details"]
    assert set(details["canonicalAffectedRepositories"]) == {details["canonicalRepository"]}
    # No multi hygiene becomes AVAILABLE
    for w in app.work_next(lane="REPO_HYGIENE", limit=100)["work"]:
        d = w["current"]["details"]
        assert set(d["canonicalAffectedRepositories"]) == {d["canonicalRepository"]}


def test_9_other_lanes_unchanged(tmp_path) -> None:
    app = _app(tmp_path)
    for lane in ["REPO_LOCAL", "VERIFICATION", "CONVERSION_PREP", "SHARED_CORE", "DOCUMENTATION"]:
        p = {
            "workId": f"work:other-{lane}-micro",
            "submittingConsumer": {"type": "worker", "id": "w"},
            "project": {"id": "mncs-family", "revision": "test"},
            "repository": "mncs-tui",
            "affectedRepositories": ["mncs-tui", "mncs-lineage"],
            "task": f"Other {lane}",
            "lane": lane,
            "evidenceLinks": ["ev"],
            "proposalSource": "worker-discovery",
            "priority": 10,
        }
        if lane == "SHARED_CORE":
            p["sharedCoreImpact"] = True
            p["capability"] = f"cap.{lane.lower()}"
        else:
            p["sharedCoreImpact"] = False
        res = app.propose_work(p)
        assert res["proposal"] == "ACCEPTED", f"{lane} multi should still be accepted"
        # Direct single for those lanes also remains
        base_ok = new_work_record(
            {
                "workId": f"work:direct-other-{lane}-micro2",
                "submittingConsumer": {"type": "agent", "id": "a"},
                "project": {"id": "mncs-family", "revision": "test"},
                "repository": "mncs-tui",
                "affectedRepositories": ["mncs-tui"],
                "task": f"Direct {lane}",
                "lane": lane,
                "priority": 10,
                **({"sharedCoreImpact": True, "capability": f"cap.{lane.lower()}"} if lane == "SHARED_CORE" else {}),  # noqa: E501
            }
        )
        assert base_ok["details"]["lane"] == lane
