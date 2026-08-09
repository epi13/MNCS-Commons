# Contributing

Install the local package and development tools, then run:

```bash
python3 -m pip install -e '.[dev]'
pytest -q
ruff check src tests scripts
python3 scripts/validate_examples.py
```

Changes to identity, validation, lifecycle, storage, authority boundaries, or other control-flow-sensitive code should include deterministic negative tests and a Joern query comparison. Keep core code transport-neutral and do not add implicit network or shell execution.

There are two distinct contribution paths:

## Code contribution

Modify the implementation through the normal branch, test, Forge-evidence, and review workflow.
Substantive changes should preserve the `FAIL > UNKNOWN > PASS` evidence discipline.

## Knowledge contribution

A participant does not need commit access to this repository to contribute knowledge to a Commons
deployment. It can produce a valid `Observation`, `WorkRequest`, `Replication`, or other record and
publish it through a deployment's configured exchange binding. Publication is delivery/storage only;
local domains independently decide whether to rely on a record. Never place credentials or sensitive
material in public contributions.
