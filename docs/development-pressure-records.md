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
