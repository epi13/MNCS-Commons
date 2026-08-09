# MNCS Commons 0.2 development protocol

The package is in `0.2.0.dev0`; the wire-level version remains `commons.mncs.dev/v0alpha1`. The
explicit protocol registry rejects unknown wire versions. JSON is normative at the canonicalization
boundary. YAML may be loaded by the CLI when the optional PyYAML dependency is installed; the core
does not import PyYAML at module import time.

## Record envelope

Each record has `apiVersion`, `kind`, `metadata`, `subject`, `scope`, `statement`, `evidence`, `dependencies`, `affectedContracts`, `provenance`, `confidence`, `security`, `lifecycle`, `relationships`, and kind-specific `details`. The JSON Schema is a reviewable snapshot, while the Python validator supplies machine-readable diagnostics and the stricter runtime checks.

`Observation`, `Claim`, `WorkRequest`, `Replication`, `Advisory`, and `Decision` have different meanings, but none has command authority. A `Replication` preserves an `independence` object containing model family, prompt/source, harness, compiler, machine, provider, and artifact ancestry fields when known. The protocol intentionally does not reduce those fields to an independence score.

`evidence` and external references may be unresolved. A reference is not evidence that the target exists, is authentic, or supports the statement. `PASS`, `FAIL`, and `UNKNOWN` are preserved; missing or incompatible context is never promoted to `PASS`.

## Identity and canonical JSON

The content digest is:

```text
sha256(canonical-json(identity-projection(record)))
```

Canonical JSON uses UTF-8, sorted object keys, compact separators, and rejects non-finite numbers. Object order never matters. Arrays are ordered unless their path is explicitly set-like (`evidence`, `relationships`, `dependencies`, `affectedContracts`, and selected provenance/review lists), in which case canonicalized members are sorted. The top-level `contentDigest` is removed before hashing; a metadata content digest is also excluded for defensive compatibility. A digest proves content integrity only. It does not prove publisher identity or correctness.

Logical `metadata.recordId`, content digest, and lifecycle-event digest are separate concepts. A caller may supply a logical ID, but content identity remains derived from the full record projection.

## History and trust-domain acceptance

Records begin in `proposed`. A separate `LifecycleEvent` names the target content digest, `from` and `to` states, evidence, and an explicit authority `{domain, actor, rationale}`. Valid transitions are derived in append order. Acceptance requires a named local domain; no event creates universal acceptance. A broken or stale event is reported and is not applied.

`lifecycle(record, domain="project-a")` projects one domain. `domain_views(record)` returns each domain
represented in the history. A domain with no events remains `proposed` for transition purposes, while
the undirected projection reports `domain-scoped` once domain events exist. Thus A may accept while B
disputes and C remains unreviewed. Rejection, dispute, expiration, and supersession remain local
dispositions; the shared evidence and event history are not rewritten.

The local store writes immutable canonical record/event files and a hash-chained `ledger.jsonl`. A
writer lock serializes appenders. Each write first records an exact-byte transaction journal and
staged content, then commits content, ledger row, and rebuildable tail metadata. An interrupted write
is visible as `PENDING_TRANSACTION`; `store verify` does not repair it and `store recover` only commits
a journal whose identities, sequence, predecessor, and bytes verify. A partial ledger line or
content/ledger mismatch fails verification.

## Scope and staleness

`scope.context` is a structured material context. The compatibility helper compares declared values exactly. A changed source revision, artifact digest, contract identity, compiler, provider/model, dependency, machine, target, semantic graph, or placement identity is incompatible when both values are known and differ. Missing context is `unknown`; an explicit `reviewAt` in the past is `review-required` only when the caller supplies an explicit clock. Similar version strings do not establish equivalence.

## Graph and coordination semantics

Relationships use a small typed vocabulary. Unresolved targets remain legal and are reported as
unresolved rather than silently treated as present. Store insertion adds semantic checks for logical
record revision lineage, self-relations, local event targets, and cycles in `supersedes`/`depends_on`.
Bounded graph traversal is evidence organization only; it does not infer truth. Replication analysis
reports declared shared dimensions and outcomes, never a universal independence score. Work requests
may carry `details.requestState` (`open`, `claimed`, `responded`, `completed`, `unable_to_complete`,
`superseded`, or `withdrawn`); an open request remains a request for independently authorized work.

## Commons Bundles

A Commons Bundle is a deterministic ZIP artifact containing `manifest.json`, canonical record files,
canonical lifecycle-event files, and sorted unresolved external references. The manifest commits to
member paths, sizes, content digests, roots, graph depth, and a bundle digest. Verification bounds
file count and sizes, rejects traversal and symlink paths, detects duplicate/unlisted/mismatched
members, and validates each record. Import is local and idempotent; it never fetches URLs, executes
reproduction content, or grants authority.

## Authority boundary

Reproduction procedures, URLs, attachments, source snippets, and suggested actions are inert untrusted data. Validation, import, query, lifecycle derivation, and adapters never invoke them. Commons does not execute shell/code, mutate repositories/contracts/evaluators, access credentials, bypass sandboxes, or dispatch Forge/Fabric work. An external system must independently authorize and sandbox any requested operation.

## MNCS-family boundaries

Producer compatibility is an explicit read-only contract. `compat/producer-contracts.json` locks
source paths and content fingerprints; `mncs-commons compat report` can inspect supplied sibling
checkouts without fetching or modifying them. `DRIFTED` source is not silently interpreted, and
missing producer checkouts or result fixtures remain `UNKNOWN`.

- Forge remains the execution/orchestration and micro-verification authority. Commons can reference Forge run, candidate, result, failure, evidence-gap, and work-request identities.
- Fabric remains transport/execution infrastructure. Commons records can carry artifact, execution, node, environment, and reconciliation references.
- MNEL observations and learned-provider findings are diagnostic evidence, including negative/resource-placement results; Commons does not treat them as verdicts.
- RAVEL can consume a scoped view containing accepted, disputed, negative, and unresolved records, but Commons does not decide what RAVEL learns.
- MNCS/MNCDS contracts and validators retain technical conformance authority; Commons only references contracts and validation results.
- MNCS Language semantic graphs, intent expressions, lowering envelopes, and evidence obligations can be subjects or references without being reimplemented by Commons.

The checked-in `compat/` snapshots name the source repository and commit represented by the minimal
fixtures. Producer adapters return structured results with source version, recognition state,
unresolved fields, and diagnostics. Missing producer identity or source time is explicit; Commons
does not invent a durable identity or use a synthetic epoch timestamp. The local workspace did not
contain `mncs-fabric`, so Fabric compatibility remains a conservative, unverified boundary.
