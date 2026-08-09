"""Read-only compatibility report for sibling checkouts present beside Commons."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    from mncs_commons.compatibility import CompatibilityStatus, compatibility_report

    root = ROOT
    sibling_names = {
        "forge": "mncs-forge-mcp",
        "fabric": "mncs-fabric",
        "mnel": "Machine-Native-Experimental-Learning",
        "ravel": "RAVEL",
        "mncs-language": "mncs-language",
        "mncs": "machine-native-complexity-standard",
        "mncs-validator-rs": "mncs-validator-rs",
    }
    repositories = {
        producer: root.parent / name
        for producer, name in sibling_names.items()
        if (root.parent / name).exists()
    }
    assessments = compatibility_report(repositories)
    statuses = [item.status for item in assessments]
    limitations = [
        "absent sibling repositories remain UNKNOWN",
        "source fingerprints establish locked bytes, not semantic equivalence",
    ]
    fabric = next((item for item in assessments if item.contract.producer == "fabric"), None)
    if fabric is not None and fabric.status == CompatibilityStatus.UNKNOWN:
        limitations.append(
            "the local Fabric checkout has no frozen source-schema fingerprint in the registry"
        )
    status = (
        "FAIL"
        if CompatibilityStatus.DRIFTED in statuses
        else "UNKNOWN"
        if any(
            item
            in {
                CompatibilityStatus.UNKNOWN,
                CompatibilityStatus.UNSUPPORTED_VERSION,
                CompatibilityStatus.COMPATIBLE_WITH_UNRESOLVED_FIELDS,
            }
            for item in statuses
        )
        else "PASS"
    )
    print(
        json.dumps(
            {
                "status": status,
                "availableProducers": sorted(repositories),
                "assessments": [item.as_dict() for item in assessments],
                "limitations": limitations,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
