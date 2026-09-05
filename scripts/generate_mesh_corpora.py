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

sys.path.insert(0, str(REPO / "src"))
from mncs_commons.mesh.interest import mirror_matches_full  # noqa: E402

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


def byte_view(text: str, width: int = 16) -> dict:
    encoded = [ord(character) for character in text]
    assert len(encoded) <= width, f"{text!r} exceeds width {width}"
    padded = encoded + [0] * (width - len(encoded))
    return {"sequence": {"values": [{"byte": {"value": b}} for b in padded]}}


def u64(value: int) -> dict:
    return {"integer": {"value": value, "type": {"bits": 64, "signed": False}}}


KIND_NAMES = {
    "Finding": 0,
    "Claim": 1,
    "Replication": 2,
    "Observation": 3,
    "Question": 4,
    "WorkRequest": 5,
}
OUTCOME_NAMES = {"PASS": 0, "FAIL": 1, "UNKNOWN": 2}
STATE_NAMES = {"proposed": 0, "reproduced": 1, "verified": 2, "accepted": 3}


NAMED_KINDS = ("Finding", "Claim", "Replication", "Observation", "Question", "WorkRequest")


def build_named_interest_corpus() -> dict:
    # Structural sample, not a cross product: backend cost is ~30s/case
    # (thousands of steps per textmap lookup), so the checked-in contract
    # hits every table row plus miss/unknown/empty fallbacks plus
    # restricted-subscription combinations (25 cases). The Python mirror
    # test replays every checked-in case fast.
    module = "commons.mesh.interest_named"
    match_all = ((True,) * 6, (True,) * 3, 0)
    restricted = (
        (True, False, False, False, False, False),
        (True, False, False),
        3,
    )
    probe_kinds = list(NAMED_KINDS) + ["LifecycleEvent", ""]
    probe_outcomes = ["PASS", "FAIL", "UNKNOWN", "BOGUS"]
    probe_states = ["proposed", "reproduced", "verified", "accepted", "archived"]
    probes = (
        [("match-all", match_all, kind, "PASS", "proposed") for kind in probe_kinds]
        + [("match-all", match_all, "Finding", outcome, "verified") for outcome in probe_outcomes]
        + [("match-all", match_all, "Claim", "FAIL", state) for state in probe_states]
        + [
            ("restricted", restricted, kind, outcome, state)
            for kind in ("Finding", "LifecycleEvent")
            for outcome in ("PASS", "BOGUS")
            for state in ("verified", "archived")
        ]
    )
    cases = []
    for sub_name, (kf, of_, min_rank), kind, outcome, state in probes:
        kind_code = KIND_NAMES.get(kind, 6)
        outcome_code = OUTCOME_NAMES.get(outcome, 9)
        state_code = STATE_NAMES.get(state, 5)
        expected = mirror_matches(kind_code, outcome_code, state_code, kf, of_, min_rank)
        args = (
            [
                byte_view(kind),
                u64(len(kind)),
                byte_view(outcome),
                u64(len(outcome)),
                byte_view(state),
                u64(len(state)),
            ]
            + [boolean(flag) for flag in kf]
            + [boolean(flag) for flag in of_]
            + [integer(min_rank)]
        )
        case_kind = kind if kind else "empty"
        cases.append(
            {
                "id": f"named-{sub_name}-{case_kind}-{outcome}-{state}",
                "request": request(module, "candidate_matches_named", args),
                "expected": [boolean(expected)],
            }
        )
    return {"schema_version": "0.1", "name": "commons-interest-named", "cases": cases}


# Independent transcription of the transition law owned by
# src/mncs_commons/mesh/mncs/commons/mesh/lifecycle.mncs (states 0-8 in
# LifecycleState order). Backend agreement with this mirror is the
# mixed-implementation interop evidence; the Python runtime in
# src/mncs_commons/lifecycle.py must agree with the same contract.
LIFECYCLE_ALLOWED = {
    0: {1, 4, 6, 7, 8},
    1: {2, 4, 6, 7, 8},
    2: {3, 4, 5, 6, 8},
    3: {5, 6, 8},
    4: {1, 2, 5, 6, 7, 8},
    5: set(),
    6: set(),
    7: {5, 8},
    8: set(),
}


def mirror_transition_allowed(current: int, target: int) -> bool:
    return current in LIFECYCLE_ALLOWED and target in LIFECYCLE_ALLOWED[current]


def mirror_transition_check(
    current: int, target: int, from_matches: bool, authority_ok: bool
) -> int:
    mask = 0
    if current not in range(9):
        mask |= 1
    if target not in range(9):
        mask |= 2
    if not mirror_transition_allowed(current, target):
        mask |= 4
    if not from_matches:
        mask |= 8
    if not authority_ok:
        mask |= 16
    return mask


def build_lifecycle_corpus() -> dict:
    module = "commons.mesh.lifecycle"
    cases = []
    for current in range(-1, 11):
        for target in range(-1, 11):
            cases.append(
                {
                    "id": f"allowed-{current}-{target}",
                    "request": request(
                        module, "transition_allowed", [integer(current), integer(target)]
                    ),
                    "expected": [boolean(mirror_transition_allowed(current, target))],
                }
            )
    check_points = [(c, t) for c in range(9) for t in range(9)]
    check_points += [(c, t) for c in (-1, 9) for t in (-1, 9)]
    for current, target in check_points:
        for from_matches in (False, True):
            for authority_ok in (False, True):
                cases.append(
                    {
                        "id": f"check-{current}-{target}-{int(from_matches)}{int(authority_ok)}",
                        "request": request(
                            module,
                            "transition_check",
                            [
                                integer(current),
                                integer(target),
                                boolean(from_matches),
                                boolean(authority_ok),
                            ],
                        ),
                        "expected": [
                            integer(
                                mirror_transition_check(current, target, from_matches, authority_ok)
                            )
                        ],
                    }
                )
    return {"schema_version": "0.1", "name": "commons-lifecycle-law", "cases": cases}


FULL_WANT_PATTERNS = {
    "all": (True,) * 6,
    "none": (False,) * 6,
    "finding-only": (True, False, False, False, False, False),
    "claim-only": (False, True, False, False, False, False),
    "replication-only": (False, False, True, False, False, False),
    "observation-only": (False, False, False, True, False, False),
    "question-only": (False, False, False, False, True, False),
    "work-only": (False, False, False, False, False, True),
}

# (has, ok) pairs after (kind_code, want×6, has_kinds): projects,
# contracts, producers, outcomes, states, reltypes, labels.
NEUTRAL_DIMS = (False, True) * 7


def full_case(case_id: str, kind_code: int, want, extras: dict) -> dict:
    values = {
        "kind_code": kind_code,
        "want": want,
        "has_kinds": True,
        "dims": NEUTRAL_DIMS,
        "record_id_hit": False,
        "open_work_only": False,
        "is_open_work": True,
        "promotion_relevant": False,
        "is_promo_relevant": True,
    }
    values.update(extras)
    dims = values["dims"]
    args = (
        [integer(values["kind_code"])]
        + [boolean(flag) for flag in values["want"]]
        + [boolean(values["has_kinds"])]
        + [boolean(item) for item in dims]
        + [boolean(values["record_id_hit"])]
        + [
            boolean(values["open_work_only"]),
            boolean(values["is_open_work"]),
            boolean(values["promotion_relevant"]),
            boolean(values["is_promo_relevant"]),
        ]
    )
    assert len(args) == 27, len(args)
    expected = mirror_matches_full(
        values["kind_code"],
        tuple(values["want"]),
        values["has_kinds"],
        *dims,
        values["record_id_hit"],
        values["open_work_only"],
        values["is_open_work"],
        values["promotion_relevant"],
        values["is_promo_relevant"],
    )
    return {
        "id": case_id,
        "request": request("commons.mesh.interest", "candidate_matches_full", args),
        "expected": [boolean(expected)],
    }


def build_full_interest_corpus() -> dict:
    cases = []
    cases.append(full_case("full-all-neutral-true", 0, FULL_WANT_PATTERNS["all"], {}))
    cases.append(
        full_case(
            "full-record-id-overrides",
            6,
            FULL_WANT_PATTERNS["none"],
            {
                "dims": (True, False) * 7,
                "record_id_hit": True,
                "open_work_only": True,
                "is_open_work": False,
                "promotion_relevant": True,
                "is_promo_relevant": False,
            },
        )
    )
    for code in range(7):
        for name, want in FULL_WANT_PATTERNS.items():
            cases.append(full_case(f"full-kind-{code}-{name}", code, want, {}))
    # Each conjunct kills the decision once while everything else passes.
    dim_names = [
        "kinds",
        "projects",
        "contracts",
        "producers",
        "outcomes",
        "states",
        "reltypes",
        "labels",
    ]
    for index, dim in enumerate(dim_names):
        killed = list(NEUTRAL_DIMS)
        if dim == "kinds":
            cases.append(
                full_case(f"full-kill-{dim}", 6, FULL_WANT_PATTERNS["all"], {"has_kinds": True})
            )
            continue
        killed[2 * (index - 1)] = True
        killed[2 * (index - 1) + 1] = False
        cases.append(
            full_case(f"full-kill-{dim}", 0, FULL_WANT_PATTERNS["all"], {"dims": tuple(killed)})
        )
    cases.append(
        full_case(
            "full-kill-open-work",
            0,
            FULL_WANT_PATTERNS["all"],
            {"open_work_only": True, "is_open_work": False},
        )
    )
    cases.append(
        full_case(
            "full-kill-promo",
            0,
            FULL_WANT_PATTERNS["all"],
            {"promotion_relevant": True, "is_promo_relevant": False},
        )
    )
    import random

    # Seeded fuzz stays small on purpose: backend cost is per-case
    # (~seconds for wide argument lists), so the checked-in contract
    # covers the kind matrix plus per-conjunct kills exhaustively and
    # samples the tails. The Python mirror test replays every case fast.
    rng = random.Random(20260904)
    for sample in range(24):
        kind_code = rng.randrange(8) - 1
        want = tuple(rng.random() < 0.5 for _ in range(6))
        dims = tuple(rng.random() < 0.5 for _ in range(14))
        cases.append(
            full_case(
                f"full-fuzz-{sample:03d}",
                kind_code,
                want,
                {
                    "has_kinds": rng.random() < 0.5,
                    "dims": dims,
                    "record_id_hit": rng.random() < 0.2,
                    "open_work_only": rng.random() < 0.3,
                    "is_open_work": rng.random() < 0.7,
                    "promotion_relevant": rng.random() < 0.3,
                    "is_promo_relevant": rng.random() < 0.7,
                },
            )
        )
    return {"schema_version": "0.1", "name": "commons-interest-full", "cases": cases}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--toolchain", default=None)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    corpora = {
        "commons-availability-corpus.json": build_availability_corpus(),
        "commons-outcome-corpus.json": build_outcome_corpus(),
        "commons-interest-corpus.json": build_interest_corpus(),
        "commons-interest-named-corpus.json": build_named_interest_corpus(),
        "commons-interest-full-corpus.json": build_full_interest_corpus(),
        "commons-lattice-corpus.json": build_lattice_corpus(),
        "commons-lifecycle-corpus.json": build_lifecycle_corpus(),
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
