#!/usr/bin/env python3
"""Generate exhaustive execution corpora for the Commons Mesh MNCS kernels.

Each corpus drives ``mncs experiment run`` against the real language
backends.  Expected values come from an independent Python mirror of the
documented kernel contract (same tables, separate implementation); backend
agreement with this mirror is the mixed-implementation interop evidence
used by ``tests/test_mesh_interop.py``.

Usage:
    python3 scripts/generate_mesh_corpora.py [--toolchain PATH] [--check]

--check regenerates into a temp dir and diffs against the checked-in
corpora, failing on any drift.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
KERNELS = REPO / "src" / "mncs_commons" / "mesh" / "mncs"
CORPORA = KERNELS / "corpora"

AVAILABILITY = ["Unavailable", "SourceAvailable", "Local", "Mirrored", "Durable", "Canonical"]
RANKS = [0, 1, 2, 3, 4, 5]
OUTCOMES = ["Pass", "Fail", "Unknown"]


def mirror_merge_rank(a: int, b: int) -> int:
    return max(RANKS[a], RANKS[b])


def mirror_should_fetch(known: int, offered: int) -> bool:
    return RANKS[offered] > RANKS[known]


def mirror_combine(a: int, b: int) -> int:
    table = [
        [0, 1, 2],
        [1, 1, 1],
        [2, 1, 2],
    ]
    return table[a][b]


def mirror_agrees(a: int, b: int) -> bool:
    return a == b


def mirror_settled(a: int) -> bool:
    return a in (0, 1)


def mirror_matches(kind, outcome, state, kf, of, min_rank) -> bool:
    kind_ok = kind in (0, 1, 2, 3, 4, 5) and kf[kind]
    outcome_ok = outcome in (0, 1, 2) and of[outcome]
    rank = {0: 1, 1: 2, 2: 3, 3: 4}.get(state, 0)
    return bool(kind_ok and outcome_ok and rank >= min_rank)


def abi_identities(toolchain: Path, kernel: Path) -> dict:
    binary = toolchain / "target" / "debug" / "mncs"
    output = subprocess.run(
        [str(binary), "abi", str(kernel)], capture_output=True, text=True, check=True
    ).stdout
    return json.loads(output)


def finite(module: str, enum: str, variant: str, discriminant: int) -> dict:
    return {
        "finite": {
            "type_identity": f"mncs:0.2:finite-type:{module}::{enum}",
            "variant_identity": f"mncs:0.2:finite-variant:{module}::{enum}::{variant}",
            "discriminant": discriminant,
        }
    }


def integer(value: int) -> dict:
    return {"integer": {"value": value, "type": {"bits": 64, "signed": True}}}


def boolean(value: bool) -> dict:
    return {"boolean": {"value": value}}


def request(module: str, function: str, arguments: list) -> dict:
    return {
        "schema_version": "0.1",
        "target": {"module": module, "function": function},
        "arguments": arguments,
        "step_budget": 4096,
    }


def build_availability_corpus() -> dict:
    module = "commons.mesh.availability"
    cases = []
    for index, variant in enumerate(AVAILABILITY):
        cases.append(
            {
                "id": f"rank-{variant.lower()}",
                "request": request(
                    module, "candidate_rank", [finite(module, "Availability", variant, index)]
                ),
                "expected": [integer(RANKS[index])],
            }
        )
    for first in range(6):
        for second in range(6):
            cases.append(
                {
                    "id": f"merge-{AVAILABILITY[first].lower()}-{AVAILABILITY[second].lower()}",
                    "request": request(
                        module,
                        "candidate_merge_rank",
                        [
                            finite(module, "Availability", AVAILABILITY[first], first),
                            finite(module, "Availability", AVAILABILITY[second], second),
                        ],
                    ),
                    "expected": [integer(mirror_merge_rank(first, second))],
                }
            )
            cases.append(
                {
                    "id": f"fetch-{AVAILABILITY[first].lower()}-{AVAILABILITY[second].lower()}",
                    "request": request(
                        module,
                        "candidate_should_fetch",
                        [
                            finite(module, "Availability", AVAILABILITY[first], first),
                            finite(module, "Availability", AVAILABILITY[second], second),
                        ],
                    ),
                    "expected": [boolean(mirror_should_fetch(first, second))],
                }
            )
    return {"schema_version": "0.1", "name": "commons-availability-exhaustive", "cases": cases}


def build_outcome_corpus() -> dict:
    module = "commons.mesh.outcome"
    cases = []
    for first in range(3):
        for second in range(3):
            combined = mirror_combine(first, second)
            cases.append(
                {
                    "id": f"combine-{OUTCOMES[first].lower()}-{OUTCOMES[second].lower()}",
                    "request": request(
                        module,
                        "candidate_combine",
                        [
                            finite(module, "Outcome", OUTCOMES[first], first),
                            finite(module, "Outcome", OUTCOMES[second], second),
                        ],
                    ),
                    "expected": [finite(module, "Outcome", OUTCOMES[combined], combined)],
                }
            )
            cases.append(
                {
                    "id": f"agrees-{OUTCOMES[first].lower()}-{OUTCOMES[second].lower()}",
                    "request": request(
                        module,
                        "candidate_agrees",
                        [
                            finite(module, "Outcome", OUTCOMES[first], first),
                            finite(module, "Outcome", OUTCOMES[second], second),
                        ],
                    ),
                    "expected": [boolean(mirror_agrees(first, second))],
                }
            )
    for index, variant in enumerate(OUTCOMES):
        cases.append(
            {
                "id": f"settled-{variant.lower()}",
                "request": request(
                    module, "candidate_is_settled", [finite(module, "Outcome", variant, index)]
                ),
                "expected": [boolean(mirror_settled(index))],
            }
        )
    return {"schema_version": "0.1", "name": "commons-outcome-exhaustive", "cases": cases}


def build_interest_corpus() -> dict:
    module = "commons.mesh.interest"
    subscriptions = {
        # match-all: every flag true, min rank 0.
        "match-all": ((True,) * 6, (True,) * 3, 0),
        # selective: findings that PASS at verified-or-better.
        "finding-pass-verified": (
            (True, False, False, False, False, False),
            (True, False, False),
            3,
        ),
        # lifecycle gate only: everything at proposed-or-better.
        "proposed-gate": ((True,) * 6, (True,) * 3, 1),
    }
    kinds = [0, 2, 6]
    outcomes = [0, 2, 9]
    states = [0, 2, 3, 4, 5]
    cases = []
    for sub_name, (kf, of_, min_rank) in subscriptions.items():
        for kind in kinds:
            for outcome in outcomes:
                for state in states:
                    expected = mirror_matches(kind, outcome, state, kf, of_, min_rank)
                    args = (
                        [integer(kind), integer(outcome), integer(state)]
                        + [boolean(flag) for flag in kf]
                        + [boolean(flag) for flag in of_]
                        + [integer(min_rank)]
                    )
                    cases.append(
                        {
                            "id": f"{sub_name}-k{kind}-o{outcome}-s{state}",
                            "request": request(module, "candidate_matches", args),
                            "expected": [boolean(expected)],
                        }
                    )
    return {"schema_version": "0.1", "name": "commons-interest-boundary", "cases": cases}


def build_lattice_corpus() -> dict:
    module = "commons.mesh.lattice_check"
    status_module = "mncs.core.status.v1"
    variants = ["PASS", "FAIL", "UNKNOWN"]
    cases = []
    for first in range(3):
        for second in range(3):
            cases.append(
                {
                    "id": f"lattice-{variants[first].lower()}-{variants[second].lower()}",
                    "request": request(
                        module,
                        "candidate_lattice_agrees",
                        [
                            finite(status_module, "Status", variants[first], first),
                            finite(status_module, "Status", variants[second], second),
                        ],
                    ),
                    "expected": [boolean(True)],
                }
            )
    return {"schema_version": "0.1", "name": "commons-lattice-agreement", "cases": cases}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--toolchain", default=None)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    corpora = {
        "commons-availability-corpus.json": build_availability_corpus(),
        "commons-outcome-corpus.json": build_outcome_corpus(),
        "commons-interest-corpus.json": build_interest_corpus(),
        "commons-lattice-corpus.json": build_lattice_corpus(),
    }
    if args.check:
        failures = 0
        for name, corpus in corpora.items():
            path = CORPORA / name
            if not path.exists():
                print(f"missing corpus: {name}")
                failures += 1
                continue
            current = json.loads(path.read_text(encoding="utf-8"))
            if current != corpus:
                print(f"drift detected: {name}")
                failures += 1
        return 1 if failures else 0
    CORPORA.mkdir(parents=True, exist_ok=True)
    for name, corpus in corpora.items():
        (CORPORA / name).write_text(
            json.dumps(corpus, indent=2, sort_keys=False) + "\n", encoding="utf-8"
        )
        print(f"wrote {name} ({len(corpus['cases'])} cases)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
