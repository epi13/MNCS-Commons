# mypy: ignore-errors
"""Adversarial REPO_HYGIENE scope invariants.

REPO_HYGIENE work must always be scoped to exactly one canonical repository:
canonicalAffectedRepositories == {canonicalRepository}. No multi-repo hygiene
task should become AVAILABLE; invalid proposals become NEEDS_RECONCILIATION
with WORK_HYGIENE_REPOSITORY_SCOPE_INVALID, and direct submission must not
bypass the invariant.
"""

from __future__ import annotations

import pytest

from mncs_commons.application import CommonsApplication
from mncs_commons.store import CommonsStore
from mncs_commons.work import WORK_HYGIENE_SCOPE_CODE, WorkProtocolError


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


def test_single_repo_hygiene_proposal_is_accepted(tmp_path) -> None:
    app = _app(tmp_path)
    res = app.propose_work(_hygiene_proposal("work:single-hyg"))
    assert res["proposal"] == "ACCEPTED"
    status = app.work_status(str(res["workId"]))
    assert status["coordinationState"] == "AVAILABLE"
    details = status["current"]["details"]  # type: ignore[attr-defined]
    assert details["lane"] == "REPO_HYGIENE"
    # canonicalAffected == {canonicalRepo}
    assert details["canonicalAffectedRepositories"] == [details["canonicalRepository"]]
    assert details["canonicalRepository"] == "epi13/mncs-language"
    # claimable via work_next
    nxt = app.work_next(lane="REPO_HYGIENE", repository="mncs-language", limit=10)["work"]
    assert any(w["workId"] == res["workId"] for w in nxt)


def test_alias_spellings_resolving_to_same_canonical_are_accepted(tmp_path) -> None:
    app = _app(tmp_path)
    # alias spellings that resolve to same canonical repo should be accepted
    cases = [
        ("mncs-forge", ["mncs-forge-mcp"]),
        ("mncs-forge-mcp", ["forge"]),
        ("epi13/mncs-forge-mcp", ["https://github.com/epi13/mncs-forge-mcp"]),
        ("MNCS-Commons", ["mncs-commons"]),
        ("commons", ["MNCS-Commons"]),
        ("mncs-language", ["MNCS-LANGUAGE"]),
    ]
    for idx, (repo, affected) in enumerate(cases):
        wid = f"work:alias-{idx}"
        res = app.propose_work(
            _hygiene_proposal(
                wid,
                repository=repo,
                affectedRepositories=affected,
            )
        )
        assert res["proposal"] == "ACCEPTED", f"alias case {repo} -> {affected} should be accepted"
        details = app.work_status(str(res["workId"]))["current"]["details"]  # type: ignore
        # canonical set is singleton and equals primary (deduplicated set)
        assert set(details["canonicalAffectedRepositories"]) == {details["canonicalRepository"]}
        assert len(set(details["canonicalAffectedRepositories"])) == 1

    # Duplicate alias entries that still deduplicate to one canonical repo are also accepted
    res_dup = app.propose_work(
        _hygiene_proposal(
            "work:alias-dup",
            repository="commons",
            affectedRepositories=["MNCS-Commons", "mncs-commons", "epi13/MNCS-Commons"],
        )
    )
    assert res_dup["proposal"] == "ACCEPTED"
    details_dup = app.work_status(str(res_dup["workId"]))["current"]["details"]  # type: ignore
    assert set(details_dup["canonicalAffectedRepositories"]) == {details_dup["canonicalRepository"]}


def test_multi_repo_hygiene_proposal_becomes_needs_reconciliation(tmp_path) -> None:
    app = _app(tmp_path)
    res = app.propose_work(
        _hygiene_proposal(
            "work:multi-hyg",
            repository="mncs-language",
            affectedRepositories=["mncs-language", "mncs-language-service"],
        )
    )
    assert res["proposal"] == "NEEDS_RECONCILIATION"
    status = app.work_status(res["workId"])
    assert status["coordinationState"] == "NEEDS_RECONCILIATION"
    details = status["current"]["details"]
    assert details["proposalStatus"] == "NEEDS_RECONCILIATION"
    assert WORK_HYGIENE_SCOPE_CODE in details.get("proposalReason", "")
    assert WORK_HYGIENE_SCOPE_CODE in res.get("proposalReason", "") or WORK_HYGIENE_SCOPE_CODE in details.get(  # noqa: E501
        "proposalReason", ""
    )
    # must not be claimable
    assert all(
        w["workId"] != res["workId"]  # noqa: E501
        for w in app.work_next(lane="REPO_HYGIENE", limit=10)["work"]
    )
    assert all(
        w["workId"] != res["workId"]  # noqa: E501
        for w in app.work_next(lane="REPO_HYGIENE", repository="mncs-language", limit=10)["work"]
    )
    with pytest.raises(WorkProtocolError, match="not claimable"):
        app.claim_work(
            res["workId"],
            actor={"type": "worker", "id": "w"},
            expected_previous_digest=status["currentDigest"],
            lane="REPO_HYGIENE",
        )


def test_multi_repo_hygiene_with_mismatched_primary_also_needs_reconciliation(tmp_path) -> None:
    app = _app(tmp_path)
    # primary A but affected only B -> canonical sets differ
    res = app.propose_work(
        _hygiene_proposal(
            "work:mismatch-hyg",
            repository="mncs-language",
            affectedRepositories=["mncs-language-service"],
        )
    )
    # propose normalizes to include primary, so this becomes  # noqa: E501
    # [service, language] size 2 -> still invalid
    assert res["proposal"] == "NEEDS_RECONCILIATION"
    assert WORK_HYGIENE_SCOPE_CODE in app.work_status(  # noqa: E501
        str(res["workId"])
    )["current"]["details"]["proposalReason"]


def test_direct_submission_cannot_bypass_invariant(tmp_path) -> None:
    app = _app(tmp_path)
    # Direct submission of multi-repo hygiene must fail closed with stable code
    with pytest.raises(WorkProtocolError) as exc:
        app.submit_work(
            {
                "workId": "work:direct-multi",
                "submittingConsumer": {"type": "agent", "id": "a"},
                "project": {"id": "mncs-family", "revision": "test"},
                "repository": "mncs-language",
                "affectedRepositories": ["mncs-language", "mncs-language-service"],
                "task": "Direct multi",
                "lane": "REPO_HYGIENE",
                "priority": 10,
            }
        )
    assert exc.value.code == WORK_HYGIENE_SCOPE_CODE

    # Single-repo direct submission must succeed
    ok = app.submit_work(
        {
            "workId": "work:direct-single",
            "submittingConsumer": {"type": "agent", "id": "a"},
            "project": {"id": "mncs-family", "revision": "test"},
            "repository": "mncs-language-service",
            "affectedRepositories": ["mncs-language-service"],
            "task": "Direct single",
            "lane": "REPO_HYGIENE",
            "priority": 10,
        }
    )
    assert ok["workId"] == "work:direct-single"
    status = app.work_status(str(ok["workId"]))  # type: ignore
    details = status["current"]["details"]  # type: ignore
    # Direct submit via submit_work does not auto-populate canonical fields;
    # verify hygiene via canonical resolution instead of requiring canonical fields
    if "canonicalAffectedRepositories" in details:
        assert details["canonicalAffectedRepositories"] == [details["canonicalRepository"]]
    else:
        # Fallback: resolve legacy fields to canonical
        from mncs_commons.family_registry import canonical_project_identity

        primary = canonical_project_identity(details.get("repository"))
        aff_set = {
            canonical_project_identity(v)["repository"]  # type: ignore
            for v in details.get("affectedRepositories", [])
            if canonical_project_identity(v)
        }
        assert primary is not None
        assert aff_set == {primary["repository"]}

    # Alias single via direct submission also succeeds
    ok_alias = app.submit_work(
        {
            "workId": "work:direct-alias",
            "submittingConsumer": {"type": "agent", "id": "a"},
            "project": {"id": "mncs-family", "revision": "test"},
            "repository": "mncs-forge",
            "affectedRepositories": ["mncs-forge-mcp"],
            "task": "Direct alias",
            "lane": "REPO_HYGIENE",
            "priority": 10,
        }
    )
    assert ok_alias["workId"] == "work:direct-alias"

    # Even with canonical fields injected, multi-repo must still be rejected for AVAILABLE
    with pytest.raises(WorkProtocolError) as exc2:
        app.submit_work(
            {
                "workId": "work:direct-canonical-multi",
                "submittingConsumer": {"type": "agent", "id": "a"},
                "project": {"id": "mncs-family", "revision": "test"},
                "repository": "mncs-language",
                "affectedRepositories": ["mncs-language"],
                "canonicalRepository": "epi13/mncs-language",
                "canonicalAffectedRepositories": [
                    "epi13/mncs-language",
                    "epi13/mncs-language-service",
                ],
                "task": "Direct canonical multi",
                "lane": "REPO_HYGIENE",
                "priority": 10,
            }
        )
    assert exc2.value.code == WORK_HYGIENE_SCOPE_CODE


def test_direct_submission_needs_reconciliation_multi_is_audit_trail(tmp_path) -> None:
    """Invalid hygiene as NEEDS_RECONCILIATION via direct submit is allowed as audit."""  # noqa: E501
    from mncs_commons.work import new_work_record

    # Propose path uses NEEDS_RECONCILIATION to persist invalid hygiene  # noqa: E501
    # direct helper should allow it too
    rec = new_work_record(
        {
            "workId": "work:direct-needs",
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

    # But AVAILABLE must still be rejected
    with pytest.raises(WorkProtocolError) as exc:
        new_work_record(
            {
                "workId": "work:direct-avail",
                "submittingConsumer": {"type": "agent", "id": "a"},
                "project": {"id": "mncs-family", "revision": "test"},
                "repository": "mncs-language",
                "affectedRepositories": ["mncs-language", "mncs-language-service"],
                "task": "avail",
                "lane": "REPO_HYGIENE",
                "priority": 10,
                "coordinationState": "AVAILABLE",
            }
        )
    assert exc.value.code == WORK_HYGIENE_SCOPE_CODE


def test_health_sweep_creates_repo_local_hygiene(tmp_path) -> None:
    app = _app(tmp_path)
    # Single FAIL observation creates one-repo hygiene
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
    assert len(sweep["proposals"]) == 1
    proposal = sweep["proposals"][0]
    assert proposal["proposal"] == "ACCEPTED"
    wid = proposal["workId"]
    details = app.work_status(wid)["current"]["details"]
    assert details["lane"] == "REPO_HYGIENE"
    assert details["affectedRepositories"] == ["mncs-forge-mcp"]
    assert details["canonicalAffectedRepositories"] == [details["canonicalRepository"]]
    assert details["canonicalRepository"] == "epi13/mncs-forge-mcp"
    # No multi-repo hygiene should be AVAILABLE from sweep
    for work in app.work_next(lane="REPO_HYGIENE", limit=100)["work"]:
        d = work["current"]["details"]
        assert d["canonicalAffectedRepositories"] == [d["canonicalRepository"]]

    # Multiple FAILs for different repos create separate single-repo works
    obs_multi = [
        {
            "repository": "mncs-language",
            "outcome": "FAIL",
            "observedAt": "2026-08-27T02:00:00Z",
            "source": "janitor",
            "sourceIdentity": "id2",
            "findingIdentity": "lang:ci:fail",
            "finding": "lang fail",
            "categories": ["ci"],
        },
        {
            "repository": "mncs-language-service",
            "outcome": "FAIL",
            "observedAt": "2026-08-27T02:00:00Z",
            "source": "janitor",
            "sourceIdentity": "id3",
            "findingIdentity": "service:ci:fail",
            "finding": "service fail",
            "categories": ["ci"],
        },
    ]
    sweep2 = app.family_health_sweep(obs_multi)
    assert len(sweep2["proposals"]) == 2
    for prop in sweep2["proposals"]:
        assert prop["proposal"] == "ACCEPTED"
        d = app.work_status(prop["workId"])["current"]["details"]
        assert d["canonicalAffectedRepositories"] == [d["canonicalRepository"]]


def test_cross_repo_follow_on_without_widening_original(tmp_path) -> None:
    app = _app(tmp_path)
    # Original hygiene for repo A
    res_a = app.propose_work(
        _hygiene_proposal(
            "work:hyg-a",
            repository="mncs-language",
            affectedRepositories=["mncs-language"],
        )
    )
    assert res_a["proposal"] == "ACCEPTED"
    status_a = app.work_status(res_a["workId"])
    # Discover issue in repo B, create separate hygiene for B with relationship to A
    res_b = app.propose_work(
        _hygiene_proposal(
            "work:hyg-b",
            repository="mncs-language-service",
            affectedRepositories=["mncs-language-service"],
            createdFrom=[res_a["workId"]],
        )
    )
    assert res_b["proposal"] == "ACCEPTED"
    details_b = app.work_status(res_b["workId"])["current"]["details"]
    assert details_b["createdFrom"] == [res_a["workId"]]
    # B's relationships include derived_from A
    rels_b = app.work_status(res_b["workId"])["current"]["relationships"]
    assert any(r["type"] == "derived_from" and r["target"] == res_a["workId"] for r in rels_b)
    # Original A is still single-repo, not widened
    details_a = app.work_status(res_a["workId"])["current"]["details"]
    assert details_a["canonicalAffectedRepositories"] == [details_a["canonicalRepository"]]
    assert details_a["canonicalRepository"] == "epi13/mncs-language"
    # Also test followOnRequests path via transition
    claimed = app.claim_work(
        res_a["workId"],
        actor={"type": "worker", "id": "w1"},
        expected_previous_digest=status_a["currentDigest"],
        lane="REPO_HYGIENE",
    )
    running = app.transition_work(
        res_a["workId"],
        {
            "state": "running",
            "coordinationState": "IN_PROGRESS",
            "actor": {"type": "worker", "id": "w1"},
            "expectedPreviousDigest": claimed["currentDigest"],
        },
    )
    # Add follow-on via attachments+followOnRequests (allowed same-state with attachments)
    followed = app.transition_work(
        res_a["workId"],
        {
            "state": "running",
            "actor": {"type": "worker", "id": "w1"},
            "expectedPreviousDigest": running["currentDigest"],
            "followOnRequests": [res_b["workId"]],
            "attachments": [{"type": "follow-on", "target": res_b["workId"]}],
        },
    )
    assert followed["state"] == "running"
    rels_a = app.work_status(res_a["workId"])["current"]["relationships"]
    assert any(r["type"] == "follows_up" and r["target"] == res_b["workId"] for r in rels_a)
    # Original task's scope unchanged
    details_a2 = app.work_status(res_a["workId"])["current"]["details"]
    assert details_a2["affectedRepositories"] == ["mncs-language"]
    assert details_a2["canonicalAffectedRepositories"] == ["epi13/mncs-language"]


def test_other_lanes_unchanged(tmp_path) -> None:
    app = _app(tmp_path)
    lanes = ["REPO_LOCAL", "VERIFICATION", "CONVERSION_PREP", "SHARED_CORE", "DOCUMENTATION"]
    for lane in lanes:
        shared = lane == "SHARED_CORE"
        proposal = {
            "workId": f"work:other-{lane}",
            "submittingConsumer": {"type": "worker", "id": "w"},
            "project": {"id": "mncs-family", "revision": "test"},
            "repository": "mncs-tui",
            "affectedRepositories": ["mncs-tui", "mncs-lineage"],
            "task": f"Other lane {lane}",
            "lane": lane,
            "evidenceLinks": ["ev"],
            "proposalSource": "worker-discovery",
            "priority": 10,
        }
        if shared:
            proposal["sharedCoreImpact"] = True
            proposal["capability"] = f"cap.{lane.lower()}"
        else:
            proposal["sharedCoreImpact"] = False
        res = app.propose_work(proposal)
        # Multi-repo for non-hygiene lanes should be ACCEPTED (not hygiene-scoped)
        assert res["proposal"] == "ACCEPTED", f"{lane} multi-repo should remain accepted"
        nxt = app.work_next(lane=lane, limit=100)["work"]
        assert any(w["workId"] == res["workId"] for w in nxt)

    # Direct submit for these lanes also remains multi-repo capable
    for lane in ["REPO_LOCAL", "VERIFICATION"]:
        ok = app.submit_work(
            {
                "workId": f"work:direct-other-{lane}",
                "submittingConsumer": {"type": "agent", "id": "a"},
                "project": {"id": "mncs-family", "revision": "test"},
                "repository": "mncs-tui",
                "affectedRepositories": ["mncs-tui", "mncs-lineage"],
                "task": f"Direct {lane}",
                "lane": lane,
                "priority": 10,
            }
        )
        assert ok["workId"] == f"work:direct-other-{lane}"


def test_hygiene_invalid_never_becomes_available_via_health_sweep_alias(tmp_path) -> None:
    """Health sweep with alias observation stays local."""  # noqa: E501
    app = _app(tmp_path)
    # Health sweep should never produce multi-repo hygiene even if observation uses alias
    obs = {
        "repository": "mncs-forge",  # alias for mncs-forge-mcp
        "outcome": "FAIL",
        "observedAt": "2026-08-27T03:00:00Z",
        "source": "janitor",
        "sourceIdentity": "id-alias",
        "findingIdentity": "alias:ci",
        "finding": "fail alias",
        "categories": ["ci"],
    }
    sweep = app.family_health_sweep([obs])
    assert sweep["proposals"][0]["proposal"] == "ACCEPTED"
    details = app.work_status(sweep["proposals"][0]["workId"])["current"]["details"]
    assert details["canonicalRepository"] == "epi13/mncs-forge-mcp"
    assert details["canonicalAffectedRepositories"] == ["epi13/mncs-forge-mcp"]
