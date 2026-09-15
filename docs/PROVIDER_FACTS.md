# Generated provider facts

`family-provider-metadata-v1.json` is an optional, generated companion to a
repository-owned `family-semantic-contracts-v1.json` declaration. It reduces
duplicated factual maintenance without inferring consumer intent.

Two authority kinds are currently accepted:

- `language-owned-abi` — callable module/interface metadata and generated host
  binding identity, as used by Ravel;
- `language-owned-export-manifest` — a compiler-owned export manifest for
  command-level compiler/runtime contracts, as used by mncs-language.

The graph validates that generated `providers` exactly equal the declaration's
`provides` facts. A changed provider contract, evidence path, authority kind,
interface identity, or generated content identity therefore cannot silently
leave stale metadata accepted. Consumer `consumes` entries remain explicit
architectural declarations.

Provider metadata may omit `typed_call_schema_version` for an export manifest;
ABI-derived metadata must carry `mncs.typed-call/1`.
