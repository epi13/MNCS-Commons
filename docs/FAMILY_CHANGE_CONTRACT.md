# Family working-change contract (`mncs.family-change/1`)

The executable law lives in
`src/mncs_commons/mesh/mncs/commons/family/change.mncs`
(`mncs.commons.family.change.v1`). Structural validation and identity
live in `src/mncs_commons/family_change.py`. This document states the
wire, lifecycle, and ownership rules around them.

## Ownership

```text
producer owns its working change and intent
Commons owns this vocabulary and lifecycle law
Environment owns observation, claims, and convergence transport
Doctor consumes changes through mncs.remediation/1
Language Service answers semantic impact, never remediation
```

A family working change is a producer's proposed or established unit
of collaborative work. It is NOT a Record Spine evidence-coordination
ChangeSet; the two link via
`evidence_refs.coordination_changesets`, never by conflation.

## Identity

`fc:<sha256>` over the canonical JSON core: producer (repository,
checkout kind, session, consumer, claim), base head, subjects,
contracts changed, operations, evidence refs, verification,
intent summary and migration id, and the breaking / semantic-choice
flags. Lifecycle state is outside the core: state advances, identity
never changes.

## Record shape

Required: `schema_version` (`mncs.family-change/1`), `identity`,
`producer`, `base` (head, generation), `state`, `subjects`, plus the
optional `contracts_changed`, `operations`, `evidence_refs`,
`verification`, `intent`, `supersedes`, `breaking`, `semantic_choice`
fields validated by `validate_family_change`. Contributors validate
under `validate_contributor`; reconciliation rows under
`validate_reconciliation`; generation cursors under
`validate_family_generation`.

## Lifecycle

Native `lifecycle_legal` judges every transition; host code never
invents one:

```text
draft -> observed -> validated -> established -> published
draft -> abandoned            established -> superseded
any   -> invalid (explicit)
```

Drafts are visible but never authoritative. Only `established`
changes converge consumers. `published` is explicit Git-side delivery,
outside ambient repair.

## Native decision functions

All take small integer fact vectors over the `mncs call` boundary
(`u64`/`i64` only; finite-enum equality is expressed through code
functions, never `==` on variants):

- `lifecycle_legal` — transition admission
- `classify_consumers` — one ordered bounded request for up to 32 consumer fact vectors
- `classify_consumer` — current / reconcilable / occupied / blocked /
  pending_verification / semantic_required / incompatible / unknown
- `gate_repair` — repair / defer / escalate
- `adopt_convergence` — legacy five-fact verified-generation admission
- `adopt_post_repair` — additionally require renewed owning proof after repair
- `transform_admit` — deterministic operation admission
- `revisit_due` — backoff expiry for deferred work
- `contributor_live` — presence liveness

Without a working toolchain the policy answer is always unknown /
defer, never optimistic repair.

## Reconciliation rows

Environment now addresses reconciliation rows as
`family:recon/<change>/<consumer>/wc:<checkout-address-digest>`. The checkout
suffix is local physical addressing inside the selected Store namespace, not
semantic/evidence equivalence across machines. Observers of the same checkout
share adoption; different worktrees establish independent adoption. Legacy
repository-only rows remain durable but cannot authorize checkout adoption.

Rows carry the consumer class,
observed and canonical generations, repair state (`no_repair`,
`applied_unknown`, `applied_pass`, `applied_fail`), attempts, and
detail. Writers use compare-and-swap; races observe the winner.
`applied_unknown` adopts only on PASS verdicts for every owning obligation.
New repairs record each obligation's pre-effect evidence digest. Every owning
proof must change before `adopt_post_repair` admits adoption; old PASS/FAIL and
partially renewed evidence remain pending. Row timestamps do not count as proof.
Historical pending rows without the marker require explicit revalidation rather
than optimistic adoption. This is a conservative local freshness gate; it does
not establish cross-session semantic/evidence equivalence.

The row payload and native consumer law remain v1; Environment owns physical
row routing, not new lifecycle or consumer-class policy.

## Compatibility

v1 is fixed. New operations, classes, or lifecycle states extend
through Commons with versioned vocabulary, never by bilateral
extension in a consumer.
