# Producer compatibility

Commons keeps a small, explicit producer contract registry in
[`compat/producer-contracts.json`](../compat/producer-contracts.json). Each entry records the
producer family, record type, source schema/version, source commit, source path, content fingerprint,
fixture, adapter boundary, and known unresolved fields.

The registry is a compatibility lock, not a claim that a producer is authoritative. A matching
fingerprint establishes that the locked source bytes are the bytes inspected by Commons. It does not
establish semantic equivalence, authentication, conformance, or independent verification.

Use the read-only local inspection commands:

```bash
mncs-commons compat list
mncs-commons compat report --repo forge=../mncs-forge-mcp --repo mnel=../Machine-Native-Experimental-Learning
mncs-commons compat check-local --producer mncs-language --repo ../mncs-language
```

The checker never fetches, invokes Git, modifies sibling repositories, or executes producer data. It
reads bounded source files and local Git metadata only. A missing checkout or missing source
fingerprint is `UNKNOWN`; a changed locked source file is `DRIFTED`; a matching source with missing
adapter information is `COMPATIBLE_WITH_UNRESOLVED_FIELDS`.

`scripts/validate_live_compat.py` checks the conventional sibling directories beside Commons. It is
also declared as the Forge `live-compat` project workflow. The Forge result is `PASS` only when all
available locked boundaries are complete, `FAIL` on drift, and `UNKNOWN` when a required producer
checkout or fixture is unavailable.

Current explicit gaps:

- `mncs-fabric` is present locally, but no frozen source-schema fingerprint is registered yet, so
  its disclosed execution envelope remains an unverified adapter contract.
- `mncs-validator-rs` provides a conformance corpus identity, but no stable producer-result
  envelope was available for a Commons adapter.
- The MNCS gate-result schema is fingerprinted and translated inertly, but no current producer
  result fixture is checked in.
