"""Full membership law: kernel owns it, Python projects onto it.

The normative law is ``candidate_matches_full`` in
``src/mncs_commons/mesh/mncs/commons/mesh/interest.mncs``; the checked-in
``commons-interest-full-corpus.json`` pins its truth table (kind matrix,
per-conjunct kills, seeded fuzz). These always-on tests bind the Python
mirror (``mirror_matches_full``, which backs ``matches``) to the same
contract. Backend execution of the same corpus is covered by
``test_mesh_interop.py``.
"""

from __future__ import annotations

import json
from pathlib import Path

from mncs_commons.mesh.interest import (
    InterestFilter,
    matches,
    mirror_matches_full,
)

CORPUS = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "mncs_commons"
    / "mesh"
    / "mncs"
    / "corpora"
    / "commons-interest-full-corpus.json"
)


def _boolean(argument: dict) -> bool:
    return bool(argument["boolean"]["value"])


def _integer(argument: dict) -> int:
    return int(argument["integer"]["value"])


def _flat(args: list) -> tuple:
    return (
        _integer(args[0]),
        tuple(_boolean(item) for item in args[1:7]),
        _boolean(args[7]),
        *[_boolean(item) for item in args[8:22]],
        _boolean(args[22]),
        _boolean(args[23]),
        _boolean(args[24]),
        _boolean(args[25]),
        _boolean(args[26]),
    )


def test_python_mirror_agrees_with_full_interest_corpus():
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    assert len(corpus["cases"]) == 92
    for case in corpus["cases"]:
        request = case["request"]
        assert request["target"]["function"] == "candidate_matches_full"
        assert len(request["arguments"]) == 27, case["id"]
        decided = mirror_matches_full(*_flat(request["arguments"]))
        assert _boolean(case["expected"][0]) == decided, case["id"]


def test_unknown_kinds_stay_inert_by_design():
    """Closed-world tightening: filters naming unknown kinds match nothing.

    The pre-kernel string-exact path exact-matched unknown record kinds
    against unknown filter names. The kernel law keeps unknown vocabulary
    inert instead: code 6 never satisfies a restricted kind dimension.
    """

    record = {"kind": "LifecycleEvent", "contentDigest": "sha256:" + "b" * 64}
    assert matches(record, InterestFilter.from_mapping({"kinds": ["LifecycleEvent"]})) is False
    assert matches(record, InterestFilter.from_mapping({"kinds": ["Finding"]})) is False
    # An unrestricted filter still matches everything: inert applies to
    # restricted dimensions, never to the empty subscription.
    assert matches(record, InterestFilter.from_mapping({})) is True
    # Known kinds keep exact behavior on both paths.
    finding = {"kind": "Finding", "contentDigest": "sha256:" + "c" * 64}
    assert matches(finding, InterestFilter.from_mapping({"kinds": ["Finding"]})) is True
    assert matches(finding, InterestFilter.from_mapping({"kinds": ["Claim"]})) is False
    assert matches(finding, InterestFilter.from_mapping({})) is True
