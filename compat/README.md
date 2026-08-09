# Compatibility snapshots

These small fixtures freeze the producer boundary that Commons understands. They are
not vendored producer implementations and they do not grant producer authority.

| fixture | source | source commit | Commons behavior |
| --- | --- | --- | --- |
| `forge/forge-cell-execution-0.1.json` | `mncs-forge-mcp/examples/forge-cell/execution-record.json` | `487c4cb` | recognized Forge `schema_version=0.1`; execution `PASS` remains evidence, attestation remains `ABSENT` |
| `mnel/mnel-episode-0.1.json` | `Machine-Native-Experimental-Learning/schemas/mnel-records.schema.json` episode definition | `a113b04` | diagnostic observation boundary; no verdict promotion |
| `ravel/ravel-0.6-development-record.json` | `RAVEL/ravel_versions/0.6/ravel-0.6-development-record.json` | `2bc3003` | development record remains UNKNOWN where source is UNKNOWN |
| `mncs-language/semantic-identity-boundary.json` | `mncs-language/spec/semantic-core.md` and `examples/semantic-foundation/after.mncs.json` | `faedb83` | stable semantic identity is preserved opaquely |

`mncs-fabric` was not present in the local sibling workspace during this iteration, so no
Fabric schema claim is made. The adapter remains a conservative field-preserving boundary.

Changing a producer schema should cause an unsupported-version or unresolved-field diagnostic;
these snapshots are intended to make that drift visible.
