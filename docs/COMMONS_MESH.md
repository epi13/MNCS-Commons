# Commons Mesh

Status: implemented (mesh `v0alpha1`) alongside the controller-local record
protocol (`commons.mncs.dev/v0alpha1`, unchanged wire format).

The architectural invariant:

> There is no global Commons database. There is a globally interoperable
> graph of content-addressed machine knowledge, held and evaluated
> independently by participating systems.

Commons is something an MNCS system **speaks**, not a server every MNCS
system must join.

```text
Each MNCS participant
        |
        v
+----------------------+
| LOCAL COMMONS NODE   |
|                      |
| local records        |
| local evidence (CAS) |
| local projections    |
| local retention      |
| local trust view     |
+----------+-----------+
           |
           | Commons Exchange (mesh v0alpha1)
           | immutable records / identities / graph edges
           |
     +-----+---------------------+
     |                           |
     v                           v
direct peers                optional relays
(bundle-file,                    |
 direct-peer)                    v
                           optional views /
                             indexes
```

## What a node owns

`mncs_commons.mesh.CommonsNode` wraps the existing content-addressed store
and adds:

- **possession frontier** — the set of immutable record/event identities
  held locally (`frontier()`); the sync unit is identities, never tables;
- **origin ledger** — `local` vs `foreign:<source>` per digest, persisted in
  `mesh-state.json`; a node receiving a record learns the record exists,
  nothing more;
- **peer cursors** — last-noted remote frontiers (`note_peer_frontier`);
- **local CAS** — content-addressed evidence blobs (`cas_put/get/has`);
  knowledge identity is tracked independently of evidence possession;
- **policy budgets** — `MeshPolicy` (record bytes, sync bounds, CAS blob
  cap, relationship/evidence caps, hot-byte and foreign-evidence budgets).

The node is authoritative only for its own possession and observations.

## The separation that must never collapse

```text
record identity != record possession != record delivery
    != transport authentication != producer identity
    != technical correctness != independent verification
    != MNCS conformance != MNCS promotion != governance acceptance
```

Ingest (`ingest_foreign`, `receive_records`) validates and stores; it never
creates lifecycle events, never changes acceptance, and never executes
content. Delivery is not correctness, here enforced in code and asserted in
`tests/test_mesh_node.py` (scenario A) and `tests/test_mesh_rights.py`.

## No global ordering

There is no `GLOBAL_SEQUENCE_NUMBER`. Local ledger sequences stay
node-local cursors. Two nodes operate offline, produce records
independently, reconnect, and reconcile by frontier set difference
(`missing_against`), with per-recipient interest filtering. Scenario C
(`test_scenario_c_offline_work_converges_without_ordering`) proves
convergence without arbitration.

Convergence invariant (tested):

> Given two nodes with compatible policies, continued opportunity to
> exchange, and no permanent withholding of records matching the
> recipient's requested projection, both nodes eventually possess the same
> set of relevant immutable record identities.

Local trust, acceptance, retention, derived views, and evidence possession
may legitimately remain different afterwards.

## Exchange knowledge, not execution exhaust

`InterestFilter` (`mesh/interest.py`) is the deterministic subscription:
kinds, projects (`scope.context.project/repository`), contracts,
producers, outcomes, lifecycle states, relationship types, labels, open-work
flag, promotion-relevance flag, plus an explicit digest allowlist
(`recordIds`, OR-clause so wanted identities always resolve).

The host projects open vocabulary to closed discriminants; the MNCS kernel
`mncs/commons/mesh/interest.mncs` owns the Boolean combination law, and
`matches` is defined through its pinned Python transcription
(`mirror_matches_full` over `project_full_args`), so the fast path cannot
evolve independently of the kernel. Mixed-evidence records project to the
strongest asserted outcome (PASS > FAIL > UNKNOWN) on both paths so they
can never disagree.

## Lazy evidence

References move eagerly, evidence moves lazily. `EvidenceReference`
(`mesh/availability.py`) carries digest, media type, byte size, provenance,
and an explicit availability drawn from a bounded vocabulary:

```text
UNAVAILABLE < SOURCE_AVAILABLE < LOCAL < MIRRORED < DURABLE < CANONICAL
```

(ranks are retention priority; `merge_availability` keeps the stronger
tier). Records may annotate `evidence[]` entries with the inert keys
`availability` / `sizeBytes` / `mediaType`, which older readers ignore.
Scenario E proves a claim propagates while multi-megabyte evidence stays
source-local; scenario F proves the record stays auditable when evidence
is `UNAVAILABLE`. Availability is never confused with validity.

## Knowledge capsules

`compose_capsule` projects a record plus local knowledge (lifecycle views,
availability map, producer) into one bounded envelope answering nine
triage questions deterministically (`assess_capsule`): understood,
already-have, relevant, structure-valid, provenance-asserted,
evidence-possessed, evidence-locations, reproducible (recipe presence only
— procedure commands are never copied), retain-candidate. No LLM required.
A capsule is a composition around the canonical record, not a new record
type. The golden capsule fixture (`tests/fixtures/mesh_capsule_golden.json`,
digest pinned in `test_mesh_interop.py`) freezes canonical stability.

## Transports and Fabric

`mesh/transport.py` defines the `Carrier` interface; sync
(`synchronize`) runs the same frontier-diff protocol over:

- `DirectCarrier` — in-process / local-IPC model;
- `BundleCarrier` — offline bundle/file transfer (air-gap; reuses the
  deterministic bundle format, depth-0 selective export);
- `RelayCarrier` — optional relay-assisted;
- `FabricCarrier` — optional; raises bounded `TRANSPORT_UNAVAILABLE`
  without a Fabric runtime and never binds implicitly.

Transport mechanics never redefine record semantics. Fabric may carry
authenticated transport, enrollment, reachability, framing, replay
protection, routing, and bounded transport; it never decides correctness,
acceptance, independence, conformance, or promotion. That boundary is
asserted by `test_fabric_is_optional_not_required`, which syncs with the
Fabric module forcibly blocked.

## Relays and views

`CommonsRelay` (`mesh/relay.py`) is bounded reference infrastructure with
zero authority: node descriptors, compact canonical records (256 KiB cap),
capsules, availability locations, frontier info. It refuses lifecycle
events (`RELAY_NO_AUTHORITY`) and oversize records. Multiple and partial
relays are normal; relay loss destroys nothing (scenario G).

`build_view` (`mesh/view.py`) derives disposable projections —
`open-work`, `verification-status`, `topic-index`,
`promotion-candidates` — from already-possessed records. Views name their
inputs, own nothing, and grant no promotion.

## Storage economics

`mesh/budgets.py` measures (`account_node`) and gates (`check_budgets`)
hot bytes, exchanged bytes, CAS bytes, and per-kind counts against
`MeshPolicy`. `tests/test_mesh_storage.py` proves the core claim with
numbers: 200 routine observations + 3 findings exchange exactly 3 compact
records (< 1/10th of generated bytes), and a 5 MiB blob referenced by three
nodes is stored once.

| Information         | Origin node | Foreign node          |
|---------------------|-------------|-----------------------|
| routine exhaust     | short TTL   | never exchanged       |
| Observation         | bounded     | selective metadata    |
| Finding / Claim     | hot         | hot compact record    |
| Replication         | hot         | hot compact record    |
| full evidence       | local CAS   | fetch on demand       |
| accepted knowledge  | durable     | broadly replicated    |

## MNCS-owned runtime paths

Real mesh decision logic runs in MNCS (`src/mncs_commons/mesh/mncs/`):

- `commons/mesh/availability.mncs` — availability ranking/merging/fetch gating;
- `commons/mesh/outcome.mncs` — replication-outcome combination law;
- `commons/mesh/interest.mncs` — subscription matching kernel
  (`candidate_matches` discriminant law, `candidate_matches_named` over
  open-vocabulary byte views via `mncs.std.text_map.v1`, and
  `candidate_matches_full`, the complete production membership law);
- `commons/mesh/lattice_check.mncs` — cross-module no-divergence proof
  binding the mesh lattice to `mncs.core.status.v1` (Profile 0.9 aliases).
- `commons/mesh/lifecycle.mncs` — append-only transition law: the 9x9
  allow-matrix plus violation-mask diagnostics (`transition_check`).

Exhaustive corpora (`mncs/corpora/`, generated by
`scripts/generate_mesh_corpora.py`) execute on research-bytecode and
portable-wasm (see `tests/test_mesh_interop.py` `KERNEL_CASES` for the
per-corpus pass/agreement gate). The Python mirrors agree with every
checked-in expectation, and the mncs-actions `commons-mesh` check
re-verifies versions, corpora drift, the law contract (every corpus case
targets a pinned entry point at the contracted arity), golden digest,
kernel studies, and descriptor negotiation on every run.

Production execution runs through `MncsKernelExecutor`
(`mesh/executor.py`): `synchronize`/`select_for_peer`/`receive_records`
take an opt-in executor that decides batched membership through
`candidate_matches_full`, reading verdicts from per-case `returned`
payloads. The default lane keeps the pinned Python mirror (identical
law, microseconds); the kernel lane is proven equivalent by
`test_executor_lane_agrees_with_mirror_on_sync` through a real sync
round and runs in the `mncs-toolchain-interop` lane.

Deliberately host-side (bounded ABI, see `MESH_PRESSURE_LEDGER.md`):
SHA-256 digest production, sockets/transports, filesystem/CAS I/O,
open-vocabulary string matching. These are explicit boundaries, not holes.

## Profiles

```text
single-node      one CommonsNode, no carriers (controller-local preserved)
peer-to-peer     DirectCarrier sync between operator-connected nodes
relay-assisted   RelayCarrier through one or more optional relays
public relay     relay with the public-contribution exchange policy
view/index       disposable build_view projections over possessed records
Fabric-carried   FabricCarrier where both peers enroll (optional)
offline/bundle   BundleCarrier export/import across an air gap
```

## Ownership

| Concern                              | Owner                  |
|--------------------------------------|------------------------|
| record identity, possession, sync    | Commons (`mesh/`)      |
| participant/producer identity shape  | Rights & Provenance    |
| authenticated transport (optional)   | Fabric                 |
| execution, pressure evidence intake  | Forge                  |
| technical conformance                | MNCS / validators      |
| acceptance / promotion decisions     | governance (not Commons) |
| family verification                  | mncs-actions           |

## Exchange evolution

`ExchangeDescriptor` now advertises an additive `mesh` capability block
(versions, sync modes, transports, negotiation rule, authority statement).
Protocol negotiation (`negotiate`) intersects capabilities; unknown
vocabulary is reported under `inert*` and never acted on.
