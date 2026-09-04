"""Mesh scenario J: mixed-implementation interoperability + legacy compat.

Three independent agreements keep implementations honest:

1. Python mirror <-> checked-in corpora (always on): the Python reference
   projections evaluate every corpus case and must equal the checked-in
   expectations -- the same expectations the MNCS backends execute.
2. MNCS backends <-> corpora (toolchain-gated): ``mncs experiment run``
   over research-bytecode and portable-wasm must PASS every corpus.
3. Canonical stability (always on): the golden capsule fixture keeps one
   fixed digest; any protocol-digest migration must be explicit.
4. Legacy path (always on): a record published through the pre-mesh
   ``CommonsApplication`` carries the identical digest into a mesh node.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from mncs_commons.application import CommonsApplication
from mncs_commons.canonical import canonical_digest
from mncs_commons.mesh import (
    RETENTION_PRIORITY,
    CommonsNode,
    DirectCarrier,
    EvidenceAvailability,
    matches_discriminants,
    merge_availability,
    synchronize,
)
from tests.test_commons import make_record

MESH_DIR = Path(__file__).resolve().parent.parent / "src" / "mncs_commons" / "mesh"
MNCS_DIR = MESH_DIR / "mncs"
CORPORA = MNCS_DIR / "corpora"

GOLDEN_CAPSULE_DIGEST = "sha256:e13acb3ec2b61c5e79199376745bf63d23885a4d12beee2681ecc7b62b71213c"

AVAILABILITY_ORDER = [
    "Unavailable",
    "SourceAvailable",
    "Local",
    "Mirrored",
    "Durable",
    "Canonical",
]
AVAILABILITY_BY_RANK = {
    0: EvidenceAvailability.UNAVAILABLE,
    1: EvidenceAvailability.SOURCE_AVAILABLE,
    2: EvidenceAvailability.LOCAL,
    3: EvidenceAvailability.MIRRORED,
    4: EvidenceAvailability.DURABLE,
    5: EvidenceAvailability.CANONICAL,
}
COMBINE_TABLE = [
    [0, 1, 2],
    [1, 1, 1],
    [2, 1, 2],
]


def _load_corpus(name: str) -> dict:
    return json.loads((CORPORA / name).read_text(encoding="utf-8"))


def _finite_arg(argument: dict) -> tuple[str, str, int]:
    finite = argument["finite"]
    return (
        finite["type_identity"].rsplit("::", 1)[-1],
        finite["variant_identity"].rsplit("::", 1)[-1],
        int(finite["discriminant"]),
    )


def _integer(argument: dict) -> int:
    return int(argument["integer"]["value"])


def _boolean(argument: dict) -> bool:
    return bool(argument["boolean"]["value"])


def test_python_mirror_agrees_with_availability_corpus():
    corpus = _load_corpus("commons-availability-corpus.json")
    assert len(corpus["cases"]) == 78
    for case in corpus["cases"]:
        request = case["request"]
        function = request["target"]["function"]
        expected = case["expected"][0]
        if function == "candidate_rank":
            _, _, discriminant = _finite_arg(request["arguments"][0])
            assert _integer(expected) == discriminant, case["id"]
        elif function == "candidate_merge_rank":
            _, _, first = _finite_arg(request["arguments"][0])
            _, _, second = _finite_arg(request["arguments"][1])
            merged = merge_availability(AVAILABILITY_BY_RANK[first], AVAILABILITY_BY_RANK[second])
            assert _integer(expected) == RETENTION_PRIORITY[merged], case["id"]
        elif function == "candidate_should_fetch":
            _, _, first = _finite_arg(request["arguments"][0])
            _, _, second = _finite_arg(request["arguments"][1])
            assert _boolean(expected) == (second > first), case["id"]
        else:
            raise AssertionError(f"unknown function {function}")


def test_python_mirror_agrees_with_outcome_corpus():
    corpus = _load_corpus("commons-outcome-corpus.json")
    assert len(corpus["cases"]) == 21
    for case in corpus["cases"]:
        request = case["request"]
        function = request["target"]["function"]
        expected = case["expected"][0]
        if function == "candidate_combine":
            _, _, first = _finite_arg(request["arguments"][0])
            _, _, second = _finite_arg(request["arguments"][1])
            _, variant, discriminant = _finite_arg(expected)
            assert discriminant == COMBINE_TABLE[first][second], case["id"]
        elif function == "candidate_agrees":
            _, _, first = _finite_arg(request["arguments"][0])
            _, _, second = _finite_arg(request["arguments"][1])
            assert _boolean(expected) == (first == second), case["id"]
        elif function == "candidate_is_settled":
            _, _, discriminant = _finite_arg(request["arguments"][0])
            assert _boolean(expected) == (discriminant in (0, 1)), case["id"]
        else:
            raise AssertionError(f"unknown function {function}")


def test_python_mirror_agrees_with_interest_corpus():
    corpus = _load_corpus("commons-interest-corpus.json")
    assert len(corpus["cases"]) == 135
    for case in corpus["cases"]:
        request = case["request"]
        assert request["target"]["function"] == "candidate_matches"
        args = request["arguments"]
        assert len(args) == 13, case["id"]
        kind, outcome, state = (_integer(args[0]), _integer(args[1]), _integer(args[2]))
        flags = [_boolean(item) for item in args[3:12]]
        min_rank = _integer(args[12])
        decided = matches_discriminants(
            kind,
            outcome,
            state,
            want_kinds=(flags[0], flags[1], flags[2], flags[3], flags[4], flags[5]),
            want_outcomes=(flags[6], flags[7], flags[8]),
            min_rank=min_rank,
        )
        assert _boolean(case["expected"][0]) == decided, case["id"]


def test_lattice_corpus_encodes_agreement():
    corpus = _load_corpus("commons-lattice-corpus.json")
    assert len(corpus["cases"]) == 9
    for case in corpus["cases"]:
        assert case["expected"] == [{"boolean": {"value": True}}], case["id"]


def test_golden_capsule_digest_is_stable():
    capsule = json.loads(
        (Path(__file__).parent / "fixtures" / "mesh_capsule_golden.json").read_text(
            encoding="utf-8"
        )
    )
    assert canonical_digest(capsule, projected=False) == GOLDEN_CAPSULE_DIGEST
    # Same semantic record never acquires a different digest across calls.
    assert canonical_digest(capsule, projected=False) == GOLDEN_CAPSULE_DIGEST


def test_legacy_application_record_enters_mesh_unchanged(tmp_path):
    """A pre-mesh producer record keeps its digest inside a mesh node."""

    application = CommonsApplication()
    record = make_record("Finding")
    record["metadata"]["recordId"] = "test:legacy:interop"
    assert application.validate(record)["valid"] is True
    node = CommonsNode(tmp_path / "node", node_id="node-j", domain="project-a")
    node.init()
    receipt = node.publish_local(record)
    assert receipt.content_digest == canonical_digest(record)
    assert receipt.content_digest in node.frontier()

    peer = CommonsNode(tmp_path / "peer", node_id="peer-j", domain="project-a")
    peer.init()
    synchronize(peer, DirectCarrier(node), push=False)
    assert receipt.content_digest in peer.frontier()
    assert peer.get_record(receipt.content_digest)["kind"] == "Finding"


def _toolchain() -> Path | None:
    override = os.environ.get("MNCS_LANGUAGE_CHECKOUT")
    candidates = [Path(override)] if override else []
    candidates.append(Path(__file__).resolve().parent.parent.parent / "mncs-language")
    for candidate in candidates:
        binary = candidate / "target" / "debug" / "mncs"
        if binary.exists():
            return candidate
    return None


needs_toolchain = pytest.mark.skipif(
    _toolchain() is None, reason="mncs-language checkout with a built mncs binary is absent"
)

KERNEL_CASES = {
    "commons/mesh/availability.mncs": "commons-availability-corpus.json",
    "commons/mesh/outcome.mncs": "commons-outcome-corpus.json",
    "commons/mesh/interest.mncs": "commons-interest-corpus.json",
    "commons/mesh/lattice_check.mncs": "commons-lattice-corpus.json",
}


@needs_toolchain
@pytest.mark.parametrize("backend", ["mncs-research-bytecode", "portable-wasm"])
@pytest.mark.parametrize("kernel", sorted(KERNEL_CASES))
def test_mncs_backends_execute_mesh_corpora(tmp_path, kernel, backend):
    checkout = _toolchain()
    assert checkout is not None
    binary = checkout / "target" / "debug" / "mncs"
    corpus = CORPORA / KERNEL_CASES[kernel]
    source = MNCS_DIR / kernel
    environment = dict(os.environ)
    library = str(checkout / "library")
    environment["MNCS_LIBRARY_PATH"] = library + ":" + str(MNCS_DIR)
    completed = subprocess.run(
        [
            str(binary),
            "experiment",
            "run",
            str(source),
            "--backend",
            backend,
            "--corpus",
            str(corpus),
            "--output-dir",
            str(tmp_path / "result"),
            "--node-id",
            "commons-interop",
        ],
        capture_output=True,
        text=True,
        env=environment,
        timeout=240,
    )
    assert completed.returncode == 0, completed.stderr[-2000:]
    result = json.loads(completed.stdout)
    assert result["status"] == "PASS", json.dumps(result)[:2000]


@needs_toolchain
@pytest.mark.parametrize("kernel", sorted(KERNEL_CASES))
def test_mncs_source_studies_complete(kernel):
    checkout = _toolchain()
    assert checkout is not None
    binary = checkout / "target" / "debug" / "mncs"
    environment = dict(os.environ)
    environment["MNCS_LIBRARY_PATH"] = str(checkout / "library") + ":" + str(MNCS_DIR)
    completed = subprocess.run(
        [str(binary), "source-study", str(MNCS_DIR / kernel), "--node-id", "commons-interop"],
        capture_output=True,
        text=True,
        env=environment,
        timeout=120,
    )
    assert completed.returncode == 0, completed.stderr[-2000:]
    result = json.loads(completed.stdout)
    assert result["compilation_status"] in ("completed", "completed_with_unresolved_obligations")
