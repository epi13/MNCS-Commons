"""Freshness and authority checks for the bounded family read projection."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from mncs_commons.family_projection import build_family_agent_projection


ROOT = Path(__file__).resolve().parents[1]


def _projection_root(tmp_path: Path) -> Path:
    root = tmp_path / "commons"
    shutil.copytree(ROOT / "family", root / "family")
    shutil.copytree(ROOT / "pressures", root / "pressures")
    return root


def test_current_generated_pressure_view_is_bound_to_registry(tmp_path: Path) -> None:
    value = build_family_agent_projection(
        _projection_root(tmp_path), "mncs-language-service", max_items=8
    )

    assert value["status"] == "verified"
    assert value["freshness"] == "current"
    assert value["pressures"]["freshness"] == "current"
    assert value["pressures"]["registry_identity"].startswith("sha256:")
    assert value["pressures"]["view_identity"].startswith("sha256:")


def test_stale_generated_pressure_view_is_not_current(tmp_path: Path) -> None:
    root = _projection_root(tmp_path)
    view_path = root / "pressures" / "views" / "unresolved-language.json"
    view = json.loads(view_path.read_text(encoding="utf-8"))
    view["pressures"][0]["title"] = "tampered"
    view_path.write_text(json.dumps(view), encoding="utf-8")

    value = build_family_agent_projection(root, "mncs-language-service", max_items=8)

    assert value["status"] == "verified"
    assert value["freshness"] == "stale"
    assert value["pressures"]["freshness"] == "stale"
    assert "pressure view is stale" in " ".join(value["limitations"])
