# MNCS Commons v0.1 protocol

The wire-level version is `commons.mncs.dev/v0alpha1`. JSON is normative at the canonicalization boundary. YAML may be loaded by the CLI when the optional PyYAML dependency is installed; JSON-compatible YAML examples keep the core dependency-free.

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

## History and local acceptance

Records begin in `proposed`. A separate `LifecycleEvent` names the target content digest, `from` and `to` states, evidence, and an explicit authority `{domain, actor, rationale}`. Valid transitions are derived in append order. Acceptance requires a named local domain; no event creates universal acceptance. A broken or stale event is reported and is not applied.

The local store writes immutable canonical record/event files and a hash-chained `ledger.jsonl`. It uses bounded reads, duplicate idempotence, atomic file replacement, content-digest verification, and orphan detection. A partial ledger line or content/ledger mismatch fails verification; it is not silently repaired or rewritten.

## Scope and staleness

`scope.context` is a structured material context. The compatibility helper compares declared values exactly. A changed source revision, contract identity, compiler, provider/model, dependency, machine, or target is incompatible when both values are known and differ. Missing context is `unknown`; an explicit `reviewAt` in the past is `review-required`. Similar version strings do not establish equivalence.

## Authority boundary

Reproduction procedures, URLs, attachments, source snippets, and suggested actions are inert untrusted data. Validation, import, query, lifecycle derivation, and adapters never invoke them. Commons does not execute shell/code, mutate repositories/contracts/evaluators, access credentials, bypass sandboxes, or dispatch Forge/Fabric work. An external system must independently authorize and sandbox any requested operation.

## MNCS-family boundaries

- Forge remains the execution/orchestration and micro-verification authority. Commons can reference Forge run, candidate, result, failure, evidence-gap, and work-request identities.
- Fabric remains transport/execution infrastructure. Commons records can carry artifact, execution, node, environment, and reconciliation references.
- MNEL observations and learned-provider findings are diagnostic evidence, including negative/resource-placement results; Commons does not treat them as verdicts.
- RAVEL can consume a scoped view containing accepted, disputed, negative, and unresolved records, but Commons does not decide what RAVEL learns.
- MNCS/MNCDS contracts and validators retain technical conformance authority; Commons only references contracts and validation results.
- MNCS Language semantic graphs, intent expressions, lowering envelopes, and evidence obligations can be subjects or references without being reimplemented by Commons.
