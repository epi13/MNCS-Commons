# ADR 0009: Conversations are typed graph projections

## Decision

Commons conversations use existing immutable records and typed relationships. Chronological or
human-readable transcripts are derived views only.

## Rationale

Typed records preserve scope, evidence, provenance, lifecycle, negative results, and concurrent
responses. A chat primitive would encourage prompt history and prose to become the protocol.

## Consequences

Conversation traversal is bounded and cannot infer truth from graph density or agreement count.
