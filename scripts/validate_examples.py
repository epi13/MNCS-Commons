"""Validate checked-in example documents without executing their reproduction fields."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mncs_commons.io import load_document
from mncs_commons.validation import validate_event, validate_record


def main() -> int:
    failures: list[str] = []
    for path in sorted(Path("examples").rglob("*")):
        if path.suffix.lower() not in {".json", ".yaml", ".yml"}:
            continue
        try:
            value = load_document(path)
            values = (
                value.get("records", []) + value.get("events", [])
                if isinstance(value, dict) and "records" in value
                else [value]
            )
            for index, item in enumerate(values):
                report = (
                    validate_event(item)
                    if item.get("kind") == "LifecycleEvent"
                    else validate_record(item)
                )
                if not report.valid:
                    failures.extend(
                        f"{path}[{index}]: {diagnostic.code} {diagnostic.path}"
                        for diagnostic in report.diagnostics
                    )
        except Exception as error:  # noqa: BLE001 - report all example failures as diagnostics
            failures.append(f"{path}: {error}")
    if failures:
        print("\n".join(failures))
        return 1
    print("all examples valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
