#!/usr/bin/env python3
"""Validate the Commons-owned architecture model for autonomous consumers."""

from __future__ import annotations

import json
from pathlib import Path
import sys

from mncs_commons.architecture import load_architecture_model, validate_architecture_model


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    result = validate_architecture_model(load_architecture_model(root), workspace_root=root)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    sys.exit(main())
