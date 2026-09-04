# SPDX-License-Identifier: Apache-2.0
"""Published family ChangeSets: everything under family/changesets/ validates.

The mncs-actions advancement lifecycle stages accepted family-graph
ChangeSets here (verbatim bundle bytes, append-only) through a Commons
PR. Commons decides nothing about promotion; this test only asserts
that what Commons publishes is well-formed owner-side: every record
validates, carries exactly the promotion profile (one promotes edge,
predecessor chain), and pins exact base revisions.
"""

from __future__ import annotations

import json
from pathlib import Path

from mncs_commons.family import producer_references
from mncs_commons.validation import validate_record

PUBLISHED = Path(__file__).resolve().parents[1] / "family" / "changesets"


def _records() -> list[Path]:
    if not PUBLISHED.is_dir():
        return []
    return sorted(PUBLISHED.glob("changeset.*.json"))


def test_published_changesets_validate() -> None:
    for path in _records():
        record = json.loads(path.read_text(encoding="utf-8"))
        report = validate_record(record)
        assert report.valid, (path.name, report.diagnostics)


def test_published_changesets_carry_the_promotion_profile() -> None:
    for path in _records():
        record = json.loads(path.read_text(encoding="utf-8"))
        assert record["kind"] == "ChangeSet", path.name
        details = record["details"]
        assert details.get("predecessorGraph"), path.name
        groups = [item["group"] for item in details["references"]]
        assert groups.count("promotes") == 1, path.name
        for revision in details["baseRevisions"]:
            commit = revision["commit"]
            assert len(commit) == 40, path.name
            int(commit, 16)


def test_published_changeset_references_are_digest_bound() -> None:
    for path in _records():
        for reference in producer_references(json.loads(path.read_text(encoding="utf-8"))):
            assert reference["contentDigest"].startswith("sha256:"), path.name
