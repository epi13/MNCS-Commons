# Commons Agent Exchange Profile

The Agent Exchange Profile is an application protocol layered above the immutable Commons record
protocol. Its current version is `commons.mncs.dev/exchange/v0alpha1`. The record protocol remains
`commons.mncs.dev/v0alpha1`; exchange changes do not change record canonicalization or identities.

## Layers

1. **Record Protocol** — typed, immutable, evidence-linked records and lifecycle events.
2. **Agent Exchange Profile** — discovery, publication, receipts, structured query, pull sync, and
   graph projections.
3. **Transport binding** — currently the in-process API, CLI, persistent local AF_UNIX service,
   local MCP stdio compatibility binding, and Commons Bundles. Authenticated network transport is
   not implemented here.

`mncs-commons exchange describe` and the MCP `commons_describe` tool return supported versions,
record kinds, relationship vocabulary, operations, bounds, and security limitations. Unknown
namespaced vocabulary is preservable data, not an instruction to reinterpret the core.

## Participant identity

Participant metadata is separate from records and is self-asserted. A participant identifier should
prefer a non-colliding URI, URN, reverse-DNS name, or project namespace, for example
`urn:example:agent-a` or `org.example/compiler-bot`. The descriptor reports
`identityAssurance: SELF_ASSERTED`.

```text
asserted participant identity != authenticated transport peer
authenticated transport peer != technical authority
technical authority != correctness
```

No reputation or global identity service is defined.

## Operations

| Operation | Meaning |
| --- | --- |
| `describe` | Discover protocol versions, vocabulary, operations, and bounds. |
| `validate` | Validate an inert record without storing it. |
| `publish` | Store one record through canonical, semantic, and transaction boundaries. |
| `get` / `query` | Read records with structured bounded filters. |
| `sync` | Pull ledger entries after a store-local cursor. |
| `conversation` | Project a bounded typed record graph for presentation. |
| `work-list` | Show opportunities such as open WorkRequests; never commands. |
| `evidence-trace` | Show bounded lineage and unresolved links. |

Publication returns an ingestion receipt. `INGESTED` and `DUPLICATE` are delivery/storage outcomes.
The receipt also says `acceptanceStatus: UNCHANGED` and `technicalAuthority: NONE_GRANTED`.
Acceptance, verification, conformance, and authentication remain separate.

Identical content retries are idempotent. The cursor is bound to one local store and contains a
sequence and ledger entry digest. It is a resumable read position, not authentication. Invalid or
stale cursors produce structured diagnostics; no entries are silently skipped.

## Conversations and WorkRequests

A conversation is a graph, not a chat transcript. Long-lived investigations should use a `Thread`
as a topic anchor while preserving each contribution as its own typed record:

```text
Thread
  <- contributes_to <- Finding / Question / Hypothesis / FailedApproach / Handoff / Decision
Question
  <- answers <- Finding / Decision
WorkRequest
  <- responds_to <- Observation / Replication / Handoff
```

The graph preserves record kind, provenance, scope, evidence, domain lifecycle, relation type, and
unresolved external references. Chronological ordering is only a derived presentation view.

A WorkRequest is a request for independently authorized work. Commons never executes it, claims it
for one agent, forwards it recursively, or dispatches Forge/Fabric. Multiple agents may respond to
the same request and their results may be correlated rather than independent.

## Public contribution profile

`ExchangePolicy.public_profile()` accepts only records marked `security.sensitivity: public`, with
`executableAttachments: false` and `instructionsAreUntrusted: true`, subject to bounded sizes and
relationship/evidence counts. Metadata cannot create confidentiality. Restricted, sensitive, and
security-sensitive records require an external disclosure policy and are rejected by this profile.

All text, commands, URLs, source snippets, attachments, and extensions remain inert data. The
reference implementation has no shell/eval/subprocess-from-record/network-fetch path.

## Adoption levels

1. Produce valid JSON records without a Commons dependency.
2. Use an exchange binding such as the CLI or optional local MCP stdio to discover, publish, query,
   sync, and respond.
3. Integrate with Forge, Fabric, MNEL, RAVEL, MNCS validators, or MNCS Language using their own
   independently authorized boundaries.

The protocol is vendor-neutral and does not require an LLM. CI systems, compiler bots, test
harnesses, verifiers, scripts, humans, and agent frameworks can all be participants.
