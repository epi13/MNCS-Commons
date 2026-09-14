from __future__ import annotations

import json
from pathlib import Path

from mncs_commons.family_graph import consumers_for, load_graph


GRAPH = Path(__file__).resolve().parents[1] / "family" / "semantic-edges-v1.json"


def test_checked_in_graph_has_digest_bound_edges_and_selective_consumers() -> None:
    graph = load_graph(GRAPH)
    consumers = consumers_for(
        graph,
        producer_repository="ravel",
        contract_identity="mncs.verification-plan/1",
    )
    assert [edge["consumer_repository"] for edge in consumers] == [
        "mncs-actions",
        "mncs-forge-mcp",
        "mncs-test",
    ]
    assert all(edge["fingerprint"] for edge in consumers)
    assert graph["graph_identity"]


def test_graph_mutation_is_rejected(tmp_path: Path) -> None:
    value = json.loads(GRAPH.read_text(encoding="utf-8"))
    value["edges"][0]["consumer_repository"] = "mncs-debug"
    path = tmp_path / "graph.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    import pytest

    with pytest.raises(ValueError):
        load_graph(path)
