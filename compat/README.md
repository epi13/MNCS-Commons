# Compatibility snapshots

These small fixtures freeze the producer boundary that Commons understands. The machine-readable
registry is [`producer-contracts.json`](producer-contracts.json). They are
not vendored producer implementations and they do not grant producer authority.

| fixture | source | source commit | Commons behavior |
| --- | --- | --- | --- |
| `forge/forge-cell-execution-0.1.json` | `mncs-forge-mcp/examples/forge-cell/execution-record.json` | `5a56917` | recognized Forge `schema_version=0.1`; execution `PASS` remains evidence |
| `fabric/*.json` | `mncs-fabric/schemas/*-v0.1.schema.json` | `fd6a1e1` | current execution, package binding, manifest, job, node, and cohort records remain inert |
| `mnel/*.json` | `Machine-Native-Experimental-Learning/schemas/*` | `3a44380` | ledger and 0.4 provider portfolio records remain diagnostic evidence |
| `ravel/*.json` | `RAVEL/ravel_versions/0.6/*` | `4b7c3c5` | matched-compute and transaction evidence retain UNKNOWN development boundaries |
| `mncs/*.json` | `machine-native-complexity-standard/schemas/*` | `49400a4` | execution receipt, bundle, and placement identity are preserved separately |
| `mncs-language/*.json` | `mncs-language/crates/mncs-model/src/*` | `26cd7f0` | executable bodies and verifier artifacts remain opaque evidence |

The validator corpus has no stable machine-readable producer result boundary in this checkout and
remains `UNKNOWN`. The MNCS gate-result contract remains
`COMPATIBLE_WITH_UNRESOLVED_FIELDS` because no current producer result fixture is available. All
other listed source schemas are content-fingerprinted; a matching fingerprint with a moved commit
is explicitly reported as a warning, while changed bytes are `DRIFTED`.

Changing a producer schema should cause an unsupported-version or unresolved-field diagnostic;
these snapshots are intended to make that drift visible.
