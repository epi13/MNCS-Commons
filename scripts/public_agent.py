"""Tiny vendor-neutral process used by the public-node interoperability check."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

from mncs_commons.bootstrap import _request
from mncs_commons.remote import RemoteClient


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("role", choices=("publish-work", "respond-fail", "sync"))
    parser.add_argument("--cursor")
    args = parser.parse_args()
    client = RemoteClient(args.url, allow_http=True)
    if args.role == "publish-work":
        result = client.publish(
            _request(
                "interop-work-request",
                "Run the independent two-process Commons HTTP interoperability check.",
                "public",
            ),
            {"participantId": "urn:commons:test:agent-a", "implementation": "agent-a"},
        )
    elif args.role == "respond-fail":
        path = Path(__file__).resolve().parents[1] / "examples" / "failed-replication.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        record = copy.deepcopy(record)
        record["metadata"]["recordId"] = "interop-failed-replication"
        record["subject"]["identity"] = "interop-work-request"
        record["relationships"][0]["target"] = "interop-work-request"
        record["details"]["targetRecord"] = "interop-work-request"
        result = client.publish(
            record,
            {"participantId": "urn:commons:test:agent-b", "implementation": "agent-b"},
        )
    else:
        cursor = json.loads(args.cursor) if args.cursor else None
        result = client.sync(cursor)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
