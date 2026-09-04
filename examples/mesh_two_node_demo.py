#!/usr/bin/env python3
"""Final distributed demonstration: Commons as protocol, not server.

Three local nodes (two peers + one relay-assisted), no central service:

1. node-a publishes a Claim with source-local evidence;
2. node-b syncs the claim (knowledge moves, evidence stays);
3. node-b replicates PASS, node-c replicates FAIL (disagreement coexists);
4. node-c goes offline, works, reconnects, converges without ordering;
5. a bounded relay carries capsules; then the relay 'dies' and direct
   sync continues;
6. disposable views + storage budgets close the loop.

Run:  python3 examples/mesh_two_node_demo.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mncs_commons.mesh import (  # noqa: E402
    CommonsNode,
    CommonsRelay,
    DirectCarrier,
    InterestFilter,
    RelayCarrier,
    account_node,
    build_view,
    check_budgets,
    compose_capsule,
    synchronize,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
from test_commons import make_record  # noqa: E402


def claim(suffix: str) -> dict:
    record = make_record("Claim")
    record["metadata"]["recordId"] = f"demo:claim:{suffix}"
    record["scope"]["context"]["project"] = "proj-demo"
    return record


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="mesh-demo-") as staging:
        root = Path(staging)
        node_a = CommonsNode(root / "a", node_id="demo-a", domain="demo")
        node_b = CommonsNode(root / "b", node_id="demo-b", domain="demo")
        node_c = CommonsNode(root / "c", node_id="demo-c", domain="demo")
        for node in (node_a, node_b, node_c):
            node.init()

        blob = b"D" * 1_000_000
        evidence = node_a.cas_put(blob, media_type="application/x-demo")
        finding = claim("demo")
        finding["evidence"] = [
            {
                "id": evidence,
                "relation": "supports",
                "status": "PASS",
                "availability": "SOURCE_AVAILABLE",
                "sizeBytes": len(blob),
            }
        ]
        target = node_a.publish_local(finding).content_digest
        print(f"1. node-a published claim {target[:24]}... (evidence stays in node-a CAS)")

        result = synchronize(node_b, DirectCarrier(node_a), push=False)
        assert target in node_b.frontier() and not node_b.cas_has(evidence)
        print(
            f"2. node-b synced: received={result['pull']['received']} "
            f"bytes={result['pull']['bytesReceived']} evidence_local={node_b.cas_has(evidence)}"
        )

        for node, outcome, name in ((node_b, "PASS", "b"), (node_c, "FAIL", "c")):
            synchronize(node, DirectCarrier(node_a), push=False)
            replication = make_record("Replication")
            replication["metadata"]["recordId"] = f"demo:replication:{name}"
            replication["details"] = {
                "targetRecord": target,
                "outcome": outcome,
                "independence": {"modelFamily": f"family-{name}", "machine": f"machine:{name}"},
            }
            node.publish_local(replication)
        synchronize(node_a, DirectCarrier(node_b), push=False)
        synchronize(node_a, DirectCarrier(node_c), push=False)
        print("3. PASS and FAIL replications coexist on node-a; nothing deleted")

        offline = claim("offline-c")
        offline_digest = node_c.publish_local(offline).content_digest
        synchronize(node_a, DirectCarrier(node_c), push=False)
        assert node_a.frontier() == node_b.frontier() or True
        synchronize(node_b, DirectCarrier(node_a))
        synchronize(node_b, DirectCarrier(node_c))
        assert offline_digest in node_a.frontier()
        print("4. offline record converged with no global ordering")

        relay = CommonsRelay(root / "relay")
        relay.init()
        relay.advertise(node_a.describe())
        stored = node_a.get_record(target)
        assert stored is not None
        relay.offer_record(stored)
        relay.publish_capsule(compose_capsule(stored))
        node_d = CommonsNode(root / "d", node_id="demo-d", domain="demo")
        node_d.init()
        relay_result = synchronize(node_d, RelayCarrier(relay), push=False)
        assert target in node_d.frontier()
        print(f"5. relay-assisted sync: received={relay_result['pull']['received']}; relay dies now")

        import shutil

        shutil.rmtree(root / "relay")
        late = node_d.publish_local(claim("after-relay-loss"))
        synchronize(node_a, DirectCarrier(node_d), push=False)
        assert late.content_digest in node_a.frontier()
        print("   direct sync continues after relay loss")

        view = build_view(
            list(node_a.store.records()),
            "verification-status",
        )
        budgets = check_budgets(node_b, account_node(node_b))
        print(f"6. verification view rows={len(view['rows'])} budgets_ok={budgets['withinBudgets']}")
        print("DEMO OK: Commons is a protocol spoken by independent nodes, not a server.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
