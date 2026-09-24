from __future__ import annotations

import pytest

from mncs_commons.obligation_plan import (
    OBLIGATION_PLAN_SCHEMA,
    ObligationPlanError,
    inventory_identity,
    obligation_plan_identity,
    validate_inventory,
    validate_obligation_plan,
)


def _inventory() -> dict:
    return {
        "schema_version": "mncs-family.verification-obligation-inventory/v1",
        "repository": "fixture",
        "revision": 1,
        "obligations": [
            {
                "identity": "fixture.semantic.regression",
                "title": "native semantic regression",
                "guarantee_domain": "semantic",
                "evidence_role": "canonical_regression",
                "lifecycle": "permanent",
                "scope": "local",
                "subjects": ["fixture:function"],
                "invalidation_dependencies": ["fixture.contract/1"],
                "executor": {
                    "provider": "mncs-test",
                    "kind": "native_first_class_test",
                    "entrypoint": "mncs test",
                    "declaration_identities": ["fixture:test"],
                },
                "evidence_identity": {
                    "subject_fields": ["subject_fingerprint"],
                    "definition_fields": ["obligation_identity"],
                    "execution_fields": ["test_case_identity", "verifier_identity"],
                },
            }
        ],
    }


def test_inventory_is_identity_bound_and_orthogonal() -> None:
    normalized = validate_inventory(_inventory())
    assert inventory_identity(normalized) != ""
    assert normalized["obligations"][0]["evidence_role"] == "canonical_regression"


def test_plan_distinguishes_current_reuse_from_new_execution() -> None:
    plan = {
        "schema_version": OBLIGATION_PLAN_SCHEMA,
        "verification_plan_id": "v-plan",
        "source": {"path": "source.mncs", "sha256": "a" * 64},
        "impact_identity": "impact",
        "inventory": {"repository": "fixture", "revision": 1, "identity": "inventory"},
        "obligations": [
            {
                "identity": "fixture.semantic.regression",
                "status": "current",
                "lifecycle": "permanent",
                "guarantee_domain": "semantic",
                "evidence_role": "canonical_regression",
                "reason": "current identity-bound PASS evidence",
                "evidence_identities": ["evidence:one"],
                "test_case_identities": ["test:one"],
            }
        ],
        "evidence": [
            {
                "status": "PASS",
                "evidence_identity": "evidence:one",
                "obligation_identity": "fixture.semantic.regression",
                "subject_fingerprint": "a" * 64,
            }
        ],
        "stop": {
            "sufficient_to_stop": True,
            "required_obligation_identities": ["fixture.semantic.regression"],
            "new_execution_required": [],
            "escalation_reasons": [],
            "boundary": "changed_item",
        },
    }
    plan["obligation_plan_id"] = obligation_plan_identity(plan)
    assert validate_obligation_plan(plan)["obligation_plan_id"] == plan["obligation_plan_id"]


def test_duplicate_inventory_identity_fails_closed() -> None:
    value = _inventory()
    value["obligations"].append(dict(value["obligations"][0]))
    try:
        validate_inventory(value)
    except ObligationPlanError as error:
        assert error.code == "DUPLICATE_IDENTITY"
    else:
        raise AssertionError("duplicate obligation identity was accepted")


def _repository_plan(
    *,
    statuses: dict[str, str] | None = None,
    evidence_statuses: dict[str, str] | None = None,
    evidence_reasons: dict[str, str] | None = None,
    fingerprint_override: dict[str, str] | None = None,
    complete: bool = True,
    missing: list[str] | None = None,
    scope: str = "repository_canonical",
) -> dict:
    required = ["fixture.repo.model", "fixture.repo.runtime"]
    missing = list(missing or [])
    selected_ids = [identity for identity in required if identity not in missing]
    statuses = statuses or {identity: "current" for identity in selected_ids}
    evidence_statuses = evidence_statuses or {identity: "PASS" for identity in selected_ids}
    evidence_reasons = evidence_reasons or {}
    repository_identity = "fixture"
    repository_fingerprint = "a" * 64
    repository = {
        "identity": repository_identity,
        "revision": "0123456789abcdef",
        "fingerprint": repository_fingerprint,
        "inventory_identity": "b" * 64,
        "scope": scope,
        "complete": complete,
        "required_obligation_identities": required,
        "selected_obligation_identities": selected_ids,
        "missing_obligation_identities": missing,
        "compiler_test_inventories": [
            {
                "path": "tests/runtime.mncs",
                "scope": "source_module",
                "identity": "c" * 64,
                "test_case_identities": ["mncs:test-case:fixture.runtime::contract"],
            }
        ],
    }
    obligations = []
    evidence = []
    for index, identity in enumerate(selected_ids):
        definition_identity = ("1" if index == 0 else "2") * 64
        subject_fingerprint = ("3" if index == 0 else "4") * 64
        executor_identity = ("5" if index == 0 else "6") * 64
        verifier_identity = ("7" if index == 0 else "8") * 64
        invalidation_identity = ("9" if index == 0 else "a") * 64
        subject_identity = f"mncs.repository-test:fixture:{identity.rsplit('.', 1)[-1]}"
        evidence_status = evidence_statuses.get(identity, "PASS")
        evidence_fingerprint = (fingerprint_override or {}).get(identity, repository_fingerprint)
        evidence_identity = f"evidence:{identity}"
        obligations.append(
            {
                "identity": identity,
                "scope": "repository_canonical",
                "status": statuses.get(identity, "current"),
                "lifecycle": "permanent",
                "guarantee_domain": "integration",
                "evidence_role": "canonical_regression",
                "reason": "current evidence" if statuses.get(identity, "current") == "current" else "execution required",
                "evidence_identities": [evidence_identity],
                "test_case_identities": [],
                "definition_identity": definition_identity,
                "subject_identity": subject_identity,
                "subject_fingerprint": subject_fingerprint,
                "executor_identity": executor_identity,
                "verifier_identity": verifier_identity,
                "invalidation_identity": invalidation_identity,
                "executor": {
                    "provider": "mncs-test",
                    "kind": "external_integration",
                    "entrypoint": f"project-test:{identity}",
                    "argv": ["cargo", "test", "--package", "fixture", "--package"],
                    "working_directory": ".",
                    "timeout_seconds": 60,
                },
            }
        )
        evidence.append(
            {
                "status": evidence_status,
                "evidence_identity": evidence_identity,
                "obligation_identity": identity,
                "repository_identity": repository_identity,
                "repository_fingerprint": evidence_fingerprint,
                "subject_identity": subject_identity,
                "subject_fingerprint": subject_fingerprint,
                "definition_identity": definition_identity,
                "executor_identity": executor_identity,
                "verifier_identity": verifier_identity,
                "invalidation_identity": invalidation_identity,
                "reason": evidence_reasons.get(identity, "executor evidence"),
            }
        )
    plan = {
        "schema_version": OBLIGATION_PLAN_SCHEMA,
        "verification_plan_id": "verification-plan-fixture",
        "source": {"path": "library/std/process.mncs", "sha256": "a" * 64},
        "impact_identity": "impact-fixture",
        "inventory": {"repository": repository_identity, "revision": 1, "identity": "inventory-fixture"},
        "repository": repository,
        "obligations": obligations,
        "excluded": [],
        "evidence": evidence,
        "stop": {
            "sufficient_to_stop": False,
            "required_obligation_identities": required,
            "new_execution_required": list(missing),
            "escalation_reasons": [],
            "boundary": "repository",
        },
    }
    if complete and all(statuses.get(identity, "current") == "current" for identity in required):
        plan["stop"]["sufficient_to_stop"] = True
    if any(statuses.get(identity) in {"escalation_required", "stale", "new_execution_required"} for identity in selected_ids):
        plan["stop"]["new_execution_required"] = [
            identity for identity in selected_ids
            if statuses.get(identity) in {"escalation_required", "stale", "new_execution_required"}
        ] + list(missing)
        plan["stop"]["sufficient_to_stop"] = False
    plan["obligation_plan_id"] = obligation_plan_identity(plan)
    return plan


def test_source_module_inventory_cannot_establish_repository_closure() -> None:
    plan = _repository_plan(scope="source_module")
    with pytest.raises(ObligationPlanError, match="source-module inventory"):
        validate_obligation_plan(plan)


def test_missing_repository_obligation_keeps_repository_plan_insufficient() -> None:
    plan = _repository_plan(complete=False, missing=["fixture.repo.runtime"])
    validated = validate_obligation_plan(plan)
    assert not validated["stop"]["sufficient_to_stop"]
    assert validated["repository"]["missing_obligation_identities"] == ["fixture.repo.runtime"]
    assert "fixture.repo.runtime" in validated["stop"]["new_execution_required"]


def test_repository_fail_preserves_exact_obligation_identity() -> None:
    failing = "fixture.repo.runtime"
    plan = _repository_plan(
        statuses={"fixture.repo.model": "current", failing: "escalation_required"},
        evidence_statuses={"fixture.repo.model": "PASS", failing: "FAIL"},
        evidence_reasons={failing: "mncs-cli integration target failed"},
    )
    validated = validate_obligation_plan(plan)
    selected = next(item for item in validated["obligations"] if item["identity"] == failing)
    assert not validated["stop"]["sufficient_to_stop"]
    assert failing in validated["stop"]["new_execution_required"]
    assert selected["evidence_identities"] == [f"evidence:{failing}"]
    assert next(item for item in validated["evidence"] if item.get("obligation_identity") == failing)["status"] == "FAIL"


def test_repository_timeout_unknown_preserves_reason_and_identity() -> None:
    timed_out = "fixture.repo.runtime"
    reason = "executor timed out after 600s"
    plan = _repository_plan(
        statuses={"fixture.repo.model": "current", timed_out: "escalation_required"},
        evidence_statuses={"fixture.repo.model": "PASS", timed_out: "UNKNOWN"},
        evidence_reasons={timed_out: reason},
    )
    validated = validate_obligation_plan(plan)
    evidence = next(item for item in validated["evidence"] if item.get("obligation_identity") == timed_out)
    assert not validated["stop"]["sufficient_to_stop"]
    assert timed_out in validated["stop"]["new_execution_required"]
    assert evidence["status"] == "UNKNOWN"
    assert evidence["reason"] == reason


@pytest.mark.parametrize("field", ["repository_fingerprint", "invalidation_identity"])
def test_repository_stale_identity_cannot_satisfy_current_status(field: str) -> None:
    identity = "fixture.repo.runtime"
    plan = _repository_plan(fingerprint_override={identity: "z" * 64} if field == "repository_fingerprint" else None)
    if field == "invalidation_identity":
        plan["evidence"][1][field] = "z" * 64
        plan["obligation_plan_id"] = obligation_plan_identity(plan)
    with pytest.raises(ObligationPlanError, match="current identity-bound PASS"):
        validate_obligation_plan(plan)


def test_complete_current_repository_obligations_establish_sufficient_stop() -> None:
    plan = _repository_plan()
    validated = validate_obligation_plan(plan)
    assert validated["repository"]["complete"]
    assert validated["stop"]["sufficient_to_stop"]
