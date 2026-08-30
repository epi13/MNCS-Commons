from __future__ import annotations

from pathlib import Path

import pytest

from mncs_commons.application import CommonsApplication
from mncs_commons.bootstrap import seed_work
from mncs_commons.family_registry import CoverageState, family_registry
from mncs_commons.lane_policy import lane_policy, scope_decision
from mncs_commons.store import CommonsStore
from mncs_commons.work import WorkProtocolError, new_work_record


def _request(work_id: str, *, lane: str = "CONVERSION_PREP") -> dict[str, object]:
    return {
        "workId": work_id,
        "submittingConsumer": {"type": "agent", "id": "agent:test"},
        "project": {"id": "mncs-family", "revision": "test"},
        "repository": "mncs-tui",
        "task": "Prepare a bounded conversion fixture.",
        "lane": lane,
        "affectedRepositories": ["mncs-tui"],
        "priority": 10,
        "capabilityRequirements": ["mncs-language:source-fixtures"],
    }


def _application(tmp_path) -> CommonsApplication:
    store = CommonsStore(tmp_path / "store")
    store.init()
    return CommonsApplication(store)


def test_lane_policy_and_scope_are_machine_readable() -> None:
    policy = lane_policy("CONVERSION_PREP").as_dict()
    assert policy["lane"] == "CONVERSION_PREP"
    assert "work_requests" in policy["mayPublish"]
    assert (
        scope_decision(
            "CONVERSION_PREP", "mncs-tui/examples/layout.mncs", assigned_repository="mncs-tui"
        )["allowed"]
        is True
    )
    assert (
        scope_decision(
            "CONVERSION_PREP", "mncs-language/src/compiler.py", assigned_repository="mncs-tui"
        )["allowed"]
        is False
    )


def test_invalid_lane_policy_combinations_fail_closed() -> None:
    with pytest.raises(WorkProtocolError, match="shared-core impact"):
        new_work_record({**_request("work:bad-safe"), "sharedCoreImpact": True})
    with pytest.raises(WorkProtocolError, match="SHARED_CORE"):
        new_work_record(
            {**_request("work:bad-core", lane="SHARED_CORE"), "sharedCoreImpact": False}
        )
    with pytest.raises(WorkProtocolError, match="unsupported"):
        new_work_record({**_request("work:bad-lane"), "lane": "NOPE"})


def test_claims_are_optimistic_bounded_and_lifecycle_evidence_bearing(tmp_path) -> None:
    app = _application(tmp_path)
    first = app.submit_work(_request("work:first"))
    second = app.submit_work(_request("work:second"))

    selected = app.work_next(
        lane="CONVERSION_PREP",
        repository="mncs-tui",
        capabilities={"mncs-language:source-fixtures"},
    )
    assert [item["workId"] for item in selected["work"]] == ["work:first"]
    claimed = app.claim_work(
        "work:first",
        actor={"type": "worker", "id": "worker:test"},
        expected_previous_digest=first["currentDigest"],
        session_id="session:test",
        lane="CONVERSION_PREP",
    )
    assert claimed["state"] == "assigned"
    assert app.work_status("work:first")["coordinationState"] == "CLAIMED"
    with pytest.raises(WorkProtocolError, match="not claimable"):
        app.claim_work(
            "work:first",
            actor={"type": "worker", "id": "worker:other"},
            expected_previous_digest=first["currentDigest"],
            lane="CONVERSION_PREP",
        )
    with pytest.raises(WorkProtocolError, match="active substantive claim"):
        app.claim_work(
            "work:second",
            actor={"type": "worker", "id": "worker:test"},
            expected_previous_digest=second["currentDigest"],
            lane="CONVERSION_PREP",
        )

    running = app.transition_work(
        "work:first",
        {
            "state": "running",
            "coordinationState": "IN_PROGRESS",
            "actor": {"type": "worker", "id": "worker:test"},
            "expectedPreviousDigest": claimed["currentDigest"],
        },
    )
    verifying = app.transition_work(
        "work:first",
        {
            "state": "checkpointed",
            "coordinationState": "VERIFYING",
            "actor": {"type": "worker", "id": "worker:test"},
            "expectedPreviousDigest": running["currentDigest"],
            "progress": {"percent": 100},
        },
    )
    complete = app.transition_work(
        "work:first",
        {
            "state": "completed",
            "coordinationState": "COMPLETE",
            "actor": {"type": "worker", "id": "worker:test"},
            "expectedPreviousDigest": verifying["currentDigest"],
            "result": {
                "terminalOutcome": "PASS",
                "evidence": [{"id": "fixture:conversion", "status": "PASS"}],
                "artifacts": [{"id": "commit:example"}],
            },
        },
    )
    assert complete["state"] == "completed"
    assert app.work_status("work:first")["coordinationState"] == "COMPLETE"


def test_blocked_lane_requires_blockers_and_shared_core_requests_are_structured(tmp_path) -> None:
    app = _application(tmp_path)
    submitted = app.submit_work(_request("work:block"))
    claimed = app.claim_work(
        "work:block",
        actor={"type": "worker", "id": "worker:blocker"},
        expected_previous_digest=submitted["currentDigest"],
        lane="CONVERSION_PREP",
    )
    with pytest.raises(WorkProtocolError, match="blockers"):
        app.transition_work(
            "work:block",
            {
                "state": "blocked",
                "coordinationState": "BLOCKED",
                "actor": {"type": "worker", "id": "worker:blocker"},
                "expectedPreviousDigest": claimed["currentDigest"],
            },
        )
    blocked = app.transition_work(
        "work:block",
        {
            "state": "blocked",
            "coordinationState": "BLOCKED",
            "actor": {"type": "worker", "id": "worker:blocker"},
            "expectedPreviousDigest": claimed["currentDigest"],
            "blockers": ["missing capability: numeric.vector.reduce"],
        },
    )
    assert app.work_status("work:block")["coordinationState"] == "BLOCKED"
    reclaimed = app.claim_work(
        "work:block",
        actor={"type": "worker", "id": "worker:follow-up"},
        expected_previous_digest=blocked["currentDigest"],
        lane="CONVERSION_PREP",
    )
    assert reclaimed["state"] == "assigned"
    escalation = app.submit_work(
        {
            **_request("work:capability-request", lane="SHARED_CORE"),
            "task": "Add numeric.vector.reduce with the documented semantics.",
            "sharedCoreImpact": True,
            "capability": "numeric.vector.reduce",
            "reason": "native training loss calculation",
            "expectedSemantics": "bounded deterministic reduction",
            "blockingWorkIds": ["work:block"],
            "evidenceLinks": ["fixture:loss"],
            "capabilityRequirements": [],
            "createdFrom": ["work:block", "fixture:loss"],
        }
    )
    assert escalation["state"] == "submitted"
    current = app.work_status("work:capability-request")["current"]["details"]
    assert current["lane"] == "SHARED_CORE"
    assert current["createdFrom"] == ["work:block", "fixture:loss"]
    assert current["capability"] == "numeric.vector.reduce"
    assert current["blockingWorkIds"] == ["work:block"]
    assert blocked["state"] == "blocked"


def test_family_registry_covers_canonical_roster_and_safe_lanes() -> None:
    registry = family_registry()
    assert len(registry["projects"]) == 17
    assert {item["id"] for item in registry["projects"]} >= {
        "mncs-language-service",
        "mncs-tui",
        "mncs-rights-provenance",
    }
    assert all(
        {"DOCUMENTATION", "REPO_HYGIENE"}.issubset(set(item["eligibleWorkLanes"]))
        for item in registry["projects"]
    )


def test_family_coverage_keeps_no_task_projects_visible(tmp_path) -> None:
    app = _application(tmp_path)
    app.submit_work(_request("work:coverage", lane="REPO_HYGIENE"))
    coverage = app.family_coverage()
    assert coverage["projectCount"] == 17
    projects = {item["projectId"]: item for item in coverage["projects"]}
    assert projects["mncs-language"]["considered"] is True
    assert projects["mncs-language"]["state"] == CoverageState.NEEDS_REVIEW.value
    assert projects["mncs-language"]["work"] == []
    assert coverage["atlas"]["schedulingAuthority"] is False
    hygiene = next(item for item in coverage["lanes"] if item["lane"] == "REPO_HYGIENE")
    assert hygiene["represented"] == hygiene["eligible"] == 17


def _proposal(work_id: str, *, capability: str, repository: str = "mncs-language"):
    return {
        "workId": work_id,
        "submittingConsumer": {"type": "worker", "id": work_id},
        "project": {"id": "mncs-family", "revision": "test"},
        "repository": repository,
        "affectedRepositories": [repository],
        "task": f"Provide {capability} for a bounded consumer.",
        "lane": "SHARED_CORE",
        "sharedCoreImpact": True,
        "capability": capability,
        "evidenceLinks": [f"fixture:{work_id}"],
        "proposalSource": "worker-discovery",
        "priority": 20,
    }


def test_fresh_seed_excludes_stale_work_and_reconciles_persistent_history(tmp_path) -> None:
    store_path = tmp_path / "store"
    result = seed_work(store_path)
    assert result["count"] == 10
    fresh_ids = {item["workId"] for item in result["seeded"]}
    assert "work:seed-shared-vector-reduce" not in fresh_ids
    app = CommonsApplication(CommonsStore(store_path))
    app.require_store().init()
    stale = app.submit_work(
        {
            **_request("work:seed-shared-vector-reduce", lane="SHARED_CORE"),
            "sharedCoreImpact": True,
            "capability": "numeric.vector.reduce",
            "evidenceLinks": ["historical:mnel"],
        }
    )
    reconciled = seed_work(store_path)
    assert reconciled["reconciledCount"] == 1
    assert stale["state"] == "submitted"
    assert app.work_status("work:seed-shared-vector-reduce")["coordinationState"] == "SUPERSEDED"
    assert (
        app.work_status("work:seed-shared-vector-reduce")["current"]["details"]["result"][
            "terminalOutcome"
        ]
        == "SUPERSEDED"
    )
    assert app.work_next(repository="mncs-language")["work"] == []


def test_proposals_deduplicate_capabilities_and_conservatively_reconcile_overlap(tmp_path) -> None:
    app = _application(tmp_path)
    first = app.propose_work(_proposal("work:core-mask", capability="mask.reduction"))
    assert first["proposal"] == "ACCEPTED"
    second = app.propose_work(
        _proposal("work:core-mask-consumer", capability="mask.reduce")
    )
    assert second["proposal"] == "ATTACHED"
    status = app.work_status(first["workId"])
    assert len(status["current"]["details"]["attachments"]) == 1
    distinct = app.propose_work(_proposal("work:core-vector", capability="numeric.vector.reduce"))
    assert distinct["proposal"] == "ACCEPTED"
    ambiguous = app.propose_work(
        _proposal("work:core-ambiguous", capability="numeric.masked.reduce")
    )
    assert ambiguous["proposal"] == "NEEDS_RECONCILIATION"
    assert app.work_next(lane="SHARED_CORE")["work"]
    with pytest.raises(WorkProtocolError, match="not claimable"):
        app.claim_work(
            ambiguous["workId"],
            actor={"type": "worker", "id": "worker:ambiguous"},
            expected_previous_digest=ambiguous["currentDigest"],
            lane="SHARED_CORE",
        )


def test_coverage_states_require_actual_work_and_actual_shared_core_dependency(tmp_path) -> None:
    app = _application(tmp_path)
    empty = {item["projectId"]: item for item in app.family_coverage()["projects"]}
    assert empty["mncs-language-service"]["state"] != CoverageState.ACTIVE_WORK.value
    core = app.submit_work(_proposal("work:core-dependency", capability="numeric.vector.reduce"))
    consumer = app.submit_work(
        {
            **_request("work:consumer-waiting"),
            "repository": "mncs-tui",
            "affectedRepositories": ["mncs-tui"],
            "dependencies": [core["workId"]],
        }
    )
    claimed = app.claim_work(
        consumer["workId"],
        actor={"type": "worker", "id": "worker:consumer"},
        expected_previous_digest=consumer["currentDigest"],
        lane="CONVERSION_PREP",
    )
    app.transition_work(
        consumer["workId"],
        {
            "state": "blocked",
            "coordinationState": "BLOCKED",
            "actor": {"type": "worker", "id": "worker:consumer"},
            "expectedPreviousDigest": claimed["currentDigest"],
            "blockers": ["waiting for shared core"],
        },
    )
    coverage = {item["projectId"]: item for item in app.family_coverage()["projects"]}
    assert coverage["mncs-tui"]["state"] == CoverageState.WAITING_SHARED_CORE.value
    ordinary = app.submit_work(
        {
            **_request("work:ordinary-blocker"),
            "repository": "mncs-lineage",
            "affectedRepositories": ["mncs-lineage"],
            "blockingWorkIds": ["not-a-core-work"],
        }
    )
    ordinary_claim = app.claim_work(
        ordinary["workId"],
        actor={"type": "worker", "id": "worker:ordinary"},
        expected_previous_digest=ordinary["currentDigest"],
        lane="CONVERSION_PREP",
    )
    app.transition_work(
        ordinary["workId"],
        {
            "state": "blocked",
            "coordinationState": "BLOCKED",
            "actor": {"type": "worker", "id": "worker:ordinary"},
            "expectedPreviousDigest": ordinary_claim["currentDigest"],
            "blockers": ["ordinary blocker"],
        },
    )
    coverage = {item["projectId"]: item for item in app.family_coverage()["projects"]}
    assert coverage["mncs-lineage"]["state"] == CoverageState.BLOCKED.value


def test_health_sweep_creates_fresh_hygiene_and_resolves_it_on_pass(tmp_path) -> None:
    app = _application(tmp_path)
    failure = {
        "repository": "mncs-forge-mcp",
        "outcome": "FAIL",
        "observedAt": "2026-08-27T01:00:00Z",
        "source": "janitor",
        "sourceIdentity": "github://actions/run/now",
        "findingIdentity": "forge:ci:windows",
        "finding": "Windows health check failed",
        "categories": ["ci"],
    }
    first = app.family_health_sweep([failure])
    assert first["proposals"][0]["proposal"] == "ACCEPTED"
    project = next(
        item
        for item in app.family_coverage()["projects"]
        if item["projectId"] == "mncs-forge-mcp"
    )
    assert project["state"] == CoverageState.ACTIVE_WORK.value
    second = app.family_health_sweep([{**failure, "observedAt": "2026-08-27T02:00:00Z"}])
    assert second["proposals"][0]["proposal"] == "ATTACHED"
    passing = app.family_health_sweep(
        [{**failure, "outcome": "PASS", "observedAt": "2026-08-27T03:00:00Z"}]
    )
    assert len(passing["superseded"]) == 1
    assert app.work_next(lane="REPO_HYGIENE", repository="mncs-forge-mcp")["work"] == []
    project = next(
        item
        for item in app.family_coverage()["projects"]
        if item["projectId"] == "mncs-forge-mcp"
    )
    assert project["state"] == CoverageState.HEALTHY_NO_WORK.value


def test_exact_cross_source_roster_and_aliases() -> None:
    projects = family_registry()["projects"]
    standard = {
        "components": [
            {
                "id": project["id"],
                "repository": {"url": f"https://github.com/{project['repository']}"},
            }
            for project in projects
        ]
    }
    atlas = {
        "projects": [
            {
                "id": {
                    "mncs-forge-mcp": "forge",
                    "mncs-control-mcp": "control",
                }.get(project["id"], project["id"]),
                "repository": (
                    None
                    if project["id"] == "mncs-control-mcp"
                    else f"https://github.com/{project['repository']}"
                ),
            }
            for project in projects
        ],
        "operator_components": [],
    }
    result = CommonsApplication.family_consistency(standard, atlas)
    assert result["valid"] is True
    assert result["canonicalProjectCount"] == 17
    atlas["projects"][0]["repository"] = "https://github.com/example/wrong-repository"
    assert CommonsApplication.family_consistency(standard, atlas)["valid"] is False


def test_scope_checker_enforces_machine_policy_and_shared_core_boundaries() -> None:
    assert (
        scope_decision(
            "DOCUMENTATION", "mncs-tui/src/main.py", assigned_repository="mncs-tui"
        )["allowed"]
        is False
    )
    assert (
        scope_decision(
            "VERIFICATION", "mncs-tui/tests/test_layout.py", assigned_repository="mncs-tui"
        )["allowed"]
        is True
    )
    assert (
        scope_decision(
            "REPO_HYGIENE", "mncs-tui/src/main.py", assigned_repository="mncs-tui"
        )["allowed"]
        is True
    )
    assert scope_decision("SHARED_CORE", "mncs-language/src/compiler.py")["allowed"] is False
    assert (
        scope_decision("VERIFICATION", "mncs-tui/tests/test.py")["code"]
        == "SCOPE_REPOSITORY_REQUIRED"
    )
    assert scope_decision(
        "REPO_LOCAL",
        "mncs-tui/src/main.py",
        assigned_repository="mncs-tui",
        allowed_write_scope=["assigned_repo/tests/**"],
    )["allowed"] is False
    assert "REPO_HYGIENE" in Path("docs/VOCABULARY.md").read_text()


def test_selection_uses_deterministic_coverage_tie_break_and_follow_on_relationship(
    tmp_path,
) -> None:
    app = _application(tmp_path)
    hot = app.submit_work(
        {**_request("work:hot"), "capabilityRequirements": [], "priority": 50}
    )
    app.claim_work(
        "work:hot",
        actor={"type": "worker", "id": "worker:hot"},
        expected_previous_digest=hot["currentDigest"],
        lane="CONVERSION_PREP",
    )
    quiet = app.submit_work(
        {
            **_request("work:quiet"),
            "repository": "mncs-lineage",
            "affectedRepositories": ["mncs-lineage"],
            "capabilityRequirements": [],
            "priority": 50,
        }
    )
    selected = app.work_next(limit=1)
    assert selected["work"][0]["workId"] == quiet["workId"]
    completed = app.transition_work(
        "work:hot",
        {
            "state": "running",
            "actor": {"type": "worker", "id": "worker:hot"},
            "expectedPreviousDigest": app.work_status("work:hot")["currentDigest"],
        },
    )
    app.transition_work(
        "work:hot",
        {
            "state": "completed",
            "coordinationState": "COMPLETE",
            "actor": {"type": "worker", "id": "worker:hot"},
            "expectedPreviousDigest": completed["currentDigest"],
            "result": {
                "terminalOutcome": "PASS",
                "evidence": [{"id": "fixture:done", "status": "PASS"}],
            },
            "followOnRequests": ["work:quiet"],
        },
    )
    assert any(
        edge["type"] == "follows_up" and edge["target"] == "work:quiet"
        for edge in app.work_status("work:hot")["current"]["relationships"]
    )
