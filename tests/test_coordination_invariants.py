"""Fail-closed invariants: adversarial tests for multi-worker safety.

Each test reproduces a defect that would allow a malformed, stale, or
ambiguous work record to become claimable if the system failed open.
"""

from __future__ import annotations

import pytest

from mncs_commons.application import CommonsApplication
from mncs_commons.family_registry import CoverageState, canonical_project_identity
from mncs_commons.lane_policy import lane_policy, scope_decision
from mncs_commons.store import CommonsStore
from mncs_commons.work import WorkProtocolError


def _app(tmp_path) -> CommonsApplication:
    store = CommonsStore(tmp_path / "store")
    store.init()
    return CommonsApplication(store)


def _proposal(work_id: str, **over) -> dict:
    base = {
        "workId": work_id,
        "submittingConsumer": {"type": "worker", "id": work_id},
        "project": {"id": "mncs-family", "revision": "test"},
        "repository": "mncs-language",
        "affectedRepositories": ["mncs-language"],
        "task": f"Task {work_id}",
        "lane": "SHARED_CORE",
        "sharedCoreImpact": True,
        "capability": "test.capability",
        "evidenceLinks": [f"fixture:{work_id}"],
        "proposalSource": "worker-discovery",
        "priority": 20,
    }
    base.update(over)
    return base


def test_invalid_proposal_with_caller_forced_available(tmp_path) -> None:
    app = _app(tmp_path)
    p = _proposal(
        "work:evil1",
        repository="not-real",
        lane="SHARED_CORE",
        capability="evil",
        evidenceLinks=["ev"],
        proposalSource="worker-discovery",
    )
    # Inject caller-supplied AVAILABLE/ACCEPTED on an otherwise invalid proposal
    p["coordinationState"] = "AVAILABLE"  # type: ignore[assignment]
    p["proposalStatus"] = "ACCEPTED"  # type: ignore[assignment]
    res = app.propose_work(p)
    status = app.work_status(res["workId"])
    assert status["coordinationState"] == "NEEDS_RECONCILIATION"
    assert res["proposal"] == "NEEDS_RECONCILIATION"
    assert all(w["workId"] != res["workId"] for w in app.work_next()["work"])


def test_invalid_proposal_with_caller_forced_accepted(tmp_path) -> None:
    app = _app(tmp_path)
    p = _proposal("work:evil2", repository="mncs-language", lane="SHARED_CORE")
    p.pop("capability", None)
    p["evidenceLinks"] = []
    p["coordinationState"] = "NEEDS_RECONCILIATION"  # type: ignore[assignment]
    p["proposalStatus"] = "ACCEPTED"  # type: ignore[assignment]
    res = app.propose_work(p)
    status = app.work_status(res["workId"])
    assert status["current"]["details"]["proposalStatus"] == "NEEDS_RECONCILIATION"
    assert status["coordinationState"] == "NEEDS_RECONCILIATION"


def test_incomplete_proposal_never_returned_by_work_next(tmp_path) -> None:
    app = _app(tmp_path)
    p = _proposal("work:incomplete", repository="mncs-language", lane="SHARED_CORE")
    p.pop("capability", None)
    p["evidenceLinks"] = []
    res = app.propose_work(p)
    assert all(w["workId"] != res["workId"] for w in app.work_next(lane="SHARED_CORE")["work"])


def test_incomplete_proposal_cannot_be_claimed(tmp_path) -> None:
    app = _app(tmp_path)
    p = _proposal("work:incomplete2", repository="mncs-language", lane="SHARED_CORE")
    p.pop("capability", None)
    p["evidenceLinks"] = []
    res = app.propose_work(p)
    status = app.work_status(res["workId"])
    with pytest.raises(WorkProtocolError, match="not claimable"):
        app.claim_work(
            res["workId"],
            actor={"type": "worker", "id": "w"},
            expected_previous_digest=status["currentDigest"],
            lane="SHARED_CORE",
        )


def test_pass_repo_a_cannot_cancel_repo_b(tmp_path) -> None:
    app = _app(tmp_path)
    app.family_health_sweep(
        [
            {
                "repository": "mncs-forge-mcp",
                "outcome": "FAIL",
                "observedAt": "2026-08-27T01:00:00Z",
                "source": "janitor",
                "sourceIdentity": "id1",
                "findingIdentity": "ci:generic",
                "finding": "fail",
                "categories": ["ci"],
            }
        ]
    )
    app.family_health_sweep(
        [
            {
                "repository": "mncs-language",
                "outcome": "FAIL",
                "observedAt": "2026-08-27T01:00:00Z",
                "source": "janitor",
                "sourceIdentity": "id2",
                "findingIdentity": "ci:generic",
                "finding": "fail",
                "categories": ["ci"],
            }
        ]
    )
    app.family_health_sweep(
        [
            {
                "repository": "mncs-forge-mcp",
                "outcome": "PASS",
                "observedAt": "2026-08-27T02:00:00Z",
                "source": "janitor",
                "sourceIdentity": "id3",
                "findingIdentity": "ci:generic",
            }
        ]
    )
    assert len(app.work_next(lane="REPO_HYGIENE", repository="mncs-language", limit=10)["work"]) == 1  # noqa: E501
    assert len(app.work_next(lane="REPO_HYGIENE", repository="mncs-forge-mcp", limit=10)["work"]) == 0  # noqa: E501


def test_stale_pass_cannot_cancel_newer_fail(tmp_path) -> None:
    app = _app(tmp_path)
    app.family_health_sweep(
        [
            {
                "repository": "mncs-forge-mcp",
                "outcome": "FAIL",
                "observedAt": "2026-08-27T02:00:00Z",
                "source": "janitor",
                "sourceIdentity": "id1",
                "findingIdentity": "f1",
                "finding": "fail",
                "categories": ["ci"],
            }
        ]
    )
    res = app.family_health_sweep(
        [
            {
                "repository": "mncs-forge-mcp",
                "outcome": "PASS",
                "observedAt": "2026-08-27T01:00:00Z",
                "source": "janitor",
                "sourceIdentity": "id2",
                "findingIdentity": "f1",
            }
        ]
    )
    assert len(res["superseded"]) == 0
    assert len(app.work_next(lane="REPO_HYGIENE", repository="mncs-forge-mcp", limit=10)["work"]) == 1  # noqa: E501


def test_equal_time_pass_does_not_override(tmp_path) -> None:
    app = _app(tmp_path)
    app.family_health_sweep(
        [
            {
                "repository": "mncs-forge-mcp",
                "outcome": "FAIL",
                "observedAt": "2026-08-27T02:00:00Z",
                "source": "janitor",
                "sourceIdentity": "id1",
                "findingIdentity": "f1",
                "finding": "fail",
                "categories": ["ci"],
            }
        ]
    )
    res = app.family_health_sweep(
        [
            {
                "repository": "mncs-forge-mcp",
                "outcome": "PASS",
                "observedAt": "2026-08-27T02:00:00Z",
                "source": "janitor",
                "sourceIdentity": "id2",
                "findingIdentity": "f1",
            }
        ]
    )
    assert len(res["superseded"]) == 0
    assert len(app.work_next(lane="REPO_HYGIENE", repository="mncs-forge-mcp", limit=10)["work"]) == 1  # noqa: E501


def test_mixed_timezone_offsets_sort_chronologically(tmp_path) -> None:
    app = _app(tmp_path)
    app.family_health_sweep(
        [
            {
                "repository": "mncs-forge-mcp",
                "outcome": "FAIL",
                "observedAt": "2026-08-27T01:00:00Z",
                "source": "janitor",
                "sourceIdentity": "id1",
                "findingIdentity": "f1",
                "finding": "fail",
                "categories": ["ci"],
            }
        ]
    )
    res = app.family_health_sweep(
        [
            {
                "repository": "mncs-forge-mcp",
                "outcome": "PASS",
                "observedAt": "2026-08-27T02:00:00+02:00",
                "source": "janitor",
                "sourceIdentity": "id2",
                "findingIdentity": "f1",
            }
        ]
    )
    assert len(res["superseded"]) == 0
    cov = app.family_coverage()
    proj = next(p for p in cov["projects"] if p["projectId"] == "mncs-forge-mcp")
    assert proj["state"] == CoverageState.ACTIVE_WORK.value


def test_alias_spellings_resolve_to_one_identity() -> None:
    for inp, exp in [
        ("epi13/mncs-forge-mcp", "mncs-forge-mcp"),
        ("mncs-forge-mcp", "mncs-forge-mcp"),
        ("mncs-forge", "mncs-forge-mcp"),
        ("forge", "mncs-forge-mcp"),
        ("https://github.com/epi13/mncs-forge-mcp", "mncs-forge-mcp"),
        ("MNCS-Commons", "mncs-commons"),
        ("commons", "mncs-commons"),
    ]:
        ident = canonical_project_identity(inp)
        assert ident is not None and ident["projectId"] == exp


def test_unknown_alias_fails_closed(tmp_path) -> None:
    app = _app(tmp_path)
    p = _proposal(
        "work:unknown",
        repository="unknown-repo-xyz",
        lane="CONVERSION_PREP",
        sharedCoreImpact=False,
    )
    p.pop("capability", None)
    res = app.propose_work(p)
    assert res["proposal"] == "NEEDS_RECONCILIATION"
    assert all(w["workId"] != res["workId"] for w in app.work_next(limit=10)["work"])


def test_several_findings_for_one_repo_coexist(tmp_path) -> None:
    app = _app(tmp_path)
    obs = [
        {
            "repository": "mncs-forge-mcp",
            "outcome": "FAIL",
            "observedAt": "2026-08-27T01:00:00Z",
            "source": "janitor",
            "sourceIdentity": "id1",
            "findingIdentity": "forge:ci",
            "finding": "ci fail",
            "categories": ["ci"],
        },
        {
            "repository": "mncs-forge-mcp",
            "outcome": "FAIL",
            "observedAt": "2026-08-27T01:00:00Z",
            "source": "janitor",
            "sourceIdentity": "id2",
            "findingIdentity": "forge:pin",
            "finding": "pin stale",
            "categories": ["pin"],
        },
    ]
    res = app.family_health_sweep(obs)
    assert len(res["proposals"]) == 2
    assert len(app.work_next(lane="REPO_HYGIENE", repository="mncs-forge-mcp", limit=10)["work"]) == 2  # noqa: E501


def test_duplicate_finding_attaches(tmp_path) -> None:
    app = _app(tmp_path)
    fail = {
        "repository": "mncs-forge-mcp",
        "outcome": "FAIL",
        "observedAt": "2026-08-27T01:00:00Z",
        "source": "janitor",
        "sourceIdentity": "id1",
        "findingIdentity": "forge:ci:dup",
        "finding": "fail",
        "categories": ["ci"],
    }
    app.family_health_sweep([fail])
    second = app.family_health_sweep([{**fail, "observedAt": "2026-08-27T02:00:00Z", "sourceIdentity": "id2"}])  # noqa: E501
    assert second["proposals"][0]["proposal"] == "ATTACHED"
    assert len(app.work_next(lane="REPO_HYGIENE", repository="mncs-forge-mcp", limit=10)["work"]) == 1  # noqa: E501


def test_latest_pass_supersedes_only_matching(tmp_path) -> None:
    app = _app(tmp_path)
    app.family_health_sweep(
        [
            {
                "repository": "mncs-forge-mcp",
                "outcome": "FAIL",
                "observedAt": "2026-08-27T01:00:00Z",
                "source": "janitor",
                "sourceIdentity": "id1",
                "findingIdentity": "forge:ci:only",
                "finding": "fail",
                "categories": ["ci"],
            }
        ]
    )
    app.family_health_sweep(
        [
            {
                "repository": "mncs-forge-mcp",
                "outcome": "FAIL",
                "observedAt": "2026-08-27T01:00:00Z",
                "source": "janitor",
                "sourceIdentity": "id2",
                "findingIdentity": "forge:pin:other",
                "finding": "fail2",
                "categories": ["pin"],
            }
        ]
    )
    res = app.family_health_sweep(
        [
            {
                "repository": "mncs-forge-mcp",
                "outcome": "PASS",
                "observedAt": "2026-08-27T02:00:00Z",
                "source": "janitor",
                "sourceIdentity": "id3",
                "findingIdentity": "forge:ci:only",
            }
        ]
    )
    assert len(res["superseded"]) == 1
    assert len(app.work_next(lane="REPO_HYGIENE", repository="mncs-forge-mcp", limit=10)["work"]) == 1  # noqa: E501


def test_ambiguous_capability_is_non_claimable(tmp_path) -> None:
    app = _app(tmp_path)
    first = app.propose_work(_proposal("work:amb-first", capability="mask.reduction"))
    assert first["proposal"] == "ACCEPTED"
    second = app.propose_work(_proposal("work:amb-second", capability="numeric.masked.reduce"))
    assert second["proposal"] == "NEEDS_RECONCILIATION"
    assert all(w["workId"] != second["workId"] for w in app.work_next(lane="SHARED_CORE", limit=10)["work"])  # noqa: E501
    status = app.work_status(second["workId"])
    with pytest.raises(WorkProtocolError, match="not claimable"):
        app.claim_work(
            second["workId"],
            actor={"type": "worker", "id": "w"},
            expected_previous_digest=status["currentDigest"],
            lane="SHARED_CORE",
        )


def test_exact_capability_duplicates_attach(tmp_path) -> None:
    app = _app(tmp_path)
    first = app.propose_work(_proposal("work:exact1", capability="mask.reduction"))
    second = app.propose_work(_proposal("work:exact2", capability="mask.reduce"))
    assert second["proposal"] == "ATTACHED"
    assert second["workId"] == first["workId"]
    status = app.work_status(first["workId"])
    assert len(status["current"]["details"].get("attachments", [])) == 1


def test_active_work_coverage_is_derived(tmp_path) -> None:
    app = _app(tmp_path)
    cov0 = {p["projectId"]: p["state"] for p in app.family_coverage()["projects"]}
    assert cov0["mncs-language-service"] != CoverageState.ACTIVE_WORK.value
    work = app.submit_work(
        {
            "workId": "work:active-test",
            "submittingConsumer": {"type": "agent", "id": "a"},
            "project": {"id": "mncs-family", "revision": "test"},
            "repository": "mncs-language-service",
            "affectedRepositories": ["mncs-language-service"],
            "task": "test",
            "lane": "CONVERSION_PREP",
            "priority": 10,
        }
    )
    cov1 = {p["projectId"]: p["state"] for p in app.family_coverage()["projects"]}
    assert cov1["mncs-language-service"] == CoverageState.ACTIVE_WORK.value
    claimed = app.claim_work(
        "work:active-test",
        actor={"type": "worker", "id": "w1"},
        expected_previous_digest=work["currentDigest"],
        lane="CONVERSION_PREP",
    )
    running = app.transition_work(
        "work:active-test",
        {
            "state": "running",
            "coordinationState": "IN_PROGRESS",
            "actor": {"type": "worker", "id": "w1"},
            "expectedPreviousDigest": claimed["currentDigest"],
        },
    )
    verifying = app.transition_work(
        "work:active-test",
        {
            "state": "checkpointed",
            "coordinationState": "VERIFYING",
            "actor": {"type": "worker", "id": "w1"},
            "expectedPreviousDigest": running["currentDigest"],
            "progress": {"percent": 100},
        },
    )
    app.transition_work(
        "work:active-test",
        {
            "state": "completed",
            "coordinationState": "COMPLETE",
            "actor": {"type": "worker", "id": "w1"},
            "expectedPreviousDigest": verifying["currentDigest"],
            "result": {"terminalOutcome": "PASS", "evidence": [{"id": "ev", "status": "PASS"}]},
        },
    )
    cov2 = {p["projectId"]: p["state"] for p in app.family_coverage()["projects"]}
    assert cov2["mncs-language-service"] != CoverageState.ACTIVE_WORK.value


def test_shared_core_wait_requires_actual_dependency(tmp_path) -> None:
    app = _app(tmp_path)
    core = app.submit_work(_proposal("work:core-dep", capability="numeric.vector.reduce"))
    consumer = app.submit_work(
        {
            "workId": "work:consumer-wait",
            "submittingConsumer": {"type": "agent", "id": "a"},
            "project": {"id": "mncs-family", "revision": "test"},
            "repository": "mncs-tui",
            "affectedRepositories": ["mncs-tui"],
            "task": "wait",
            "lane": "CONVERSION_PREP",
            "priority": 10,
            "dependencies": [core["workId"]],
        }
    )
    claimed = app.claim_work(
        consumer["workId"],
        actor={"type": "worker", "id": "w2"},
        expected_previous_digest=consumer["currentDigest"],
        lane="CONVERSION_PREP",
    )
    app.transition_work(
        consumer["workId"],
        {
            "state": "blocked",
            "coordinationState": "BLOCKED",
            "actor": {"type": "worker", "id": "w2"},
            "expectedPreviousDigest": claimed["currentDigest"],
            "blockers": ["waiting"],
        },
    )
    cov = {p["projectId"]: p["state"] for p in app.family_coverage()["projects"]}
    assert cov["mncs-tui"] == CoverageState.WAITING_SHARED_CORE.value
    ordinary = app.submit_work(
        {
            "workId": "work:ordinary",
            "submittingConsumer": {"type": "agent", "id": "a"},
            "project": {"id": "mncs-family", "revision": "test"},
            "repository": "mncs-lineage",
            "affectedRepositories": ["mncs-lineage"],
            "task": "ordinary",
            "lane": "CONVERSION_PREP",
            "priority": 10,
            "blockingWorkIds": ["not-core"],
        }
    )
    claimed2 = app.claim_work(
        ordinary["workId"],
        actor={"type": "worker", "id": "w3"},
        expected_previous_digest=ordinary["currentDigest"],
        lane="CONVERSION_PREP",
    )
    app.transition_work(
        ordinary["workId"],
        {
            "state": "blocked",
            "coordinationState": "BLOCKED",
            "actor": {"type": "worker", "id": "w3"},
            "expectedPreviousDigest": claimed2["currentDigest"],
            "blockers": ["ordinary"],
        },
    )
    cov2 = {p["projectId"]: p["state"] for p in app.family_coverage()["projects"]}
    assert cov2["mncs-lineage"] == CoverageState.BLOCKED.value


def test_lane_scope_enforcement(tmp_path) -> None:
    assert scope_decision("DOCUMENTATION", "mncs-tui/docs/foo.md", assigned_repository="mncs-tui")["allowed"] is True  # noqa: E501
    assert scope_decision("DOCUMENTATION", "mncs-tui/src/foo.py", assigned_repository="mncs-tui")["allowed"] is False  # noqa: E501
    assert scope_decision("VERIFICATION", "mncs-tui/tests/test.py", assigned_repository="mncs-tui")["allowed"] is True  # noqa: E501
    assert scope_decision("VERIFICATION", "mncs-tui/src/foo.py", assigned_repository="mncs-tui")["allowed"] is False  # noqa: E501
    assert scope_decision("REPO_HYGIENE", "mncs-tui/src/foo.py", assigned_repository="mncs-tui")["allowed"] is True  # noqa: E501
    assert scope_decision("SHARED_CORE", "mncs-language/src/foo.py")["allowed"] is False
    assert scope_decision("VERIFICATION", "mncs-tui/tests/test.py")["code"] == "SCOPE_REPOSITORY_REQUIRED"  # noqa: E501
    assert lane_policy("CONVERSION_PREP").lane == "CONVERSION_PREP"
    assert lane_policy("REPO_HYGIENE").lane == "REPO_HYGIENE"


def test_shared_core_single_writer(tmp_path) -> None:
    app = _app(tmp_path)
    c1 = app.propose_work(_proposal("work:sc1", capability="cap.one"))
    c2 = app.propose_work(_proposal("work:sc2", capability="cap.two"))
    app.claim_work(c1["workId"], actor={"type": "worker", "id": "w1"}, expected_previous_digest=c1["currentDigest"], lane="SHARED_CORE")  # noqa: E501
    with pytest.raises(WorkProtocolError, match="SHARED_CORE"):
        app.claim_work(c2["workId"], actor={"type": "worker", "id": "w2"}, expected_previous_digest=c2["currentDigest"], lane="SHARED_CORE")  # noqa: E501


def test_one_substantive_active_claim_per_worker(tmp_path) -> None:
    app = _app(tmp_path)
    w1 = app.submit_work(
        {
            "workId": "work:w1",
            "submittingConsumer": {"type": "agent", "id": "a"},
            "project": {"id": "mncs-family", "revision": "test"},
            "repository": "mncs-tui",
            "affectedRepositories": ["mncs-tui"],
            "task": "t1",
            "lane": "CONVERSION_PREP",
            "priority": 10,
        }
    )
    w2 = app.submit_work(
        {
            "workId": "work:w2",
            "submittingConsumer": {"type": "agent", "id": "a"},
            "project": {"id": "mncs-family", "revision": "test"},
            "repository": "mncs-tui",
            "affectedRepositories": ["mncs-tui"],
            "task": "t2",
            "lane": "CONVERSION_PREP",
            "priority": 10,
        }
    )
    app.claim_work(w1["workId"], actor={"type": "worker", "id": "same-worker"}, expected_previous_digest=w1["currentDigest"], lane="CONVERSION_PREP")  # noqa: E501
    with pytest.raises(WorkProtocolError, match="active substantive claim"):
        app.claim_work(w2["workId"], actor={"type": "worker", "id": "same-worker"}, expected_previous_digest=w2["currentDigest"], lane="CONVERSION_PREP")  # noqa: E501


def test_naive_timestamp_rejected(tmp_path) -> None:
    app = _app(tmp_path)
    with pytest.raises(ValueError, match="timezone"):
        app.family_health_sweep(
            [
                {
                    "repository": "mncs-forge-mcp",
                    "outcome": "FAIL",
                    "observedAt": "2026-08-27T01:00:00",
                    "source": "janitor",
                    "sourceIdentity": "id1",
                    "findingIdentity": "f1",
                    "finding": "fail",
                    "categories": ["ci"],
                }
            ]
        )
