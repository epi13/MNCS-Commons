from __future__ import annotations

import pytest

from mncs_commons.application import CommonsApplication
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
    assert projects["mncs-language"]["state"] == CoverageState.HEALTHY_NO_WORK.value
    assert projects["mncs-language"]["work"] == []
    assert coverage["atlas"]["schedulingAuthority"] is False
    hygiene = next(item for item in coverage["lanes"] if item["lane"] == "REPO_HYGIENE")
    assert hygiene["represented"] == hygiene["eligible"] == 17
