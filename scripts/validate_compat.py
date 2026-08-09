"""Validate frozen producer compatibility snapshots without executing source content."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mncs_commons.adapters.fabric import (
    from_fabric_artifact_manifest,
    from_fabric_bundle_binding,
    from_fabric_cohort_result,
    from_fabric_execution,
    from_fabric_job_plan,
    from_fabric_node_capabilities,
)
from mncs_commons.adapters.forge import from_execution_receipt, from_forge_result
from mncs_commons.adapters.language import (
    from_executable_artifact,
    from_language_identity,
    from_verifier_artifact,
)
from mncs_commons.adapters.mncs import (
    from_mncs_execution_bundle,
    from_mncs_execution_placement,
    from_mncs_execution_receipt,
    from_mncs_result,
)
from mncs_commons.adapters.mnel import from_mnel_observation, from_provider_study_record
from mncs_commons.adapters.ravel import from_development_record
from mncs_commons.compatibility import CompatibilityStatus, contracts
from mncs_commons.validation import validate_record


def _load(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"fixture root is not an object: {path}")
    return value


def _assert_translated(result: object, label: str) -> None:
    if not hasattr(result, "record"):
        raise ValueError(f"{label} adapter did not return AdapterResult")
    record = result.record  # type: ignore[attr-defined]
    if record is None or not validate_record(record).valid:
        raise ValueError(f"{label} compatibility translation failed")


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    lock = _load(root / "compat/producer-contracts.json")
    locked_contracts = lock.get("contracts")
    if not isinstance(locked_contracts, list):
        raise ValueError("producer compatibility lock must contain contracts")
    expected_contracts = [item.as_dict() for item in contracts()]
    if locked_contracts != expected_contracts:
        raise ValueError("producer compatibility lock differs from the in-code registry")

    forge = _load(root / "compat/forge/forge-cell-execution-0.1.json")
    forge_result = from_forge_result(
        forge,
        subject_identity="candidate:compatibility-fixture",
        scope_context={"environment": forge["identities"]["environment"]},
    )
    if (
        not forge_result.recognized
        or forge_result.record is None
        or not validate_record(forge_result.record).valid
    ):
        raise ValueError("Forge compatibility translation failed")
    _assert_translated(
        from_execution_receipt(
            _load(root / "compat/forge/mncs-execution-receipt-0.1.json"),
            subject_identity="forge:receipt-fixture",
        ),
        "Forge execution receipt",
    )

    mnel = _load(root / "compat/mnel/mnel-episode-0.1.json")
    mnel_result = from_mnel_observation(mnel, subject_identity="mnel:compatibility-fixture")
    _assert_translated(mnel_result, "MNEL")

    timestamp = "2026-08-08T00:00:00Z"
    for name, adapter, path in (
        ("Fabric execution", from_fabric_execution, "compat/fabric/execution-record-v0.1.json"),
        (
            "Fabric artifact manifest",
            from_fabric_artifact_manifest,
            "compat/fabric/artifact-manifest-v0.1.json",
        ),
        ("Fabric job plan", from_fabric_job_plan, "compat/fabric/job-plan-v0.1.json"),
        (
            "Fabric bundle binding",
            from_fabric_bundle_binding,
            "compat/fabric/execution-bundle-binding-v0.1.json",
        ),
        (
            "Fabric node capabilities",
            from_fabric_node_capabilities,
            "compat/fabric/node-capabilities-v0.1.json",
        ),
        ("Fabric cohort", from_fabric_cohort_result, "compat/fabric/cohort-result-v0.1.json"),
    ):
        _assert_translated(
            adapter(_load(root / path), subject_identity=f"{name}:subject", created_at=timestamp),
            name,
        )

    for name, adapter, path in (
        (
            "MNCS execution receipt",
            from_mncs_execution_receipt,
            "compat/mncs/execution-receipt-0.1.json",
        ),
        (
            "MNCS execution bundle",
            from_mncs_execution_bundle,
            "compat/mncs/execution-bundle-0.1.json",
        ),
        (
            "MNCS execution placement",
            from_mncs_execution_placement,
            "compat/mncs/execution-placement-0.1.json",
        ),
    ):
        _assert_translated(
            adapter(_load(root / path), subject_identity=f"{name}:subject", created_at=timestamp),
            name,
        )

    _assert_translated(
        from_provider_study_record(
            _load(root / "compat/mnel/provider-portfolio-0.4.json"),
            subject_identity="mnel:provider-study",
            created_at=timestamp,
        ),
        "MNEL provider portfolio",
    )
    _assert_translated(
        from_provider_study_record(
            _load(root / "compat/mnel/calibration-0.4.json"),
            subject_identity="mnel:calibration",
            created_at=timestamp,
        ),
        "MNEL calibration",
    )

    language = from_language_identity(
        _load(root / "compat/mncs-language/semantic-identity-boundary.json"),
        subject_identity="mncs-language:compatibility-fixture",
        created_at="2026-08-08T00:00:00Z",
    )
    if language.record is None or not validate_record(language.record).valid:
        raise ValueError("MNCS Language compatibility translation failed")

    ravel = _load(root / "compat/ravel/ravel-0.6-development-record.json")
    if ravel.get("formal_status", {}).get("mncs") != "UNKNOWN":
        raise ValueError("RAVEL fixture must preserve UNKNOWN formal status")
    for name in ("matched-compute-0.6.json", "transaction-0.6.json"):
        _assert_translated(
            from_development_record(
                _load(root / "compat/ravel" / name),
                subject_identity=f"ravel:{name}",
                created_at="2026-08-08T00:00:00Z",
            ),
            f"RAVEL {name}",
        )

    mncs_result = from_mncs_result(
        {
            "schema_version": "0.2",
            "mncs_version": "0.2",
            "result_id": "sha256:compatibility-result",
            "contract_id": "contract:synthetic-compatibility",
            "status": "UNKNOWN",
            "evidence_references": [],
            "completed_at": "2026-08-08T00:00:00Z",
        },
        subject_identity="mncs:compatibility-fixture",
    )
    if mncs_result.record is None or not validate_record(mncs_result.record).valid:
        raise ValueError("MNCS compatibility translation failed")

    _assert_translated(
        from_executable_artifact(
            _load(root / "compat/mncs-language/executable-body-0.2.json"),
            subject_identity="language:body",
            created_at="2026-08-08T00:00:00Z",
        ),
        "MNCS Language executable body",
    )
    _assert_translated(
        from_verifier_artifact(
            _load(root / "compat/mncs-language/verifier-result-0.2.json"),
            subject_identity="language:verifier",
            created_at="2026-08-08T00:00:00Z",
        ),
        "MNCS Language verifier artifact",
    )

    registry = {item.contract_id: item for item in contracts()}
    if registry["fabric:execution-record:0.1"].expected_status != CompatibilityStatus.COMPATIBLE:
        raise ValueError("Fabric execution contract must be frozen against the current schema")
    print("all compatibility fixtures valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
