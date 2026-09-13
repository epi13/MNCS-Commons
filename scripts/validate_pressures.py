"""Validate the canonical pressure exchange and its checked-in projections."""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mncs_commons.pressure import PressureRegistry


def _json_files(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*.json"))
        if path.is_file()
    }


def main() -> int:
    repository_root = Path(__file__).resolve().parents[1]
    pressure_root = repository_root / "pressures"
    registry = PressureRegistry(pressure_root)
    report = registry.validate()
    if not report.valid:
        for diagnostic in report.diagnostics:
            print(f"{diagnostic.code} at {diagnostic.path}: {diagnostic.message}")
        return 1

    checked_in = _json_files(pressure_root / "views")
    with tempfile.TemporaryDirectory(prefix="mncs-pressure-validate-") as temporary:
        temporary_root = Path(temporary) / "pressures"
        shutil.copytree(pressure_root, temporary_root)
        generated_registry = PressureRegistry(temporary_root)
        generated_registry.generate_views()
        generated = _json_files(temporary_root / "views")
    if checked_in != generated:
        missing = sorted(set(generated) - set(checked_in))
        unexpected = sorted(set(checked_in) - set(generated))
        changed = sorted(
            path for path in set(checked_in) & set(generated) if checked_in[path] != generated[path]
        )
        if missing:
            print("missing generated views: " + ", ".join(missing))
        if unexpected:
            print("unexpected generated views: " + ", ".join(unexpected))
        if changed:
            print("stale generated views: " + ", ".join(changed))
        return 1
    print(f"pressure registry valid; {len(registry.projections())} pressures; views current")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
