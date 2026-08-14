# Institutional memory

Commons is the shared institutional memory of MNCS, not a transcript archive. Fabric, harnesses,
models, verifiers, and tools may generate large volumes of execution receipts and stdout. Those
records are evidence. They become institutional memory only when a participant explicitly promotes
reusable knowledge into a typed Commons record.

The promotion boundary is intentional:

```text
execution / stdout / receipt
          |
          | evidence + provenance
          v
     Observation
          |
          | deliberate promotion
          v
Finding / Question / Hypothesis / FailedApproach / Handoff
Decision / ArtifactReference / Thread
```

A model response is therefore not durable knowledge merely because it exists in stdout. Promotion
requires a bounded subject, scope, provenance, confidence, evidence/relationships when available,
and an explicit semantic record kind.

## Institutional-memory kinds

| Kind | Publish when | Required memory payload | Typical relationships |
| --- | --- | --- | --- |
| `Finding` | Work produced a reusable conclusion that should survive the run. | `basis`, `significance` | `derived_from`, `supports`, `contradicts`, `contributes_to` |
| `Decision` | An authorized project/domain choice needs its rationale preserved. | existing `domain`, `rationale`, `authorityScope` | `responds_to`, `supersedes`, `contributes_to` |
| `Question` | A concrete unresolved uncertainty can affect later work. | `question`, `answerCriteria` | `requests`, `follows_up`, `contributes_to` |
| `Hypothesis` | There is a testable explanation worth carrying forward. | `hypothesis`, `falsifier` | `explores`, `derived_from`, `contributes_to` |
| `FailedApproach` | An attempted path failed in a way future agents could repeat. | `approach`, `failureMode`, `lesson` | `attempts`, `derived_from`, `contributes_to` |
| `Handoff` | Work is intentionally being continued by another agent/session/node. | `objective`, `continuation`, `authorityBoundary` | `hands_off`, `responds_to`, `contributes_to` |
| `ArtifactReference` | A durable artifact identity must remain discoverable without embedding the artifact. | `artifactIdentity`, `artifactType` | `references_artifact`, `derived_from`, `contributes_to` |
| `Thread` | Several memory records need one durable topic/context anchor. | `topic`, `status` | receives `contributes_to`; may `supersede` another thread |

`Decision` remains the existing authority-scoped decision record. `Thread` is not a chat message and
does not grant command authority. It is a graph anchor whose allowed status is `open`, `resolved`,
`superseded`, or `archived`.

## Agent publication contract

An agent should publish institutional memory when at least one of these is true:

1. another agent would otherwise need to rediscover the same fact;
2. the result changes what should be tried next;
3. a failed approach is likely to be repeated without a warning;
4. an unresolved question or hypothesis materially gates future work;
5. a decision or exception needs durable rationale;
6. work is crossing a session, worker, model, or human boundary;
7. an artifact is important enough to be referenced after the producing execution is archived.

Do **not** publish a memory record merely because a run happened, a model emitted text, a test marker
was returned, or a receipt exists. Those remain execution evidence/observations unless they are
useful outside that run.

For every promoted record:

- identify the smallest correct `subject`;
- bind material assumptions in `scope.context` and state limitations;
- preserve producer/source lineage in `provenance`;
- attach evidence identities rather than copying large logs into prose;
- link the record to its thread/work/question/source with typed `relationships`;
- keep `security.instructionsAreUntrusted: true`;
- never use a Commons record as execution authorization;
- prefer one precise memory object over a transcript-sized summary.

If the participant has no publication authority, it should produce the proposed record for an
operator-authorized publisher rather than bypassing the boundary.

## Threads instead of transcript storage

Create a `Thread` when a line of investigation needs continuity beyond one execution or agent.
Participants then publish independent typed records with:

```json
{"type": "contributes_to", "target": "thread:mncs:<topic>"}
```

A question can be answered by a Finding/Decision using `answers`; a hypothesis can be explored by an
Observation/Finding using `explores`; a failed path can name the work/request it `attempts`; and a
handoff can identify the work or prior memory object it `hands_off` or `responds_to`.

Use `commons_conversation` on the Thread record/digest to reconstruct the bounded typed graph. The
chronological rendering is a presentation; the individual immutable records and edges remain the
canonical information.

## Retrieval

Consumers can ask for only promoted institutional memory with the structured query flag:

```json
{"institutionalMemory": true, "limit": 100}
```

It can be combined with existing `kind`, `subject`, `related`, `domain`, and lifecycle filters. This
keeps raw execution observations out of the normal memory recall path without deleting their
evidence.

## Handoffs and durable work

A `Handoff` is continuity information, not a second work scheduler. When executable work already has
a durable `WorkRequest`, the Handoff should reference that work identity and capture only what the
next participant needs: current objective, completed context, blockers, next bounded action, relevant
memory/evidence identities, and authority boundary. Fabric/controller remains responsible for actual
execution acceptance and dispatch.

Open-work discovery must consider only the latest revision of a revisioned WorkRequest. Historical
`submitted`, `accepted`, `queued`, or `running` revisions must never reappear as current
opportunities after the same work reaches a terminal state.

## Retention

Institutional memory is deliberately sparse and receives stronger retention than execution exhaust.
`Finding`, `Question`, `Hypothesis`, `FailedApproach`, `Handoff`, `Thread`, and `Decision` are
canonical/protected knowledge. `ArtifactReference` is evidence-class and is retained/archive-managed
as evidence. Raw Observations retain the existing diagnostic/ephemeral behavior unless separately
promoted or protected by a canonical record reference.

This is the scaling mechanism: preserve the evidence trail, but make the hot, agent-facing memory a
small set of intentionally promoted knowledge rather than thousands of near-duplicate model turns.
