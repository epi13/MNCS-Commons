#!/usr/bin/env python3
"""Explicit import-backed validation; never manufactures architectural edges."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from mncs_commons.family_graph import audit_stdlib_dependencies


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--stdlib", type=Path, required=True)
    parser.add_argument("--repository", action="append", required=True,
                        help="bounded immediate checkout name; repeat to select")
    args = parser.parse_args()
    if len(args.repository) > 32 or any(Path(name).name != name or name in (".", "..")
                                        for name in args.repository):
        parser.error("select at most 32 immediate checkout names")
    try:
        result = audit_stdlib_dependencies(
            {name: (args.workspace / name).resolve() for name in args.repository},
            args.stdlib.resolve())
    except (OSError, ValueError, KeyError) as error:
        print(json.dumps({"status": "unknown", "error": str(error)}))
        return 2
    print(json.dumps(result, sort_keys=True, indent=2))
    return 5 if result["missing_consumes"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
