#!/usr/bin/env python3
"""Run the cheap repository-local semantic declaration check."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from mncs_commons.family_graph import bind_declaration_evidence


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--declaration",
        type=Path,
        default=Path("family-semantic-contracts-v1.json"),
    )
    args = parser.parse_args()
    root = args.root.resolve()
    declaration_path = args.declaration
    if not declaration_path.is_absolute():
        declaration_path = root / declaration_path
    value = json.loads(declaration_path.read_text(encoding="utf-8"))
    bound = bind_declaration_evidence(root, value)
    from mncs_commons.family_graph import declaration_identity

    print(
        json.dumps(
            {
                "repository_id": bound["repository_id"],
                "declaration_identity": declaration_identity(bound),
                "evidence_digests": bound["_evidence_digests"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
