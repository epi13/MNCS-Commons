# Durable work records

The local service provides a small append-only work-memory protocol. It records
requests and execution-component assertions; it is not a scheduler, command
channel, permission grant, or proof that an assertion is true.

Only the operator socket can append work state:

- `work.submit` persists a `submitted` WorkRequest and returns its `workId` and
  content digest. `executionAccepted` is explicitly false.
- `work.transition` appends the next immutable revision. The caller must supply
  the current `expectedPreviousDigest`, an actor identity, and an allowed next
  state. Stale writers fail with `WORK_CONFLICT`.

The consumer socket exposes `work.status` and `work.list`. Status returns the
current record plus every digest-linked state event. The supported states are:

```text
submitted -> accepted -> assigned/queued -> running
running -> checkpointed/blocked/retrying -> running
running/checkpointed -> completed/failed/cancelled
```

Additional fail-closed transitions exist for queue, blocker, retry, failure, and
cancellation handling. Terminal states cannot be reopened. `blocked` requires a
blocker list; `completed` and `failed` require `result.terminalOutcome`.

A submission request carries the submitting consumer, project, optional
repository and parent work identity, task, constraints, optional Fabric job,
worker/model routing, and attempt. Later revisions may add progress, blockers,
routing observations, and result/artifact/evidence references.

New submissions may also declare one of the six coordination lanes
(`DOCUMENTATION`, `CONVERSION_PREP`, `VERIFICATION`, `REPO_LOCAL`, `REPO_HYGIENE`, or `SHARED_CORE`), affected
repositories, priority, capability requirements, dependencies, shared-core impact, allowed and
forbidden write scopes, and source work/evidence identities. Lane-aware records expose a
coordination state (`AVAILABLE`, `CLAIMED`, `IN_PROGRESS`, `BLOCKED`, `VERIFYING`, `COMPLETE`,
`ABANDONED`, `SUPERSEDED`, or `NEEDS_RECONCILIATION`) while retaining the existing execution state
for compatibility. `work.next` selects only dependency-ready `AVAILABLE` tasks; `work.claim`
appends an optimistic claim revision and rejects stale or already-owned work. See
[`PARALLEL_WORK.md`](PARALLEL_WORK.md) for the worker workflow and authority policy.

Workers publish discoveries through `work.propose`, not `work.submit`. Commons classifies the
proposal's lane, repository, evidence, and overlap dimensions before making it `AVAILABLE`.
Incomplete proposals and plausible capability overlaps remain `NEEDS_RECONCILIATION`; exact
capability or finding duplicates attach their consumer, evidence, and dependency pressure to the
existing open request. `family.health-sweep` accepts bounded observations from an independently
authorized scanner and records fresh `REPO_HYGIENE` opportunities. It does not crawl repositories,
execute checks, or grant write authority.

All work content remains `UNTRUSTED`, has `executionAuthority: none`, and keeps
`security.instructionsAreUntrusted: true`. An independently authorized Fabric,
Harness, or worker component must explicitly accept and execute work; Commons
itself never executes record content.
