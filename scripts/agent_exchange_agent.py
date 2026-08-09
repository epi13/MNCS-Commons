"""Tiny vendor-neutral participant used by the deterministic exchange scenario."""

from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mncs_commons.application import CommonsApplication
from mncs_commons.exchange import ParticipantDescriptor
from mncs_commons.store import CommonsStore


def _load(name: str) -> dict[str, object]:
    root = Path(__file__).resolve().parents[1]
    return json.loads((root / "examples" / name).read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--store", required=True)
    parser.add_argument("--role", choices=("request", "failed-replication"), required=True)
    parser.add_argument("--agent-id", required=True)
    args = parser.parse_args(argv)
    application = CommonsApplication(CommonsStore(args.store))
    participant = ParticipantDescriptor(args.agent_id, "commons-interop-agent", "0.1")
    if args.role == "request":
        value = _load("work-request.json")
    else:
        requests = [
            item for item in application.list_records() if item.get("kind") == "WorkRequest"
        ]
        if not requests:
            raise RuntimeError("no WorkRequest was available to the responding agent")
        request_id = str(requests[0].get("metadata", {}).get("recordId"))
        value = deepcopy(_load("failed-replication.json"))
        value["metadata"]["recordId"] = f"commons:replication:{args.agent_id}"
        value["metadata"]["author"] = {"type": "agent", "id": args.agent_id}
        value["relationships"] = [
            {"type": "responds_to", "target": request_id},
            {"type": "failed_to_replicate", "target": "commons:observation:compiler-pattern-0001"},
        ]
    print(json.dumps(application.publish(value, participant=participant), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
