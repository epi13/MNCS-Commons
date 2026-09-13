# Atlas WASM backend pressure evidence — 2026-09

This page is the human-readable companion to the immutable Commons pressure
records. The JSON declarations and append-only observations remain the
machine-readable source of truth:

- [`MNCS-LANG-4F3798658F55`](../../pressures/records/MNCS-LANG-4F3798658F55.json)
  — nested cell address normalization.
- [`MNCS-LANG-4219A56741DB`](../../pressures/records/MNCS-LANG-4219A56741DB.json)
  — packed bounded view lifetime across region reclamation.

## What Atlas exposed

Atlas's current stateful model is a useful pressure workload because it parses
bounded JSON, retains typed model state across chunks, and emits a structured
render plan. The model exercised generic cell flattening, scratch-address
transport, packed byte views, and loop-region lifetime in one real consumer.

### Nested cell address normalization

At the pre-fix language revision `a0255f8`, recursive flattening used an `i64`
scratch local as the address for a WASM `i32.load`. The generated module was
rejected by WASM validation before instantiation. The pressure is not an Atlas
special case: the lowering layer must normalize every address to the type
required by the memory instruction while preserving the generic cell layout.

The generic fix is in `mncs-language` commit `f527b49`, where nested flattening
wraps an `i64` scratch address with `i32.wrap_i64`. The regression is named
`nested_flatten_wraps_i64_scratch_addresses_before_memory_access`.

### Packed bounded view lifetime

After address typing was corrected, the full Atlas render plan exposed a
second independent failure at language revision `f527b49`. Bounded byte views
are packed `i64` descriptors, but region planning classified them as
heap-backed views and disabled safe reclamation. The stateful model therefore
retained temporary regions across chunks until the 32 MiB arena was exhausted.

The generic fix is in `mncs-language` commit `f9d790b`, where packed bounded
views are classified as nonallocating words for region planning. The regression
is named `packed_bounded_views_are_preserved_as_nonallocating_words`.

## Verification

Both pressures were verified against language profile `0.16`:

- `mncs-language`: `cargo test -p mncs-codegen` passed, including both focused
  regressions.
- `mncs-atlas`: `python -m unittest tests.test_experimental_wasm -q` passed,
  including independent module instantiation and the complete model render
  plan.

The pressures are marked `resolved` only after both repositories contributed
current PASS verification. No consumer-side workaround is treated as a
resolution, and the original failed reproductions remain preserved in the
append-only Commons observations.
