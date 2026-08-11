"""Run one fixed Commons check for the Forge declared-workflow boundary.

This module is a development-time Forge provider helper, not part of the Commons runtime.  It
accepts only a fixed check name, invokes a fixed argv array without a shell, and emits one compact
JSON object so Forge can distinguish a passing check from mere command completion.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

CHECKS: dict[str, tuple[str, ...]] = {
    "compileall": ("python", "-m", "compileall", "-q", "src"),
    "ruff": ("ruff", "check", "src", "tests", "scripts"),
    "mypy": ("mypy", "src"),
    "pytest": ("pytest", "-q"),
    "examples": ("python", "scripts/validate_examples.py"),
    "compatibility": ("python", "scripts/validate_compat.py"),
    "live-compat": ("python", "scripts/validate_live_compat.py"),
    "security-inertness": ("pytest", "-q", "-k", "inert"),
    "evidence-lineage": ("pytest", "-q", "tests/test_evidence.py"),
    "cli-help": ("python", "-m", "mncs_commons.cli", "--help"),
    "agent-exchange": ("python", "scripts/validate_agent_exchange.py"),
    "local-agent": ("python", "scripts/validate_local_agent.py"),
    "knowledge-lifecycle": ("python", "scripts/local_knowledge_lifecycle.py"),
    "exchange-security": ("pytest", "-q", "tests/test_exchange.py"),
    "mcp-parity": ("python", "scripts/validate_mcp.py"),
    "exchange-vectors": ("python", "scripts/validate_exchange.py"),
    "public-node-http": ("python", "scripts/validate_public_node.py"),
    "public-node-security": ("pytest", "-q", "tests/test_public_node.py"),
}

TIMEOUT_SECONDS = 180
OUTPUT_LIMIT = 16_384


def _result(status: str, check: str, *, returncode: int | None = None, detail: str = "") -> None:
    witnesses: list[dict[str, object]] = []
    if returncode is not None:
        witnesses.append({"check": check, "returncode": returncode})
    limitations = [detail] if detail else []
    print(
        json.dumps(
            {
                "status": status,
                "witnesses": witnesses,
                "limitations": limitations,
                "unsupported_constructs": [],
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )


def main(argv: list[str] | None = None) -> int:
    values = sys.argv[1:] if argv is None else argv
    if len(values) != 1 or values[0] not in CHECKS:
        _result("UNKNOWN", values[0] if values else "missing", detail="check is not allowlisted")
        return 2
    check = values[0]
    command = list(CHECKS[check])
    try:
        completed = subprocess.run(
            command,
            cwd=Path(__file__).resolve().parents[1],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            timeout=TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        _result("UNKNOWN", check, detail=f"check exceeded {TIMEOUT_SECONDS} seconds")
        return 0
    if completed.returncode == 0:
        if check == "live-compat":
            try:
                report = json.loads(completed.stdout.decode("utf-8"))
                status = str(report.get("status", "UNKNOWN"))
                if status not in {"PASS", "FAIL", "UNKNOWN"}:
                    status = "UNKNOWN"
                _result(status, check, returncode=0, detail="live producer compatibility report")
            except (json.JSONDecodeError, UnicodeDecodeError):
                _result(
                    "UNKNOWN",
                    check,
                    returncode=0,
                    detail="live compatibility report was malformed",
                )
        else:
            _result("PASS", check, returncode=0)
    else:
        diagnostic = (completed.stderr or completed.stdout).decode("utf-8", errors="replace")
        _result(
            "FAIL",
            check,
            returncode=completed.returncode,
            detail=diagnostic[:OUTPUT_LIMIT] or "check returned a non-zero exit code",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
