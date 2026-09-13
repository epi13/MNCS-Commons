# Development Pressure Records

Status: experimental coordination model. Commons remains independently usable and does not depend on Forge.

Commons is the exchange surface where independent development observations, proposals, replications, and decisions meet. It records structured claims and relationships; it does not decide that a capability becomes part of MNCS or MNCDS.

## Record types

### CapabilityGap

A `CapabilityGap` is a Commons representation of development pressure. It contains a content-addressed identity, producer, originating project and exact revision, requested capability, limitation, reproducer, affected surfaces, protected properties, evidence requirements, scoped PASS/FAIL/UNKNOWN status, and explicit unresolved fields.

### ResolutionProposal

A proposal names one candidate resolution for one or more gaps, including its semantic interpretation, implementation surfaces, compatibility impact, rejected alternatives, and evaluation plan. Multiple proposals remain distinct.

### ChangeSet

A change set binds coordinated work across repositories: exact base revisions, participating repositories, dependency edges, contract snapshots, landing order, evidence expectations, and assembled final-tree identity. Repository PRs remain authoritative for repository changes.

### EvidenceAmendment and PromotionDecision

Evidence is append-only from Commons' perspective. New results, replications, disagreements, invalidations, and corrected metadata are amendments linked to the original identity. A `PromotionDecision` identifies the selected candidate, authority level, evaluator, policy, evidence, scope, and unresolved unknowns. It records a decision; it does not upgrade status automatically.

## Relationship vocabulary

Commons should preserve typed, attributable edges:

- `supports_pressure`
- `proposes_resolution`
- `groups_with`
- `implements_change_set`
- `supported_by`
- `replicates`
- `contradicts`
- `invalidates`
- `promotes`
- `supersedes`

A relationship carries evidence for that relationship only.

## Distributed rules

Publication is not acceptance. Contributors may publish competing pressures and proposals without a central lock. Similarity may suggest convergence but cannot erase original records.

Consumers must be able to recover origin, exact revisions, candidates, supporting/contradicting evidence, unknowns, policy, decision-maker, and later amendments. Commons must not import private Forge/Fabric state, rewrite raw execution receipts, convert observations into authority, infer system-level PASS from component records, or hide unavailable/disagreeing evaluators.

Forge may publish through a public adapter, but Commons must remain useful with independently produced records.

## Atlas WASM backend pressures (2026-09)

The Atlas family-registry campaign produced three concrete language/backend
pressures. They are recorded as separate immutable declarations because their
root causes, owning layers, and regression tests are different:

| Pressure | Root cause | Owner | Status |
| --- | --- | --- | --- |
| [`MNCS-LANG-4F3798658F55`](../pressures/records/MNCS-LANG-4F3798658F55.json) | Recursive cell flattening passed an `i64` scratch local directly to a WASM `i32.load` address operand. | `mncs-language` | resolved |
| [`MNCS-LANG-4219A56741DB`](../pressures/records/MNCS-LANG-4219A56741DB.json) | Packed bounded view descriptors were treated as allocating views, suppressing loop-region reclamation until Atlas exhausted its arena. | `mncs-language` | resolved |
| [`MNCS-LANG-59894A2D6A3D`](../pressures/records/MNCS-LANG-59894A2D6A3D.json) | Current artifacts preserved source-level function contracts while physical backend exports became qualified; the pre-refresh Harness adapter confused the two. | `mncs-harness` / `mncs-language` | resolved |

Both records preserve a pre-fix Atlas reproduction, the exact language
revision at which it was observed, implementation metadata, and separate
current PASS verification from `mncs-language` and `mncs-atlas`. The focused
regressions are `nested_flatten_wraps_i64_scratch_addresses_before_memory_access`
and `packed_bounded_views_are_preserved_as_nonallocating_words`; Atlas's
consumer verification is `tests.test_experimental_wasm`.

The corresponding human-readable investigation is
[`atlas-wasm-2026-09.md`](development-pressure-evidence/atlas-wasm-2026-09.md).
The artifact-contract investigation is
[`harness-artifact-contract-2026-09.md`](development-pressure-evidence/harness-artifact-contract-2026-09.md).
