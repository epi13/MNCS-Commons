# Compatibility snapshots

These small fixtures freeze the producer boundary that Commons understands. The machine-readable
registry is [`producer-contracts.json`](producer-contracts.json). They are
not vendored producer implementations and they do not grant producer authority.

| fixture | source | source commit | Commons behavior |
| --- | --- | --- | --- |
| `forge/forge-cell-execution-0.1.json` | `mncs-forge-mcp/examples/forge-cell/execution-record.json` | `bc9388d` | recognized Forge `schema_version=0.1`; execution `PASS` remains evidence, attestation remains `ABSENT` |
| `mnel/mnel-episode-0.1.json` | `Machine-Native-Experimental-Learning/schemas/mnel-records.schema.json` episode definition | `7e11fbd` | current ledger envelope translated as diagnostic evidence; no verdict promotion |
| `ravel/ravel-0.6-development-record.json` | `RAVEL/ravel_versions/0.6/ravel-0.6-development-record.json` | `2bc3003` | development record remains UNKNOWN where source is UNKNOWN |
| `mncs-language/semantic-identity-boundary.json` | `mncs-language/crates/mncs-model/src/identity.rs` | `bbc3cef` | stable semantic identity is preserved opaquely |

The current MNCS standard exposes a stable gate-result schema and has an inert adapter, but no local
producer result fixture was available; the contract therefore remains
`COMPATIBLE_WITH_UNRESOLVED_FIELDS`. The validator corpus has no stable machine-readable producer
result boundary in this checkout and remains `UNKNOWN`. The local `mncs-fabric` checkout is
present, but no frozen Fabric source-schema fingerprint is registered yet, so the Fabric boundary
also remains `UNKNOWN`. The adapter remains a conservative field-preserving boundary.

Changing a producer schema should cause an unsupported-version or unresolved-field diagnostic;
these snapshots are intended to make that drift visible.
