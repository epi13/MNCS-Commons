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
import re
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


def _byte_view_name(argument: dict) -> str:
    values = [entry["byte"]["value"] for entry in argument["sequence"]["values"]]
    return bytes(values).split(b"\x00")[0].decode("ascii")


def test_python_mirror_agrees_with_named_interest_corpus():
    from mncs_commons.mesh.interest import (
        KIND_DISCRIMINANTS,
        LIFECYCLE_DISCRIMINANTS,
        OUTCOME_DISCRIMINANTS,
    )

    corpus = _load_corpus("commons-interest-named-corpus.json")
    assert len(corpus["cases"]) == 108
    for case in corpus["cases"]:
        request = case["request"]
        assert request["target"]["function"] == "candidate_matches_named"
        args = request["arguments"]
        assert len(args) == 16, case["id"]
        kind = _byte_view_name(args[0])
        outcome = _byte_view_name(args[2])
        state = _byte_view_name(args[4])
        flags = [_boolean(item) for item in args[6:15]]
        min_rank = _integer(args[15])
        decided = matches_discriminants(
            KIND_DISCRIMINANTS.get(kind, 6),
            OUTCOME_DISCRIMINANTS.get(outcome, 9),
            LIFECYCLE_DISCRIMINANTS.get(state, 5),
            want_kinds=(flags[0], flags[1], flags[2], flags[3], flags[4], flags[5]),
            want_outcomes=(flags[6], flags[7], flags[8]),
            min_rank=min_rank,
        )
        assert _boolean(case["expected"][0]) == decided, case["id"]


def test_mixed_evidence_projects_strongest_outcome():
    from mncs_commons.mesh import InterestFilter, matches

    record = make_record("Observation")
    record["details"] = {"outcome": "FAIL", "measurements": {}}
    record["evidence"] = [
        {"id": "a", "status": "FAIL"},
        {"id": "b", "status": "PASS"},
    ]
    # Strongest asserted outcome (PASS) decides on both paths; a FAIL-only
    # subscription does not match a record that also asserts PASS.
    assert matches(record, InterestFilter.from_mapping({"outcomes": ["PASS"]})) is True
    assert matches(record, InterestFilter.from_mapping({"outcomes": ["FAIL"]})) is False
    assert matches(record, InterestFilter.from_mapping({"outcomes": ["PASS", "FAIL"]})) is True


TABLE_ROW = re.compile(
    r"textmap\.Coded16 \{ key: \[([0-9 as byte,]+)\], key_length: (\d+), code: (-?\d+) \}"
)
TABLE_SECTION = re.compile(r"// TABLE (\w+)")
TABLE_FALLBACK = re.compile(r"lookup16<\d+>\(table, \w+, \w+_length, (-?\d+)\)")


def _parse_mncs_tables() -> tuple[dict[str, list[tuple[str, int, int]]], dict[str, int]]:
    """Parse normative TABLE blocks into rows plus per-table fallbacks."""
    source = (MNCS_DIR / "commons" / "mesh" / "interest_named.mncs").read_text(
        encoding="utf-8"
    )
    tables: dict[str, list[tuple[str, int, int]]] = {}
    fallbacks: dict[str, int] = {}
    current: str | None = None
    for line in source.splitlines():
        section = TABLE_SECTION.match(line.strip())
        if section:
            current = section.group(1)
            tables[current] = []
            continue
        if current is None:
            continue
        row = TABLE_ROW.search(line)
        if row:
            raw_bytes = [
                int(piece.strip().removesuffix("as byte")) for piece in row.group(1).split(",")
            ]
            length = int(row.group(2))
            code = int(row.group(3))
            name = bytes(raw_bytes[:length]).decode("ascii")
            assert raw_bytes[length:] == [0] * (16 - length), f"padding drift in {name}"
            assert length == len(name), f"length drift in {name}"
            tables[current].append((name, length, code))
        fallback = TABLE_FALLBACK.search(line)
        if fallback and current is not None:
            fallbacks[current] = int(fallback.group(1))
    return tables, fallbacks


def test_mncs_tables_are_normative_for_host_projection():
    """The .mncs TABLE literals own name->discriminant mapping; host dicts must match.

    Mutating a code, name, or row in interest_named.mncs without updating
    the host materialization fails here. The backends execute the .mncs
    side (named corpus); this test binds the Python side to the same
    literals.
    """
    from mncs_commons.mesh.interest import (
        KIND_DISCRIMINANTS,
        LIFECYCLE_DISCRIMINANTS,
        OUTCOME_DISCRIMINANTS,
    )

    tables, fallbacks = _parse_mncs_tables()
    assert set(tables) == {"kind", "outcome", "state"}
    assert set(fallbacks) == {"kind", "outcome", "state"}
    expected = {
        "kind": KIND_DISCRIMINANTS,
        "outcome": OUTCOME_DISCRIMINANTS,
        "state": LIFECYCLE_DISCRIMINANTS,
    }
    for name, rows in tables.items():
        materialized = {row[0]: row[2] for row in rows}
        assert materialized == dict(expected[name]), f"{name} table drifted"
        assert len(rows) == len(materialized), f"{name} has duplicate keys"
        # Unknown names must project to the table fallback on both sides.
        assert fallbacks[name] not in materialized.values(), f"{name} fallback collides"
    assert KIND_DISCRIMINANTS.get("Nope", 6) == fallbacks["kind"]
    assert OUTCOME_DISCRIMINANTS.get("BOGUS", 9) == fallbacks["outcome"]
    assert LIFECYCLE_DISCRIMINANTS.get("archived", 5) == fallbacks["state"]


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

# Each kernel maps to (corpora, mode). Mode "pass" requires a clean PASS
# verdict (no unmet expectations, no blocking obligations). Mode "agreement"
# requires every case to return with its expectation met while tolerating a
# top-level UNKNOWN carried by visible backend obligations -- the same
# tolerance source-study applies (completed_with_unresolved_obligations).
# Agreement mode is a ratchet, not a loophole: kernels whose bodies avoid
# obligation-carrying constructs (iteration with unproven exact cost, as in
# mncs.std.text_map.v1 lookups) belong in "pass" mode, and any kernel that
# stops carrying obligations must be promoted to it.
KERNEL_CASES = {
    "commons/mesh/availability.mncs": [("commons-availability-corpus.json", "pass")],
    "commons/mesh/outcome.mncs": [("commons-outcome-corpus.json", "pass")],
    "commons/mesh/interest.mncs": [
        ("commons-interest-corpus.json", "pass"),
        ("commons-interest-full-corpus.json", "pass"),
    ],
    "commons/mesh/interest_named.mncs": [
        ("commons-interest-named-corpus.json", "agreement"),
    ],
    "commons/mesh/lattice_check.mncs": [("commons-lattice-corpus.json", "pass")],
    "commons/mesh/lifecycle.mncs": [("commons-lifecycle-corpus.json", "pass")],
}


def _assert_corpus_result(result: dict, mode: str, corpus: str) -> None:
    cases = result.get("cases", [])
    assert cases, f"{corpus}: no cases executed"
    unmet = [
        item.get("case_id")
        for item in cases
        if item.get("status") != "returned" or not item.get("expectation_met")
    ]
    assert not unmet, f"{corpus}: unmet cases {unmet[:5]}"
    if mode == "pass":
        assert result["status"] == "PASS", json.dumps(result)[:2000]


@needs_toolchain
@pytest.mark.parametrize("backend", ["mncs-research-bytecode", "portable-wasm"])
@pytest.mark.parametrize("kernel", sorted(KERNEL_CASES))
def test_mncs_backends_execute_mesh_corpora(tmp_path, kernel, backend):
    checkout = _toolchain()
    assert checkout is not None
    binary = checkout / "target" / "debug" / "mncs"
    source = MNCS_DIR / kernel
    environment = dict(os.environ)
    library = str(checkout / "library")
    environment["MNCS_LIBRARY_PATH"] = library + ":" + str(MNCS_DIR)
    for name, mode in KERNEL_CASES[kernel]:
        corpus = CORPORA / name
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
            timeout=600,
        )
        assert completed.returncode == 0, completed.stderr[-2000:]
        _assert_corpus_result(json.loads(completed.stdout), mode, name)


@needs_toolchain
def test_executor_lane_agrees_with_mirror_on_sync(tmp_path):
    """Production kernel lane decides the identical sync as the mirror.

    Two fresh node pairs exchange the same fixture set under the same
    restrictive interest; the mirror lane and the ``experiment run``
    lane must receive the same digests with the same skip accounting.
    This is the production execution path for MNCS-owned membership law.
    """

    from mncs_commons.mesh import InterestFilter, MncsKernelExecutor
    from mncs_commons.mesh.node import CommonsNode
    from mncs_commons.mesh.transport import synchronize

    def fixture(suffix: str, kind: str, outcome: str) -> dict:
        record = make_record(kind)
        record["metadata"]["recordId"] = f"test:exec:{suffix}"
        details = dict(record.get("details", {}))
        details["outcome"] = outcome
        record["details"] = details
        return record

    fixtures = [
        ("a", "Finding", "PASS"),
        ("b", "Finding", "FAIL"),
        ("c", "Claim", "PASS"),
        ("d", "Observation", "UNKNOWN"),
        ("e", "Question", "PASS"),
    ]
    interest = InterestFilter.from_mapping({"kinds": ["Finding", "Claim"], "outcomes": ["PASS"]})
    received: list[set] = []
    skipped: list[int] = []
    for lane in ("mirror", "kernel"):
        local = CommonsNode(tmp_path / f"local-{lane}", node_id=f"local-{lane}", domain="d")
        local.init()
        remote = CommonsNode(tmp_path / f"remote-{lane}", node_id=f"remote-{lane}", domain="d")
        remote.init()
        for suffix, kind, outcome in fixtures:
            local.publish_local(fixture(suffix, kind, outcome))
        executor = MncsKernelExecutor() if lane == "kernel" else None
        if executor is not None:
            assert executor.available
        report = synchronize(
            remote,
            DirectCarrier(local),
            interest=interest,
            push=False,
            executor=executor,
        )
        received.append(set(remote.frontier()))
        skipped.append(report["pull"]["skippedByInterest"])
    assert received[0] == received[1]
    assert len(received[0]) == 2
    assert skipped[0] == skipped[1] == 3


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
