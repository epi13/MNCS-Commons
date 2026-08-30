# Low-conflict parallel work

Commons is the coordination and work-request plane for the MNCS family. It records durable,
inert work state and evidence; it does not execute records, authenticate workers, route models,
or grant repository permissions.

## Concurrent lanes and shared core

| Lane | Safe scope | Purpose |
| --- | --- | --- |
| `DOCUMENTATION` | Assigned repository documentation and examples | README, architecture, ADR/RFC, roadmap, Atlas/descriptive synchronization |
| `CONVERSION_PREP` | Assigned repository | Conversion maps, `.mncs` scaffolds, corpora, fixtures, and repo-local conversions already supported by the language |
| `VERIFICATION` | Assigned repository tests, fixtures, CI, and evidence | Regression, compatibility, diagnostics, reproducibility, and maintenance |
| `REPO_LOCAL` | Assigned repository | Substantive consumer implementation using existing MNCS capabilities |
| `REPO_HYGIENE` | Assigned repository health and CI surfaces | Repair red CI, stale pins, generated-file drift, warnings, skipped tests, and environment assumptions without changing intended semantics |
| `SHARED_CORE` | Explicitly authorized shared-core scope | Language/compiler/stdlib, Commons protocol, Fabric contracts, Harness policy, and family-wide semantic contracts; single writer by default |

The five safe lanes (`DOCUMENTATION`, `CONVERSION_PREP`, `VERIFICATION`, `REPO_LOCAL`,
`REPO_HYGIENE`) may run concurrently within an assigned repository without modifying shared
semantic infrastructure; `SHARED_CORE` is the sixth, exclusive single-writer lane for
language/compiler/stdlib, Commons protocol, Fabric contracts, Harness policy, and family-wide
semantic schemas. This 5+1 structure is referred to as the five-lane safe model with an
exclusive shared-core escalation lane.

The machine-readable policy is available from `mncs-commons work policy` and can assess a path
with `mncs-commons work scope-check`. A safe lane may inspect the family and publish observations,
findings, work requests, blockers, and handoffs, but must not modify shared semantic
infrastructure. A policy result is a deterministic coordination check, not a replacement for
repository or Harness authorization.

## Work lifecycle

Lane-aware durable work records retain the existing execution `state` and add a coordination
projection:

```text
AVAILABLE -> CLAIMED -> IN_PROGRESS -> VERIFYING -> COMPLETE
                 |          |             |
                 +---------> BLOCKED <-----+

AVAILABLE/CLAIMED/IN_PROGRESS/BLOCKED/VERIFYING -> NEEDS_RECONCILIATION
AVAILABLE/CLAIMED/IN_PROGRESS/BLOCKED/NEEDS_RECONCILIATION -> ABANDONED
AVAILABLE/CLAIMED -> SUPERSEDED
```

Every revision carries the current digest as `expectedPreviousDigest`. A claim therefore loses
deterministically when another writer has already claimed the task. By default, a worker may own
one active substantive claim (`CLAIMED`, `IN_PROGRESS`, or `VERIFYING`). Blocked work names its
blockers. Complete work carries `result.terminalOutcome`, non-empty `result.evidence`, and should
include artifact, commit, or PR references where applicable.

Coordination states and their execution `state` mapping:

- `AVAILABLE` (`submitted`/`accepted`) — dependency-ready, claimable.
- `CLAIMED` (`assigned`/`queued`) — exclusively owned after optimistic claim.
- `IN_PROGRESS` (`running`) — active work inside the lane's allowed scope.
- `VERIFYING` (`checkpointed`) — local verification before declaring completion.
- `BLOCKED` (`blocked`) — waiting on an explicit blocker, often a missing shared-core capability.
- `COMPLETE` (`completed`) — verified completion with evidence.
- `ABANDONED`/`SUPERSEDED`/`NEEDS_RECONCILIATION` — terminal or reconciliation states for withdrawn, superseded, or incompletely classified work.

Transitions are validated optimistically against `expectedPreviousDigest`; stale writers receive
`WORK_CONFLICT`. See `src/mncs_commons/work.py:85` for the exact `WORK_COORDINATION_STATES` and
`src/mncs_commons/work.py:99` for allowed transitions.

## Worker bootstrap

An operator starts the service and seeds a small real backlog:

```bash
mncs-commons store init /var/lib/mncs-commons
mncs-commons store seed-work /var/lib/mncs-commons
mncs-commons-service --store /var/lib/mncs-commons \
  --socket /run/user/$UID/mncs-commons.sock \
  --operator-socket /run/user/$UID/mncs-commons-operator.sock run
```

The equivalent worker loop is:

```text
read policy and family context
work next --lane <lane> (include required capabilities)
claim the returned workId with its currentDigest and worker/session identity
inspect related work, decisions, findings, and capability requests
work only inside the recorded allowed scope
if a shared capability is missing: publish a SHARED_CORE WorkRequest, mark this work BLOCKED,
and attach the fixture/corpus/source evidence
verify and publish completion evidence, blockers, discoveries, and follow-on work
select another task only after COMPLETE, BLOCKED, ABANDONED, or explicit relinquishment
```

The standalone CLI makes the common actions explicit:

```bash
mncs-commons work next /var/lib/mncs-commons --lane CONVERSION_PREP \
  --repository mncs-tui --capability mncs-language:source-fixtures
mncs-commons work claim /var/lib/mncs-commons work:... \
  --actor-id worker:tui-1 --session-id session:2026-08-27
mncs-commons work block /var/lib/mncs-commons work:... \
  --actor-id worker:tui-1 --reason 'missing capability: bounded.text.traversal'
mncs-commons work complete /var/lib/mncs-commons work:... \
  --actor-id worker:tui-1 --result completion.json
```

Service clients use the read-only `work.next`, `work.policy`, and `work.scope-check` operations;
`work.claim` and state revisions remain on the operator write surface. Commons records the claim
and provenance; Fabric continues to own enrolled worker identity/presence, transport, bounded
execution, and execution evidence. Harness continues to own model/tool routing, permissions,
governance, and acceptance/escalation. Forge evaluates workflows and evidence. Git remains source
control.

## Proposal and health intake

Worker discoveries, verification failures, conversion blockers, follow-on work, and health findings
enter through `work.propose`. The proposal is classified against its lane, repository, scope,
dependencies, evidence, and shared-core impact before it can become `AVAILABLE`. Missing
classification or plausible-but-unproven capability overlap remains `NEEDS_RECONCILIATION` and is
not claimable. Exact capability or finding duplicates attach consumer/evidence/dependency pressure
to the existing open request.

The bounded `family.health-sweep` operation accepts observations from an independently authorized
janitor or scanner. It records `PASS`, `FAIL`, or `UNKNOWN` with an observation timestamp and
source identity, creates fresh `REPO_HYGIENE` proposals for failures, and supersedes available
hygiene work when a newer matching observation is `PASS`. It does not crawl repositories or execute
checks inside Commons. Unavailable current health remains `UNKNOWN`/`NEEDS_REVIEW`; historical run
IDs are evidence references only.

`work.next` ranks by priority, dependency-unblocking value, a small quiet-project coverage boost,
then creation time and `workId`. Explicit high-priority work still wins; the coverage signal only
prevents long-neglected eligible projects from disappearing behind a continuously hot repository.

## Four concurrent workers

An operator can give four workers the same bootstrap prompt while assigning distinct lanes:

| Worker | Lane | Example first task |
| --- | --- | --- |
| A | `DOCUMENTATION` | Update Commons lane and authority-boundary documentation |
| B | `CONVERSION_PREP` | Prepare the `mncs-tui` geometry conversion map and fixtures |
| C | `VERIFICATION` | Run the `mncs-lineage` sealed corpus and publish reproducibility evidence |
| D | `REPO_LOCAL` | Improve the MNEL differential-run reporting inside MNEL only |

Each worker claims before substantive edits, so two workers do not silently interpret the same
MNCS concept in incompatible ways.

### Shared-core escalation (safe lane → SHARED_CORE)

A safe-lane worker must not independently implement a missing shared capability. The bounded
escalation is:

1. **Search** Commons for an existing `SHARED_CORE` request with `capability_overlap == "exact"` for
   the required capability (e.g., `bounded.text.traversal`). Use `mncs-commons work next
   --lane SHARED_CORE` and capability filtering.
2. **Attach** pressure/evidence — if found, add consumer, fixture/corpus/source evidence, and
   dependency links via `work.propose` attachment rather than duplicating the request.
3. **Propose** — if not found, submit a new bounded `SHARED_CORE` WorkRequest containing
   `capability`, `consumer` (requesting workId/repository), `expectedSemantics`, blocker/work
   identity, and fixture or corpus references. The proposal is classified; plausible-but-unproven
   overlap becomes `NEEDS_RECONCILIATION`, not `AVAILABLE`.
4. **Block** — mark the consumer work `BLOCKED` with explicit `blockers` and `blockingWorkIds`
   referencing the `SHARED_CORE` request, attach the evidence, and continue another eligible safe-lane
   task. Only the explicitly assigned single-writer shared-core worker changes the language or
   shared semantic contract, and `mncs-commons work claim --lane SHARED_CORE` enforces the
   single-writer invariant.

Example: if B discovers that the language lacks a required traversal or reduction, B searches
Commons for an existing request, adds its evidence if present, or submits a structured
`SHARED_CORE` request containing `capability`, `consumer`, expected semantics, blocker/work
identity, and fixture or corpus references. B then marks its task `BLOCKED` and can continue
another eligible safe-lane task. Only the explicitly assigned shared-core worker changes the
language or shared semantic contract.

## Seeding and escalation

`mncs-commons store seed-work` is idempotent by stable `workId` and seeds a deliberately small
backlog across the six concurrent lanes from current MNCS repositories. Operators may submit additional
records with `work.submit` or `CommonsApplication.submit_work`, including `affectedRepositories`,
`dependencies`, `capabilityRequirements`, `sharedCoreImpact`, `allowedWriteScope`,
`forbiddenWriteScope`, `createdFrom`, and priority. A safe-lane worker should not implement a
missing shared capability merely because its consumer task is blocked: the structured request is
the handoff that turns application pressure into exclusive shared-core input.

## Family registry and coverage

Commons owns the active coordination registry at `commons.mncs.dev/family-registry/v0alpha1`.
It covers the canonical 17 repositories, records their groups, authority classes, eligible lanes,
and known consumers, and keeps explicit coverage posture for projects with no current task. Atlas
remains the descriptive orientation source and is never a scheduling authority.

```bash
mncs-commons family registry
mncs-commons family coverage /var/lib/mncs-commons
```

Coverage is a bounded projection over the registry and latest WorkRequest revisions. It reports
`ACTIVE_WORK`, `HEALTHY_NO_WORK`, `BLOCKED`, `WAITING_SHARED_CORE`, `INTENTIONALLY_INACTIVE`, or
`NEEDS_REVIEW`; it does not manufacture work to make counts look complete.

The registry validates the exact canonical component identities and repository paths, not only a
count. `family.consistency` can compare Standard and Atlas snapshots while resolving explicit
source aliases such as `mncs-forge`/`mncs-forge-mcp`/`forge` and
`mncs-control`/`mncs-control-mcp`/`control`. Standard remains discovery authority, Commons owns
coordination, and Atlas remains orientation-only.

## REPO_HYGIENE rules

The janitor may repair CI and environment debt, but must preserve intended behavior. It must not
delete meaningful tests, weaken assertions, turn `FAIL` into `PASS`, add broad skips, hide warnings,
remove platform coverage without evidence, or redesign shared semantics. When a red check requires
a semantic decision, it publishes a structured shared-core blocker and moves on.
