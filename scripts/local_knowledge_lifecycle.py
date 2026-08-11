"""Build a bounded, synthetic local knowledge lifecycle using real Commons records."""

from __future__ import annotations

import json
import tempfile
from copy import deepcopy
from pathlib import Path

from mncs_commons.application import CommonsApplication
from mncs_commons.io import load_document
from mncs_commons.store import CommonsStore

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str) -> dict[str, object]:
    value = load_document(ROOT / "examples" / name)
    if not isinstance(value, dict):
        raise RuntimeError(f"example {name} is not an object")
    return value


def _event(
    target: str, source: str, destination: str, domain: str, author: str
) -> dict[str, object]:
    return {
        "apiVersion": "commons.mncs.dev/v0alpha1",
        "kind": "LifecycleEvent",
        "metadata": {
            "createdAt": "2026-08-10T01:00:00Z",
            "author": {"type": "local-reviewer", "id": author},
        },
        "target": {"contentDigest": target},
        "transition": {"from": source, "to": destination},
        "authority": {
            "domain": domain,
            "actor": author,
            "rationale": "bounded local projection over explicit evidence",
        },
        "evidence": [{"id": "commons:verifier:local", "relation": "supports", "status": "PASS"}],
    }


def run() -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="commons-lifecycle-") as temporary:
        store = CommonsStore(Path(temporary) / "store")
        store.init()
        application = CommonsApplication(store)

        observation = _load("observation.example.yaml")
        work = _load("work-request.json")
        failed = _load("failed-replication.json")
        observation["metadata"] = {
            **observation["metadata"],
            "recordId": "commons:observation:lifecycle",
        }
        work["metadata"] = {**work["metadata"], "recordId": "commons:work:lifecycle"}

        passing = deepcopy(failed)
        passing["metadata"] = {
            **passing["metadata"],
            "recordId": "commons:replication:pass",
            "author": {"type": "verifier", "id": "verifier:clang-x86"},
        }
        passing["statement"] = {
            "summary": "The observation replicated under the original narrow toolchain scope."
        }
        passing["evidence"] = [
            {"id": "forge:verifier-result:clang-x86", "relation": "supports", "status": "PASS"}
        ]
        passing["relationships"] = [
            {"type": "replicates", "target": "commons:observation:lifecycle"}
        ]
        passing["details"] = {**passing["details"], "outcome": "PASS"}

        failed["metadata"] = {
            **failed["metadata"],
            "recordId": "commons:replication:fail",
        }
        failed["relationships"] = [
            {"type": "failed_to_replicate", "target": "commons:observation:lifecycle"}
        ]
        failed["details"] = {**failed["details"], "targetRecord": "commons:observation:lifecycle"}

        claim = deepcopy(observation)
        claim["kind"] = "Claim"
        claim["metadata"] = {
            **claim["metadata"],
            "recordId": "commons:claim:narrowed",
            "author": {"type": "local-reviewer", "id": "reviewer:controller"},
        }
        claim["statement"] = {
            "summary": "The observation is supported only for the original clang x86_64 scope.",
            "details": (
                "The GCC aarch64 failure narrows the claim; it does not establish "
                "a global negative."
            ),
        }
        claim["evidence"] = [
            {"id": "commons:replication:pass", "relation": "supports", "status": "PASS"},
            {"id": "commons:replication:fail", "relation": "narrows", "status": "FAIL"},
            {"id": "commons:verifier:local", "relation": "verifies", "status": "PASS"},
        ]
        claim["relationships"] = [
            {"type": "narrows", "target": "commons:observation:lifecycle"},
            {"type": "supports", "target": "commons:replication:pass"},
        ]
        claim["details"] = {
            "outcome": "UNKNOWN",
            "falsifier": "a bounded counterexample within the declared scope",
        }

        verifier = deepcopy(observation)
        verifier["metadata"] = {
            **verifier["metadata"],
            "recordId": "commons:verifier:local",
            "author": {"type": "verifier", "id": "verifier:local"},
        }
        verifier["subject"] = {"type": "verifier-result", "identity": "verifier:local"}
        verifier["statement"] = {"summary": "A local verifier checked the narrowed claim envelope."}
        verifier["evidence"] = [
            {"id": "forge:verifier-result:local", "relation": "supports", "status": "PASS"}
        ]
        verifier["relationships"] = [{"type": "verifies", "target": "commons:claim:narrowed"}]
        verifier["details"] = {"outcome": "PASS", "verificationScope": "local claim envelope only"}

        records = [observation, work, passing, failed, claim, verifier]
        added = [application.add(record) for record in records]
        claim_digest = added[4].digest
        transitions = (
            ("proposed", "reproduced"),
            ("reproduced", "verified"),
            ("verified", "accepted"),
        )
        for source, destination in transitions:
            store.add_event(
                _event(
                    claim_digest,
                    source,
                    destination,
                    "controller:local",
                    "reviewer:controller",
                )
            )
        store.add_event(
            _event(
                claim_digest,
                "proposed",
                "disputed",
                "peer:independent",
                "reviewer:peer",
            )
        )

        return {
            "status": "PASS",
            "records": len(store.records()),
            "events": len(store.events()),
            "claimDigest": claim_digest,
            "controllerState": application.lifecycle(claim_digest, "controller:local")["state"],
            "peerState": application.lifecycle(claim_digest, "peer:independent")["state"],
            "conversationRecords": len(application.conversation(claim_digest)["records"]),
            "authorityBoundary": "local projections and evidence organization; no global truth",
        }


if __name__ == "__main__":
    print(json.dumps(run(), sort_keys=True))
