"""Run a bounded two-process Agent Exchange interoperability scenario."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mncs_commons.application import CommonsApplication
from mncs_commons.exchange import ExchangeError
from mncs_commons.store import CommonsStore


def _run_agent(script: Path, store: Path, role: str, agent_id: str) -> dict[str, object]:
    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--store",
            str(store),
            "--role",
            role,
            "--agent-id",
            agent_id,
        ],
        cwd=script.parents[1],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        shell=False,
        timeout=30,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace")[:4096]
        raise RuntimeError(f"agent process failed: {detail}")
    value = json.loads(completed.stdout.decode("utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError("agent receipt was not an object")
    return value


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "agent_exchange_agent.py"
    with tempfile.TemporaryDirectory(prefix="commons-agent-exchange-") as temporary:
        store_path = Path(temporary) / "store"
        store = CommonsStore(store_path)
        store.init()
        first = _run_agent(script, store_path, "request", "urn:example:agent-a")
        if first.get("deliveryStatus") != "INGESTED":
            raise RuntimeError("requesting agent was not ingested")
        second = _run_agent(script, store_path, "failed-replication", "urn:example:agent-b")
        third = _run_agent(script, store_path, "failed-replication", "urn:example:agent-c")
        if {second.get("deliveryStatus"), third.get("deliveryStatus")} != {"INGESTED"}:
            raise RuntimeError("independent responses were not both ingested")
        application = CommonsApplication(store)
        sync = application.sync(limit=10)
        entries = sync.get("entries", [])
        if not isinstance(entries, list) or len(entries) != 3:
            raise RuntimeError("sync did not return all three contributions")
        request_digest = str(first["contentDigest"])
        conversation = application.conversation(request_digest, max_nodes=10)
        if len(conversation.get("records", [])) != 3:
            raise RuntimeError("conversation graph did not retain both responses")
        if not any(
            item.get("type") == "failed_to_replicate"
            for item in conversation.get("edges", [])
            if isinstance(item, dict)
        ):
            raise RuntimeError("negative replication edge was lost")
        if store.events():
            raise RuntimeError("publication implicitly created lifecycle acceptance")
        try:
            application.sync({**dict(sync["nextCursor"]), "entryDigest": "sha256:" + "0" * 64})
        except ExchangeError as error:
            if error.code != "STALE_CURSOR":
                raise
        else:
            raise RuntimeError("stale cursor was not rejected")
    print(json.dumps({"status": "PASS", "agents": 3, "negativeEvidence": True}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
