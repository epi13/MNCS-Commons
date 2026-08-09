"""Validate frozen producer compatibility snapshots without executing source content."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mncs_commons.adapters.forge import from_forge_result
from mncs_commons.adapters.language import from_language_identity
from mncs_commons.adapters.mncs import from_mncs_result
from mncs_commons.adapters.mnel import from_mnel_observation
from mncs_commons.compatibility import CompatibilityStatus, contracts
from mncs_commons.validation import validate_record


def _load(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"fixture root is not an object: {path}")
    return value


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

    mnel = _load(root / "compat/mnel/mnel-episode-0.1.json")
    mnel_result = from_mnel_observation(mnel, subject_identity="mnel:compatibility-fixture")
    if mnel_result.record is None or not validate_record(mnel_result.record).valid:
        raise ValueError("MNEL compatibility translation failed")

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

    registry = {item.producer: item for item in contracts()}
    if registry["fabric"].expected_status != CompatibilityStatus.UNKNOWN:
        raise ValueError("Fabric must remain UNKNOWN without a local producer contract")
    print("all compatibility fixtures valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
