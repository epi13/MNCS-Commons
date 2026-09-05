# Mesh Pressure Ledger: what distributed Commons taught MNCS-language

Every material deficiency or deliberate boundary encountered while building
the Commons Mesh as an MNCS workload. Classifications follow the family
rule: `LANGUAGE_GAP | STDLIB_GAP | RUNTIME_GAP | ABI_GAP | TOOLING_GAP |
COMPILER_BUG | BACKEND_GAP | DOCUMENTATION_GAP | COMMONS_DESIGN_GAP`.
Host interop kept as a deliberate bounded ABI boundary is marked
`HOST_BOUNDARY_RETAINED` (not a deficiency).

## P-COMMONS-01 — no boolean negation operator

- Originating capability: mesh interest-matching kernel
  (`mncs/commons/mesh/interest.mncs`).
- Classification: `LANGUAGE_GAP` (known; stdlib notes operators pending).
- Minimal reproduction: `if !flag { ... }` fails lexing with `MNL002
  "unsupported source character '!'"`.
- Owning repository: `mncs-language`.
- Resolution: worked around in Commons with if/else branching (the
  `mncs.core.logic.v1` pattern). No compiler change requested this
  iteration; expression operators remain a language roadmap item.
- Tests: `commons-interest-corpus.json` (135 cases) executes the branchy
  form on both backends, PASS.
- Commons consumer: `candidate_matches` entry point.
- Status: `OPEN` (upstream), workaround is permanent-safe.

## P-COMMONS-02 — no unary minus / negative literals in expressions

- Originating capability: lifecycle-rank mapping in the interest kernel.
- Classification: `LANGUAGE_GAP`.
- Minimal reproduction: `return -1;` fails parsing (`MNP064 "expected
  expression"`, found minus).
- Owning repository: `mncs-language`.
- Resolution: Commons design adaptation (kept): ranks shifted to
  `other/disputed(0) < proposed(1) < reproduced(2) < verified(3) <
  accepted(4)`, eliminating negative literals. Comparison-only code
  carries no integer-overflow obligation, confirmed by
  `completed`-without-obligation study results.
- Tests: interest corpus boundary cases (`min_rank` 0/1/3) on both backends.
- Commons consumer: `lifecycle_rank`, mirrored by `_lifecycle_rank`.
- Status: `RESOLVED_BY_DESIGN` (no workaround debt).

## P-COMMONS-03 — qualified record construction does not elaborate

- Originating capability: lattice-agreement probe binding stdlib
  `mncs.core.status.v1` (`mncs/commons/mesh/lattice_check.mncs`).
- Classification: `LANGUAGE_GAP` (candidate `COMPILER_BUG` if qualified
  construction is specified; qualified *calls*, *types*, and *variant
  patterns* all resolve, only `Alias.Record { ... }` construction fails).
- Minimal reproduction: with `use mncs.core.status.v1 as status`,
  `status.StatusPair { left: left, right: right }` fails elaboration with
  `MNE123 "finite constructor names an unknown nominal type"`.
- Owning repository: `mncs-language`.
- Resolution: Commons workaround via the scalar-argument join
  `status.dominate/2` (same lattice join `combine` delegates to), so the
  no-divergence proof stays exact. Machine-readable pressure artifact
  issued: `mncs:0.2:capability-gap:e2ac5125...` (see below).
- Tests: `commons-lattice-corpus.json` (9/9 agreement) on both backends;
  fixture + unit tests in `crates/mncs-model/src/capability_gap.rs`.
- Commons consumer: `candidate_lattice_agrees`.
- Evidence digest: `mncs:0.2:capability-gap:e2ac5125d915242e2c1ebddfd4b4a2bfe5a0f3fa03ff2d1d42938ffcf386dc7e`.
- Status: `RECORDED` (artifact issued, workaround exact).
- Update (conversion run): **resolved upstream** — `mncs-language` PR #107
  retries two-segment `alias.Record { ... }` in the record namespace
  (finite constructors keep priority). The lattice probe now constructs a
  real `StatusPair` and calls stdlib `combine` directly; the `dominate`
  workaround is removed. Status: `RESOLVED`.

## P-COMMONS-04 — capability-gap artifact machinery existed only as prose

- Originating capability: filing P-COMMONS-03 through the proper mechanism.
- Classification: `TOOLING_GAP` (language-family).
- Minimal reproduction: `docs/capability-gap-artifacts.md` specified the
  artifact; no schema, emitter, fixture, or test existed.
- Owning repository: `mncs-language`.
- Resolution: **fixed this iteration** — `crates/mncs-model/src/capability_gap.rs`
  (content-addressed artifact, local-path redaction, tri-state status,
  fail-closed bounds), JSON Schema `spec/capability-gap-0.1.schema.json`,
  fixture `examples/capability-gaps/qualified-record-construction.json`,
  emitter example, 5 unit/integration tests green.
- Tests added: `capability_gap::tests::*` (5).
- Commons consumer: mesh pressure filing (P-COMMONS-03 round-trips).
- Status: `RESOLVED`.

## P-COMMONS-05 — SHA-256 digest production is host-only

- Originating capability: content identities for mesh records/capsules.
- Classification: `HOST_BOUNDARY_RETAINED` (deliberate; matches
  `mncs.core.identity.v1`, which keeps digest *comparison/ordering* portable
  and digest *production* at the capability boundary).
- Owning repository: `mncs-language` (acknowledged boundary).
- Resolution: none requested. Commons computes digests in Python;
  `Digest32` equality/ordering logic stays available to portable code.
- Status: `RETAINED_BY_DESIGN`.

## P-COMMONS-06 — sockets/transports/filesystem stay host-side

- Originating capability: mesh carriers, node CAS, relay persistence.
- Classification: `HOST_BOUNDARY_RETAINED`.
- Owning repository: `mncs-language` (portable profiles) / Fabric (carrier).
- Resolution: none requested. `FabricCarrier` fails bounded
  (`TRANSPORT_UNAVAILABLE`) without a runtime; direct/bundle/relay paths
  prove the mesh never requires Fabric (`test_fabric_is_optional_not_required`).
- Status: `RETAINED_BY_DESIGN`.

## P-COMMONS-07 — open-vocabulary string matching has no portable surface

- Originating capability: projecting kind/project/contract/producer names
  to kernel discriminants.
- Classification: `STDLIB_GAP` (narrow: bounded fixed-width byte equality
  exists in `mncs.std.text_view.v1`; open text -> closed discriminant
  mapping does not).
- Owning repository: `mncs-language`.
- Resolution: host-side discriminant tables (`KIND_DISCRIMINANTS`,
  `OUTCOME_DISCRIMINANTS`, `LIFECYCLE_DISCRIMINANTS`) with unknown names
  mapping to never-matching `Other` discriminants. No stdlib change
  requested: the general primitive (bounded text map) needs its own design
  cycle beyond this iteration.
- Tests: interest corpus invalid-vocabulary cases (`k6/o9/s5`) agree
  (excluded) across Python mirror and both backends.
- Status: `RECORDED` (narrow follow-on).
- Update (conversion run): **resolved upstream** — `mncs.std.text_map.v1`
  (`mncs-language` PR #107) provides bounded caller-owned `Coded16/32`
  tables with total `lookup16/32` over `text_view` matchers. The named
  interest tables (`kind_code_of`, `outcome_code_of`, `state_code_of`)
  consume it; the machine-readable table-authority test binds host
  projections to the same literals. Status: `RESOLVED`.

## P-COMMONS-08 — per-decision subprocess execution cannot own hot paths

- Originating capability: executing normative kernels on production sync
  paths (`select_for_peer`, `receive_records`).
- Classification: `RUNTIME_GAP` (embeddable execution). One
  `experiment run` costs seconds (compile-dominated); per-decision
  subprocess calls are infeasible on synchronous paths, and
  `experiment execute` refuses substituted corpora by design (frozen
  replication only).
- Owning repository: `mncs-language`.
- Resolution: filed upstream as `commons.mesh/embeddable-execution`
  (`GapStatus::Fail`, `mncs-language` PR #107); sanctioned fallback is
  the batched production executor (`MncsKernelExecutor`: one
  `experiment run` per batch, verdicts read from per-case `returned`),
  wired opt-in through `synchronize`/`select_for_peer`/`receive_records`.
  Hot single-decision paths keep Python mirrors pinned by corpus
  agreement until the runtime closes the gap.
- Tests: `test_executor_lane_agrees_with_mirror_on_sync` (both lanes
  receive identical digests through a real sync round).
- Status: `RECORDED` (open upstream, fallback exact).

## P-COMMONS-09 — plain integer `+` leaves overflow obligations

- Originating capability: summing violation-mask bits in the lifecycle
  transition kernel (`transition_check`).
- Classification: `LANGUAGE_GAP` (narrow; resolved by existing
  semantics, newly applied).
- Minimal reproduction: `transition_check` with `+` compiles
  `completed_with_unresolved_obligations`
  (`body:integer-overflow`); the same kernel with `+%` compiles
  `completed` with zero obligations.
- Owning repository: `mncs-language` (documented in
  `mncs.core.numeric.v1`; applied here, no compiler change needed).
- Resolution: **resolved in-kernel** — wrapping addition expresses the
  exact intent (each bit set at most once, sum far below range), so the
  lifecycle law is PASS-capable end to end. If-chain kernels stay
  obligation-free; `iterate`-carrying kernels (textmap lookups) retain
  `iteration-exact-resource-cost` obligations and gate in agreement mode.
- Tests: `commons-lifecycle-corpus.json` (484 cases) PASS on
  research-bytecode; source-study `completed`.
- Status: `RESOLVED`.

## What Commons forced MNCS-language to learn

1. Cross-module **record construction** is the sharp missing edge of the
   otherwise working Profile 0.9 namespace system (calls, types, and
   variant patterns resolve; construction does not) — now a
   content-addressed artifact, not a chat message.
2. The capability-gap pipeline went from design prose to working
   schema + emitter + fixture + tests because a real workload needed to
   file a real gap.
3. Missing micro-syntax (`!`, unary minus) is absorbable by design
   (branchy negation, shifted ranks) with zero obligation debt — but each
   instance should be a ledger line, not folklore.
4. The family pattern (normative `.mncs` + golden vectors + host mirror +
   agreement tests, as pioneered by rights pressure provenance) ports
   cleanly to application-owned kernels via `MNCS_LIBRARY_PATH`, with the
   lattice-agreement probe proving stdlib/mesh coherence mechanically.
5. Dogfooding the family workflow as a first caller finds real defects
   fast: `required-checks` takes comma-separated ids (a JSON array fails
   the aggregate closed with `check id is not declared`), the reusable
   workflow runs on the runner's default `python3` (no `pytest` — the
   caller installs its hash-pinned lock first), and every new caller
   file must extend the owning capability map (`family-capability.json`,
   enforced by `test_capability_covers_tracked_actions_files`). A FAIL
   verdict is data: the first red aggregate honestly reported the
   unmapped-file suite failure, not a broken mechanism.
6. Converting production behavior to MNCS is shaped like the toolchain:
   single-assignment pushes law into total if-chains and `&&`
   conjunctions (proven on research-bytecode and portable-wasm);
   `experiment run` economics (~1.5s fixed, ~0.5s/case for small
   argument lists, ~30s/case for textmap-heavy lookups) make the batch
   the unit of
   production execution, with per-case `returned` payloads as the
   decision channel and placeholder `expected` values as harness
   affordance. The host projects, the kernel decides — and the Python
   fast path is a pinned transcription of the kernel, not a second
   implementation.

## Family verification adoption (2026-09)

- `mncs-actions` self-hosts its own reusable workflow
  (`mncs-actions-orchestration-boundary`: `project-tests` pytest suite +
  `action-pins` immutable-ref hygiene; PR #26).
- `mncs-language` declares `mncs-language-pressure-boundary`
  (`language-pressure-tests`: `cargo test -p mncs-compiler --test
  module_imports`, 34 tests incl. P-COMMONS-03 coverage; PR #106).
- `MNCS-Commons` declares `mncs-commons-mesh-boundary`
  (`commons-mesh-tests`: deterministic mesh unit scope, 22 tests across
  evidence/node/rights/security/storage; PR #39). The
  toolchain-latency-bound interop scope (one `mncs` source-study per
  kernel, tens of minutes) stays in repo CI by explicit boundary
  statement, not by omission.
- All three render evidence-backed MNCS badges
  (`docs/mncs-badge.svg` + `docs/mncs-badge.json` sidecar) from the
  aggregate verdict on `main` pushes. Carrier pin for this round:
  `mncs-actions@9469d8d61f4604df0f00f983aedb3d66c6ff8616`.
