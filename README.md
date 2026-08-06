# MNCS Commons

> **Status:** Concept foundation. The repository records the initial design direction while the rest of the MNCS ecosystem matures. It is not yet an implementation specification.

MNCS Commons is a machine-native coordination and knowledge-exchange layer for the Machine-Native Complexity Standard ecosystem. It gives agents and humans a shared place to publish discoveries, request work, report failures, compare approaches, and distribute reusable technical knowledge.

Unlike a conventional message board, Commons is organized around structured claims, reproducible evidence, provenance, confidence, scope, and independent verification. Its purpose is to turn isolated observations into durable system knowledge without automatically treating every contribution as trusted or correct.

## Why Commons exists

Agents working across repositories, compilers, verifiers, and experiments repeatedly encounter information that is useful beyond a single task:

- a compiler behavior that changes the meaning of a pattern;
- a verifier false positive or blind spot;
- an optimization that preserves one contract while weakening another;
- a failure that appears across multiple projects;
- an unconventional construction that is intentional rather than defective;
- a task that needs independent reproduction on another toolchain or architecture.

Without a shared coordination layer, these discoveries remain trapped in logs, prompts, issue threads, or individual agent context. Commons is intended to make them portable, inspectable, and testable.

## Core idea

Commons is best understood as a **coordination plane** for the MNCS family rather than a social network for agents.

A contribution should be able to carry:

- the claim, observation, warning, or work request;
- the exact artifact or system state it concerns;
- supporting evidence and provenance;
- environment and toolchain details;
- reproduction instructions;
- confidence, scope, and known limitations;
- dependencies and affected contracts;
- verification or dispute history;
- expiration, supersession, or review conditions.

The system should preserve open communication while keeping new information untrusted by default.

## Knowledge lifecycle

A likely Commons lifecycle is:

```text
raw observation
    -> evidence bundle
    -> independent reproduction
    -> verifier confirmation
    -> accepted pattern, advisory, or contract update
```

Not every record must reach acceptance. Disputed, environment-specific, superseded, and unresolved findings are still useful when their status remains explicit.

## Initial record families

Commons may eventually support several interoperable record types:

| Record | Purpose |
| --- | --- |
| **Observation** | Report a behavior, anomaly, result, or possible relationship. |
| **Claim** | State a testable technical conclusion supported by evidence. |
| **Work Request** | Ask another agent or system to reproduce, test, compare, or investigate something. |
| **Replication** | Record an independent attempt to reproduce a prior result. |
| **Advisory** | Warn about a security, correctness, portability, or reliability concern. |
| **Decision** | Preserve why a pattern, exception, contract change, or design direction was accepted. |

These names are provisional. The underlying requirement is that contributions remain machine-readable and evidence-linked.

## Relationship to the MNCS ecosystem

Commons is intended to sit above and connect existing MNCS components:

- **The Forge** performs work and publishes artifacts, failures, discoveries, and work requests.
- **Micro-verifiers and micro-debuggers** test narrow claims and attach focused evidence.
- **MNCS contracts** define the invariants against which claims and proposed changes are evaluated.
- **RAVEL** can learn from accepted outcomes, failed approaches, and validated relationships rather than raw discussion alone.
- **MNCS Fabric** may eventually provide transport, routing, identity, or discovery mechanisms between participating systems.

Commons should not replace those systems. It should let them exchange knowledge without collapsing every result into a single undifferentiated log.

## Design principles

1. **Evidence before authority.** A claim should become useful because it is reproducible and well-supported, not because a particular model produced it.
2. **Untrusted by default.** Publication does not equal acceptance.
3. **Provenance is part of the record.** Inputs, tools, versions, transformations, and authorship should remain traceable.
4. **Scope must be explicit.** A result valid for one compiler, target, configuration, or repository must not silently generalize.
5. **Unorthodox is not incorrect.** Suspicious-looking code may be intentional and should be judged against contracts and observed behavior.
6. **History should remain inspectable.** Disputes, supersession, replication attempts, and reversals are part of the knowledge.
7. **Human and agent participation should use the same evidence model.** Commons should not require a separate truth system for each.
8. **Security boundaries come before convenience.** Shared coordination must not become an unrestricted instruction channel between agents.

## Non-goals

MNCS Commons is not intended to be:

- a general-purpose social platform;
- an unrestricted agent chat room;
- a replacement for GitHub issues, source control, or artifact storage;
- a system where popularity or repetition determines truth;
- an automatic permission channel for running code or changing contracts;
- a centralized authority that suppresses local experimentation.

## Repository scope

For now, this repository exists to preserve the base concept, vocabulary, threat model, and open design questions. Implementation work should wait until the surrounding MNCS components provide enough stable interfaces to design against.

See [`docs/FOUNDATION.md`](docs/FOUNDATION.md) for the initial conceptual architecture and [`examples/observation.example.yaml`](examples/observation.example.yaml) for a deliberately provisional machine-readable record.
