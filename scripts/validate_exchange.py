"""Validate language-independent Agent Exchange golden vectors."""

from __future__ import annotations

import json
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    directory = root / "compat" / "exchange-v0alpha1"
    required = (
        "descriptor.json",
        "participant.json",
        "receipt.json",
        "sync-result.json",
        "conversation.json",
    )
    values = {
        name: json.loads((directory / name).read_text(encoding="utf-8")) for name in required
    }
    descriptor = values["descriptor.json"]
    if descriptor["exchangeVersion"] != "commons.mncs.dev/exchange/v0alpha1":
        raise ValueError("descriptor exchange version mismatch")
    if descriptor["recordVersions"] != ["commons.mncs.dev/v0alpha1"]:
        raise ValueError("record version mismatch")
    if values["participant.json"]["identityAssurance"] != "SELF_ASSERTED":
        raise ValueError("participant identity must remain self-asserted")
    receipt = values["receipt.json"]
    if (
        receipt["acceptanceStatus"] != "UNCHANGED"
        or receipt["technicalAuthority"] != "NONE_GRANTED"
    ):
        raise ValueError("receipt authority boundary changed")
    for name in ("sync-result.json", "conversation.json"):
        if values[name]["exchangeVersion"] != descriptor["exchangeVersion"]:
            raise ValueError(f"{name} version mismatch")
    print(json.dumps({"status": "PASS", "vectors": len(required)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
