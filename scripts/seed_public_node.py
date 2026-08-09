"""Operator-run deterministic bootstrap seeding for an experimental public node."""

from __future__ import annotations

import argparse
from pathlib import Path

from mncs_commons.bootstrap import seed_public


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("store", type=Path)
    parser.add_argument("--domain", default="public")
    args = parser.parse_args()
    import json

    print(json.dumps(seed_public(args.store, args.domain), sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
