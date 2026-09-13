# Harness artifact contract evidence — 2026-09

This investigation records a compatibility pressure exposed while Atlas's
related Harness implementation was refreshed against current `mncs-language`
`main` at profile `0.16`. The pressure is recorded as
[`MNCS-LANG-59894A2D6A3D`](../../pressures/records/MNCS-LANG-59894A2D6A3D.json).

## Reproduction

The current compiler preserved source-level names such as
`pin_fields_valid` and `fold4` in `function_value_contracts`, while the
physical backend export list contained qualified names such as
`mncs_mncs_harness_pins_v1__pin__fields__valid`. The pre-refresh Harness
runtime checked only the physical list and failed closed before execution with
`...pin_fields_valid is not an artifact export`.

This was an adapter assumption, not permission to edit generated artifacts or
to add a second semantic function registry. The stable execution request is
the source-level function name; backend export spelling is an implementation
detail of the artifact contract.

## Resolution

Harness commit `512af42` regenerated all 18 shipped WASM and research-bytecode
artifacts with language `main` and updated `mncs_runtime` to validate either
legacy direct exports or current source-level function contracts. The artifact
manifest remains identity- and byte-digest-bound.

The current checks are:

- `python scripts/build_mncs_artifacts.py --verify`
- `python -m pytest -q tests/test_mncs_exec.py tests/test_mncs_logic.py tests/test_atlas_context.py`

Both the language producer and Harness consumer supplied PASS verification;
the Commons pressure is resolved. No change to language semantics was needed.
