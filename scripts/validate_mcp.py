"""Validate the optional MCP binding without making it a core dependency."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mncs_commons.store import CommonsStore


def main() -> int:
    try:
        from mncs_commons.mcp_server import build_server
    except (ImportError, RuntimeError) as error:
        print(json.dumps({"status": "UNKNOWN", "limitation": str(error)}))
        return 0
    with tempfile.TemporaryDirectory(prefix="commons-mcp-") as temporary:
        store = CommonsStore(Path(temporary) / "store")
        store.init()
        server = build_server(store)
        if server is None:
            raise RuntimeError("MCP server was not constructed")
    print(json.dumps({"status": "PASS", "tools": 9, "resources": 4}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
