"""Validate frozen producer compatibility snapshots without executing source content."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mncs_commons.adapters.forge import from_forge_result
from mncs_commons.adapters.language import from_language_identity
from mncs_commons.adapters.mnel import from_mnel_observation
from mncs_commons.validation import validate_record


def _load(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"fixture root is not an object: {path}")
    return value


def main() -> int:
    root = Path(__file__).resolve().parents[1]
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
    payload = mnel["payload"]
    if not isinstance(payload, dict):
        raise ValueError("MNEL fixture payload is not an object")
    mnel_result = from_mnel_observation(
        {
            "observation_identity": payload["observation_id"],
            "provider_id": payload["provider_identity"],
            "provider_version": "compatibility-fixture",
        },
        subject_identity=payload["experiment_id"],
        created_at=mnel["timestamp"],
    )
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
    print("all compatibility fixtures valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
