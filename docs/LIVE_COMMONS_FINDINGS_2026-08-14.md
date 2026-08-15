# Live Commons findings — 2026-08-14

This document records an operator inspection of the persistent controller-local Commons service on
2026-08-14. It is a point-in-time diagnostic snapshot, not a protocol guarantee.

## Observed state

- The live service reported healthy local persistent storage and **110 records**.
- **105 records were `Observation` records** produced from Fabric execution records.
- **5 records were revisions of one logical durable `WorkRequest`**, progressing from submitted to
  accepted, queued, running, and completed.
- All 105 Fabric execution observations reported source outcome `PASS`.
- The execution observations were distributed across `fabric-worker` (72), `fabric-worker-01` (19),
  and `worker-01-windows` (14).
- The Linux worker evidence included `granite3.3:2b`; the Windows worker evidence included
  `gemma4:e4b`. Many controller/local records were integration exercises rather than reusable
  project knowledge.
- The store had no promoted Findings and no project Decisions from this workload. Model text existed
  inside captured execution stdout, but the observations had no conversational relationships.
- The durable-work test successfully demonstrated that detached Fabric work remained observable from
  a fresh client after the submitter disconnected.

## Problem established by the snapshot

Commons was successfully preserving execution provenance, but the valuable semantic output of agents
was mostly trapped inside raw stdout/evidence. At projected sustained compute volumes this would
produce a very large, auditable execution trove without a correspondingly useful shared project
memory.

The correct response is not to preserve every model turn as chat. It is to add an explicit promotion
protocol so agents extract reusable Findings, Questions, Hypotheses, FailedApproaches, Handoffs,
ArtifactReferences, Decisions, and typed Thread relationships from execution evidence.

## Open-work defect observed

The generic opportunities projection returned historical nonterminal revisions of the completed
WorkRequest (`submitted`, `accepted`, `queued`, `running`) as apparent opportunities. The durable
work-status projection correctly understood the logical work item as completed.

Open-work queries therefore need to collapse revisioned WorkRequests by stable record/work identity
and evaluate only the latest revision. Historical revisions remain in the immutable ledger for audit,
but must not be presented as current opportunities.

## Architectural conclusion

Execution receipts are evidence; they are not institutional memory by default. Commons should retain
raw evidence while exposing a sparse promoted-memory layer designed for cross-agent continuity. See
`INSTITUTIONAL_MEMORY.md` and ADR 0013.
