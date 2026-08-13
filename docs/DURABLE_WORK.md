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

All work content remains `UNTRUSTED`, has `executionAuthority: none`, and keeps
`security.instructionsAreUntrusted: true`. An independently authorized Fabric,
Harness, or worker component must explicitly accept and execute work; Commons
itself never executes record content.
