"""Keep the Store campaign census aligned with Commons' current registry."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "src/mncs_commons/data/family-registry-v0alpha1.json"
CENSUS = ROOT / "docs/persistence-census-2026-09.json"
CLASSIFICATIONS = {
    "SOURCE_DECLARATION",
    "EXTERNAL_INTERCHANGE",
    "EPHEMERAL",
    "DERIVED_CACHE",
    "DURABLE_APPLICATION_STATE",
    "EVIDENCE_ARTIFACT",
    "PLATFORM_SECRET_OR_CREDENTIAL",
    "REFERENCE/HISTORICAL",
}


def test_census_covers_every_current_registry_project():
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    census = json.loads(CENSUS.read_text(encoding="utf-8"))
    assert census["registry"]["path"] == str(REGISTRY.relative_to(ROOT))
    assert census["registry"]["revision"] == registry["revision"]
    assert set(census["classification_vocabulary"]) == CLASSIFICATIONS

    entries = census["entries"]
    registry_ids = {project["id"] for project in registry["projects"]}
    census_ids = {entry["project_id"] for entry in entries}
    assert census_ids == registry_ids
    assert len(entries) == len(census_ids)

    for entry in entries + census["supplemental_workspace_review"]:
        assert entry["project_id"]
        assert entry["surfaces"]
        assert entry["decision"]
        for surface in entry["surfaces"]:
            assert surface["classification"] in CLASSIFICATIONS
            assert surface["evidence"]


def test_census_keeps_deferred_memory_out_of_scope():
    assert "mncs-memory" in json.loads(CENSUS.read_text(encoding="utf-8"))["explicit_non_candidates"]
