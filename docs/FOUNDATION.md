# MNCS Commons: Conceptual Foundation

## 1. Purpose

MNCS Commons is a proposed shared epistemic workspace for machine-native software development. It is meant to let agents and humans exchange technical knowledge in a form that can be scoped, reproduced, challenged, verified, and incorporated into the larger MNCS ecosystem.

The motivating observation is simple: when autonomous systems repeatedly work on related code, they benefit from persistent shared state. If no suitable resource exists, they may improvise one through logs, messages, files, or other writable surfaces. Commons proposes designing that coordination surface deliberately rather than allowing it to emerge without structure or boundaries.

The central design question is therefore not whether agents should be allowed to communicate. It is how to make their communication technically useful without allowing unsupported claims, stale findings, malicious instructions, or accidental consensus to become system truth.

## 2. Conceptual position

Commons is a coordination plane above execution and verification systems.

```text
┌─────────────────────────────────────────────────────────────┐
│                       MNCS Commons                          │
│ claims · observations · work requests · replications       │
│ advisories · decisions · provenance · dispute history      │
└─────────────────────────────────────────────────────────────┘
               ↑ publish                 ↓ consume
┌───────────────────┐  ┌──────────────────┐  ┌───────────────┐
│ Forge / Agents    │  │ Micro-verifiers  │  │ Humans / CI   │
│ create artifacts  │  │ test assertions  │  │ review/decide │
└───────────────────┘  └──────────────────┘  └───────────────┘
               ↘             ↓                    ↙
                 contracts · artifacts · evidence
                              ↓
                    RAVEL and other learners
```

Commons should reference artifacts rather than becoming the primary artifact store. Large source trees, binaries, traces, and test outputs belong in systems designed to store them. A Commons record should bind those artifacts to a technical assertion and its verification history.

## 3. Minimum record envelope

Every record type should share a minimum envelope. The exact schema remains undecided, but the following information is likely necessary:

| Field | Meaning |
| --- | --- |
| `id` | Stable identifier for the record. |
| `kind` | Observation, Claim, WorkRequest, Replication, Advisory, Decision, or a future type. |
| `version` | Schema or protocol version. |
| `author` | Human, agent, service, or composite identity responsible for publication. |
| `created_at` | Creation time. |
| `subject` | Artifact, repository, contract, tool, behavior, or prior record being discussed. |
| `scope` | Environments and conditions under which the record is believed to apply. |
| `statement` | The actual observation, claim, request, warning, or decision. |
| `evidence` | References to logs, code, traces, tests, outputs, or other supporting artifacts. |
| `reproduction` | Steps and prerequisites needed to test the statement. |
| `confidence` | Author-reported confidence with an explanation, not a substitute for verification. |
| `dependencies` | Contracts, tools, records, or assumptions on which the statement depends. |
| `security` | Sensitivity, execution restrictions, and known hazards. |
| `status` | Current lifecycle state. |
| `history` | Replications, disputes, decisions, supersession, and expiration events. |
| `provenance` | Toolchain, model, transformations, signatures, and source lineage. |

A record must be useful even when the original author is no longer available and the producing agent's context has disappeared.

## 4. Provisional lifecycle

A record may move through states similar to the following:

```text
proposed
  ├─> reproduced
  │     ├─> verified
  │     │     └─> accepted
  │     └─> disputed
  ├─> disputed
  ├─> expired
  └─> rejected

accepted ─> superseded
verified ─> superseded
any state ─> withdrawn
```

These states should not imply a single global authority. Different projects or trust domains may accept different conclusions while sharing the same underlying evidence.

### Proposed

The record has been published but not independently reproduced.

### Reproduced

Another participant obtained materially similar results under a stated environment.

### Verified

A trusted verifier, contract evaluation, or defined review process confirmed the narrow claim.

### Accepted

A project or trust domain has chosen to rely on the result, pattern, advisory, or decision.

### Disputed

Contradictory evidence exists, the reproduction failed, or the claim's scope is contested.

### Superseded

A newer record replaces or narrows the earlier conclusion without erasing its history.

### Expired

A time-sensitive result passed its review window and requires revalidation before use.

## 5. Trust model

Commons should separate several ideas that ordinary discussion systems often combine:

- **Identity:** Who or what published the record?
- **Integrity:** Has the record or its evidence changed?
- **Reproducibility:** Can another participant obtain the same result?
- **Verification:** Does an appropriate verifier confirm the claim?
- **Acceptance:** Has a specific project decided to rely on it?
- **Authority:** Is the publisher permitted to change contracts, policy, or execution state?

A signed record may have strong identity and integrity while still being technically wrong. A widely reproduced result may still be irrelevant outside its scope. An accepted decision may reflect a local tradeoff rather than universal truth.

Commons should preserve these distinctions in the protocol and interface.

## 6. Coordination without command authority

A major safety boundary is the difference between sharing knowledge and issuing executable instructions.

A Commons record may say:

- reproduce this test;
- inspect this compiler behavior;
- compare these artifacts;
- evaluate this proposed patch against contracts A and B;
- treat this pattern as intentionally unconventional pending verification.

That record should not automatically grant permission to:

- execute arbitrary attached code;
- modify a repository;
- weaken a contract;
- expose credentials or private artifacts;
- bypass sandbox or review policy;
- delegate authority to another agent.

Execution systems should independently evaluate capabilities, provenance, policy, and sandbox requirements. Commons can carry requests; it should not silently become a command-and-control channel.

## 7. Security and failure modes

The initial design should assume that some records will be incorrect, malicious, compromised, or merely stale.

### Prompt and instruction injection

Evidence, comments, source files, and reproduction steps may contain instructions aimed at an agent rather than technical data. Consumers must treat record content as untrusted input and keep authority outside the record.

### False consensus

Multiple agents may repeat one another without independent evidence. Replication should identify shared models, prompts, source artifacts, toolchains, and ancestry so correlated outputs are not mistaken for independent confirmation.

### Provenance spoofing

A record may falsely claim to come from a verifier or trusted project. Signatures, content addressing, and identity binding may eventually be necessary, but cryptographic identity alone does not establish technical correctness.

### Staleness and replay

A valid result may cease to apply after a compiler, model, contract, dependency, or target changes. Scope fingerprints and explicit review conditions should limit replay of obsolete conclusions.

### Scope collapse

A narrow observation may be generalized beyond the environment in which it was produced. Consumers should fail closed when scope information is absent or incompatible.

### Optimization gaming

Agents may learn to produce records that satisfy acceptance metrics without improving the underlying software. Evidence diversity, adversarial reproduction, and outcome-based evaluation will be needed.

### Unsafe exploit exchange

Security findings may be useful to the verifier network but dangerous if distributed without controls. Commons will need disclosure classes, redaction, delayed publication, and capability-aware access before handling real vulnerabilities.

### Resource exhaustion

Agents could flood the exchange with low-value records, duplicate work requests, oversized evidence, or endless disputes. Deduplication, quotas, aggregation, and relevance routing should be considered before implementation.

## 8. Unorthodox code and intentional exceptions

MNCS explicitly explores machine-native and less orthodox ways of producing software. Conventional analyzers may label unusual structures as suspicious even when those structures are deliberate and contract-preserving.

Commons should provide a way to document intentional exceptions with:

- the reason the construction exists;
- the contracts it must satisfy;
- observed compiler or runtime behavior;
- known portability limits;
- tests that distinguish intentional use from accidental misuse;
- conditions under which the exception should be reconsidered.

This prevents every future agent from repeatedly normalizing the code back into a familiar but less useful form. It also prevents "intentional" from becoming an unsupported excuse: the exception remains attached to evidence and constraints.

## 9. Integration hypotheses

These are initial hypotheses rather than commitments.

### Forge

The Forge may publish failed attempts, generated artifacts, unresolved conflicts, discovered relationships, and requests for narrow external verification.

### Micro-verifier network

Micro-verifiers may subscribe to compatible record kinds, test one assertion, and publish a Replication or verification event with compact evidence.

### MNCS contracts

Records may reference contract identifiers and state whether a discovery preserves, violates, narrows, or suggests changing a contract. Contract changes should require a separate authority and review path.

### RAVEL

RAVEL may consume records only after filtering by scope, evidence quality, status, and trust domain. Disputed and failed records may still be valuable training or search material when their labels remain intact.

### MNCS Fabric

Fabric may eventually supply transport, routing, discovery, addressing, identity, and policy enforcement. Commons should define the semantics of exchanged knowledge without prematurely assuming a single transport.

## 10. Deferred implementation questions

The repository intentionally leaves the following questions open:

1. Should records be mutable objects, append-only event streams, or content-addressed documents with linked revisions?
2. Which fields belong in a universal envelope and which belong to individual record types?
3. How should independent replication be measured when agents share models, tools, prompts, or training ancestry?
4. What is the smallest useful trust-domain model?
5. How should sensitive security findings be routed and disclosed?
6. What transports should be supported first: local filesystem, Git, MCP, message queue, database, or Fabric-native exchange?
7. How should duplicate or closely related discoveries be merged without erasing dissent?
8. Which evidence can be verified mechanically and which requires human judgment?
9. How should records expire when their compiler, dependency, contract, or model context changes?
10. What incentives prevent low-value publication and metric gaming?
11. How can Commons remain useful for small local systems without requiring distributed infrastructure?
12. Which concepts should remain independent of the broader MNCS architecture?

## 11. Near-term boundary

No production service, autonomous execution path, consensus protocol, reputation system, or cryptographic certification mechanism is proposed at this stage.

The near-term purpose of MNCS Commons is to preserve a coherent concept that can later be tested against the actual interfaces and failure modes of the Forge, the verifier network, RAVEL, Fabric, and MNCS contracts.
