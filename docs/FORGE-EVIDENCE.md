# Forge-controlled development evidence

This file records the bounded Forge development evidence for the 0.3 iteration. It is not an
independent evaluation or a conformance decision.

Forge source:

- repository: local `../mncs-forge-mcp`
- commit used for the control plane: `bc9388d0ad8e8be554791def5d8aa6ff2f44d72d`
- version: `0.1.0a2`
- interface: local CLI through `../mncs-forge-mcp/.venv/bin/mncs-forge`
- Commons configuration: [`mncs-forge.toml`](../mncs-forge.toml)

The epoch was begun with generator `codex-luna-high-2026-08-08` and evaluator
`local-human-review-v1`. The final epoch and candidate identities are recorded in the final
development report after registration. The candidate is bound to the bounded `src/`, `scripts/`,
and `tests/` surfaces.

## Baseline and candidate slices

The initial declared checks completed with exit code zero but Forge correctly recorded them as
`UNKNOWN`, because plain declared-command completion does not emit structured evidence. Commons
then added the fixed-argv Forge check adapter. Subsequent Forge project checks recorded:

| workflow | status |
| --- | --- |
| compileall | PASS |
| ruff | PASS |
| mypy | PASS |
| pytest | PASS |
| examples | PASS |
| compatibility | PASS |
| cli-help | PASS |
| live-compat | UNKNOWN |
| security-inertness | PASS |

`live-compat` is `UNKNOWN` because the local sibling set has no frozen Fabric source-schema
fingerprint, no stable
validator-result producer envelope, and no current MNCS result fixture. The detailed, read-only
report is available through:

```bash
python scripts/validate_live_compat.py
mncs-commons compat report --repo forge=../mncs-forge-mcp
```

Forge retains the `FAIL > UNKNOWN > PASS` aggregation rule. No UNKNOWN was promoted to PASS.

The Forge ledger itself is local runtime state under `.mncs-forge/` and is intentionally ignored by
Git. Its identities and status summary are recorded here so the repository does not claim that a
local ledger is protected custody.
