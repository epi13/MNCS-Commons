# ADR 0008: Keep Agent Exchange separate from record protocol

## Decision

Define `commons.mncs.dev/exchange/v0alpha1` as an application profile above the existing
`commons.mncs.dev/v0alpha1` record protocol.

## Rationale

Discovery, limits, receipts, cursors, and operations are interaction semantics. Putting them in
record identity would make a transport/interface change alter evidence identities. A separate profile
lets CLI, MCP, bundles, and a future Fabric binding share the same record meanings.

## Consequences

The record protocol remains stable. Exchange receipts cannot be mistaken for acceptance, and future
transport authentication can be represented without making it correctness or technical authority.
