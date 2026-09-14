# MNCS native observability pressure reconciliation

This is the Commons reconciliation for the 2026-09 observability tranche. It
refreshes every `mncs-debug` pressure against the current Profile 0.17
compiler/runtime and records capability availability separately from consumer
verification.

## Pinned campaign revisions

| Repository | Revision | Role |
| --- | --- | --- |
| `mncs-language` | `dbea90d18b28c8716ab34a8873ba308edba265f7` | compiler, source map, reference runtime |
| `mncs-test` | `65c261680c3ee05a16e1caf422b7f9011f1a3e55` | canonical test provider |
| `mncs-debug` | `178f8bfd05b9ecee6aa5edb912baa59ddcc1bfdd` | debugger consumer and evidence |
| `mncs-actions` | `a5082391c9ac03d395a71fe4decc390a6eb19e7a` | provider transport |
| `mncs-forge-mcp` | `3aa93ee15a057932e12aaccd1133101e9a2c9209` | structured diagnosis and verification |
| `mncs-language-service` | `88b3c275249d119b2af471ea616a22eef1046597` | operation/source projection |
| `MNCS-Commons` | `48c11e3025affc532e83ff59a78af3cb29f40db2` | starting Commons head for this reconciliation |

## Native capability results

| Local pressure | Canonical record | Classification | Evidence-backed result |
| --- | --- | --- | --- |
| P-001 | `MNCS-RUNTIME-F42CEFCE989D` | `PARTIALLY_RESOLVED` | Bounded typed values, versions, operation inputs/outputs, and value-origin traversal pass. Full read/write history and watchpoints remain open. Lifecycle: `available`. |
| P-002 | `MNCS-COMPILER-E445EECC9F96` | `RESOLVED` | The original operation-span reproducer passes, and compiler, debugger, Forge, and language-service consumers all verify the same `mncs.execution-source-map/1`. Lifecycle: `resolved`. |
| P-003 | `MNCS-RUNTIME-D5179B1A5E9D` | `PARTIALLY_RESOLVED` | Nested execution-scoped frames and parent/call-operation ancestry pass. The reference executor has no task scheduler ancestry. Lifecycle: `available`. |
| P-004 | `MNCS-RUNTIME-A32B31916255` | `STILL_OPEN` | Fresh negative reproduction: observations are immutable completed-run projections; no safe suspension/resume exists. Lifecycle: `discovered`. |
| P-005 | `MNCS-RUNTIME-6382A1A44458` | `STILL_OPEN` | Fresh negative reproduction: effect lineage and bounded re-execution do not establish deterministic scheduler/effect/environment replay. Lifecycle: `discovered`. |
| P-006 | `MNCS-VERIFY-54B12B4A78DF` | `RESOLVED` | First-class test result remains the oracle and now hands canonical execution evidence to bounded debug capture. Existing lifecycle remains `resolved`. |
| P-007 | `MNCS-TOOLING-0C870FCAFFEB` | `RESOLVED` | Registered Actions provider transports observation/source-map artifacts without reinterpreting debugger semantics. Existing lifecycle remains `resolved`. |
| P-008 | `MNCS-TOOLING-673C8430E951` | `PARTIALLY_RESOLVED` | Operation source resolution is verified against the compiler map; live breakpoint execution remains unsupported. Lifecycle: `available`. |
| P-009 | `MNCS-COMPILER-94428E41EEAC` | `RESOLVED` | Structured compiler/runtime boundary remains verified on the native path. Existing lifecycle remains `resolved`. |
| P-010 | `MNCS-TOOLING-A74DFC47DDB6` | `PARTIALLY_RESOLVED` | Native observation modes are near direct execution; complete debugger recording remains bootstrap/semantic-core bound. Lifecycle: `available`. |
| P-011 | `MNCS-RUNTIME-3B723B6FADD8` | `PARTIALLY_RESOLVED` | Supported effects emit shared invocation/result identities and capability/frame lineage. Input/result values, task ancestry, and environment capture remain incomplete. Lifecycle: `available`. |
| P-012 | `MNCS-TOOLING-14E88C1C7431` | `PLATFORM_BOUNDARY` | Workspace quota/storage is operational evidence, not a semantic runtime result. Lifecycle remains `deferred`. |

## Evidence lineage

The debugger evidence is checked in at
`mncs-debug/evidence/native-observability-demonstrations-2026-09.json` and
`mncs-debug/evidence/native-observability-overhead-2026-09.json`. The exact
operation/source-map, frame, value, effect, test execution, observation, and
Forge identities are retained there. Append-only Commons observations and
verification documents reference those artifacts and the owner revisions.

The resolved P-002 chain is:

```text
original operation-span reproducer FAIL
  → mncs-language emits execution-source-map/1
  → mncs-debug joins operation events to exact spans
  → language-service and Forge consume the same map
  → all four affected repositories verify PASS
  → Commons record transitions to resolved
```

No record was marked resolved merely because an owner commit existed. Partial
records remain available but unresolved where the broader requirement still
includes unsupported task, watchpoint, environment, suspension, or replay
semantics.

## Ownership

`mncs-language` owns compiler/runtime facts, `mncs-debug` interprets them,
`mncs-language-service` projects source locations, `mncs-actions` transports
artifacts, and Forge reasons over structured evidence. Commons records the
pressure lifecycle; it does not execute or reinterpret the fixtures.
