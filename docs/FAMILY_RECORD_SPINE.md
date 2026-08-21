# MNCS Family Record Spine

Status: architecture proposal / non-normative

## Purpose

The MNCS family now produces useful records in many places: compiler and semantic records in MNCS Language, execution records in Fabric, routing/tool observations in Harness, durable run state in Control, evaluation records in Forge, development records in MNCDS, and assurance/conformance records in MNCS. The missing piece is not another authority layer. It is a coherent, inspectable way to connect these producer-owned records without copying their semantics into one repository.

This document defines the proposed **MNCS Family Record Spine**. Commons is the coordination and record graph for the family, while each producer continues to own the meaning of its native records.

## Core rule

> Transport, storage, indexing, and graph projection do not transfer semantic authority.

Commons MAY store, reference, bundle, query, and relate producer records. Commons MUST NOT reinterpret a Fabric execution PASS as an MNCS PASS, a Forge result as a development decision, a model recommendation as an MNEL or RAVEL conclusion, or an ingestion receipt as technical acceptance.

## Ownership model

| Producer | Owns | Commons role |
| --- | --- | --- |
| MNCS Language | semantic graphs, compiler stages, lowering/translation evidence, language-profile facts | index and relate exact identities |
| Fabric | execution, worker, environment, placement, receipt, bundle and cohort facts | preserve execution references |
| Harness | model/worker routing, declared role, tool exposure and policy observations | preserve actor and route provenance |
| Control | durable experiment lifecycle, actor scheduling, handoffs and terminal run state | preserve coordination lineage |
| Forge | bounded verifier/evaluator results, candidate comparisons and unresolved obligations | preserve independent evaluation references |
| MNEL | scientific experiment interpretation, causal attribution and distilled experimental learning | future producer; not required for bootstrap |
| RAVEL | adaptive strategy/learning records and next-intervention proposals | future producer; not required for bootstrap |
| MNCDS | development-process lineage, selection, feedback, release/regeneration lifecycle | preserve governed development references |
| MNCS | assurance, claim and conformance semantics | preserve final evidence-case references |

RAVEL and MNEL are deliberately not required for the first implementation of this spine. Temporary Harness/Fabric model roles MAY provide investigator or adaptive-critic observations, but their producer identity MUST remain the exact Harness/Fabric/model identity and MUST NOT claim to be RAVEL or MNEL.

## Record is not artifact

The spine distinguishes durable records from large implementation artifacts.

A record should normally carry identity, digest, producer, schema/version, scope, provenance, relationships and a resolvable artifact reference. Large binaries, compiler dumps, model weights, worktrees and execution bundles may remain in their producer-owned stores or artifact systems.

Commons is the semantic index and graph, not a universal blob store.

## Producer-neutral Concept Experiment envelope

The first cross-family record to exercise the spine should be a producer-neutral **Concept Experiment** envelope. It identifies a bounded study without assigning scientific authority to a future system that may not yet be running.

Illustrative shape:

```text
ConceptExperiment {
  experiment_id
  concept_id
  governing_contract_refs[]
  governing_rfc_refs[]
  target_capability
  language_profile

  hypothesis
  task
  falsifiers[]
  protected_properties[]
  frozen_inputs[]
  hidden_inputs[]
  resource_budget

  actors[] {
    worker_id
    model_id
    harness_role
    provider_id
  }

  candidate_refs[]
  compiler_record_refs[]
  execution_refs[]
  evaluation_refs[]
  observation_refs[]
  failure_refs[]

  status
  rerun_of
  predecessor
}
```

The envelope is a coordination identity, not a verdict. Its references retain their native meaning.

## Concept Reconstruction Experiments

A **Concept Reconstruction Experiment (CRE)** asks one or more independent experimenters to reconstruct a fundamental computing concept required by the MNCS family using the semantics currently available in MNCS Language.

The existing Python/Rust implementation of an MNCS component is a source of requirements, invariants and comparison evidence, not the implementation template. Where practical, initial candidate generation should be blind to the original implementation so the study tests independent expressivity rather than transpilation.

Example progression:

```text
fundamental CS concept
        -> independent MNCS implementations
        -> compiler/language records
        -> Fabric execution records
        -> Forge evaluation
        -> PASS / FAIL / UNKNOWN observations
        -> causal/failure classification
        -> language/compiler/tooling proposal
        -> rerun the frozen experiment
```

Failures are first-class evidence. Recommended machine-readable failure classes include:

- implementation error
- language expressivity gap
- semantic-model gap
- compiler/lowering gap
- verifier/evaluator gap
- tooling/orchestration gap
- target/portability gap
- specification ambiguity
- unresolved/insufficient evidence

A failed study SHOULD remain addressable so that the same frozen experiment can become a regression experiment after a repair.

## Bootstrap roles before RAVEL/MNEL

The first studies may use ordinary models routed through Harness/Fabric under explicit roles:

- `experimenter` / `builder`: construct a candidate implementation;
- `experiment-investigator`: critique the experiment, identify falsifiers and competing explanations, classify evidence gaps;
- `adaptive-experiment-critic`: propose the next high-information intervention from retained outcomes;
- `reviewer` / `skeptic`: challenge claims or attempt independent reproduction.

These are model roles, not project identities. Their records should preserve exact worker, model, provider, prompt/source, harness version and tool exposure where available.

This bootstrap has a useful later consequence: future MNEL and RAVEL implementations can be empirically compared with the ordinary-model role baselines they replace.

## Transport and coordination

Initial deployment should use one controller-local Commons node:

```text
remote model/worker
      -> Fabric execution
      -> Harness/Control mediation
      -> producer-native records
      -> controller-local Commons
```

Workers do not require Commons store paths, operator sockets or direct mutation authority. Fabric carries execution material; Harness/Control mediate tools and orchestration; Commons receives inert records or references through explicit publication boundaries.

Federated Commons-over-Fabric transport may be added later if locality requires it. Federation is not required for the first experiments.

## Progressive evidence projection

The family should prefer non-destructive projection over destructive summarization:

```text
raw execution/compiler/verifier evidence
        -> Concept Experiment graph
        -> scientific/adaptive interpretations
        -> MNCDS development record
        -> MNCS assurance case
```

Each upper layer references exact lower-layer identities. A consumer can therefore drill from an MNCS claim through MNCDS lineage, experiment identity, verifier result, compiler record and exact Fabric receipt without forcing MNCS to ingest every stdout line or model turn.

## Initial integration obligations

1. Commons: define stable external-reference conventions and producer compatibility entries for the experiment spine.
2. Control: give durable experiments an explicit Concept Experiment manifest and terminal publication boundary.
3. Harness: preserve exact role/model/worker/tool provenance; model roles must not impersonate RAVEL/MNEL.
4. Fabric: preserve execution identities and transport facts without claiming experiment or conformance authority.
5. Forge: bind evaluation records to candidate, concept experiment, language profile and verifier identity; generator cannot self-certify.
6. MNCS Language: expose stable semantic/compiler study identities suitable for CRE references.
7. MNCDS: define how eligible Concept Experiments and their evidence may be bound into governed development records.
8. MNCS: define how downstream assurance cases reference MNCDS and evidence identities without absorbing producer semantics.
9. Atlas: document the family-level flow and ownership map.

## First end-to-end study

Before relying on the spine for substantial language work, run one tiny synthetic study through the full path:

```text
Control -> Harness -> Fabric -> Language -> Forge -> Commons -> MNCDS -> MNCS
```

The preferred first CRE is the MNCS tri-state result lattice (`PASS`, `UNKNOWN`, `FAIL`) because it has a tiny exhaustive state space and clear algebraic laws. A second strong target is retry authority under uncertain failure; a third is capability/effect authorization.

Every boundary should preserve identities and be able to retain `UNKNOWN` without silently strengthening it.

## Extraction threshold

Do not create a new shared `mncs-record-protocol` repository preemptively. Extract a neutral interoperability package only when multiple independent implementations genuinely need the same canonical reference/digest/envelope primitives and duplicated compatibility code becomes a material burden. Domain record semantics should remain in their owning repositories even if neutral plumbing is later shared.
