# Contributing

Install the local package and development tools, then run:

```bash
python3 -m pip install -e '.[dev]'
pytest -q
ruff check src tests scripts
python3 scripts/validate_examples.py
```

Changes to identity, validation, lifecycle, storage, authority boundaries, or other control-flow-sensitive code should include deterministic negative tests and a Joern query comparison. Keep core code transport-neutral and do not add implicit network or shell execution.
