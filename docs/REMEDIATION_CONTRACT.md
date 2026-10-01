# Family remediation contract (`mncs.remediation/1`)

The executable contract lives in
`src/mncs_commons/mesh/mncs/commons/family/remediation/v1.mncs`. This
document states the wire, process, and ownership rules around it.

## Ownership

```text
provider knows how to diagnose/repair its domain
Doctor orchestrates remediation policy
Environment owns session/context/claims/lifecycle
Commons owns this family contract
```

Environment must not gain provider-specific repair knowledge. Doctor
must not guess provider shell commands. Providers must not invent
envelope fields the contract does not define.

## Capability identity

A remediation provider publishes the `repository-remediation` contract
(or a future Commons-standardized domain contract) in its
`.mncs/project.json` `provides` with a working `invocation` descriptor
and `effects: ["write"]`. The bound capability reads
`<provider>:repository-remediation`. Availability is honest: the
capability binds only when the declared address exists.

The repository domain is the only domain standardized in v1. New
domains extend the `domain` vocabulary through Commons, never
bilaterally.

## Request shape (argv)

```text
<provider> [--target <path>] [--json] [--dry-run]
           [--changed-path <scope-relative-path> ...] [--budget <n>]
```

- `--target`: scope target. Repository domain: checkout root (required).
- `--json`: print exactly one envelope on stdout (required for machine use).
- `--dry-run`: MUST NOT mutate anything. Records carry `validated: false`,
  verification is vacuous, evidence is still written.
- `--changed-path`: hint narrowing the scope, repeatable, relative to the
  target. The provider MUST NOT remediate outside the hinted paths when
  hints are given.
- `--budget`: max items repaired per run (default 256). Items beyond the
  budget escalate as `budget-exhausted:<target>` (warning); a re-run
  continues.

## Response envelope (`mncs.remediation/1`)

JSON shape: `schemas/mncs-remediation-v1.schema.json`. Native shape:
`RemediationEnvelope` in the contract module.

- `schema_version` MUST be exactly `mncs.remediation/1`.
- `scope` echoes `{domain, target}` so the orchestrator can check the
  provider addressed the requested scope.
- `summary` carries terse counts `{repaired, reconciled, degraded,
  blockers}`. `repaired`/`reconciled` count validated actions this run
  performed; `degraded` counts currently degraded items; `blockers`
  counts error-severity escalations.
- `remaining` carries escalation ids only (max 64, with
  `remaining_truncated` when cut). Full records belong in evidence.
- `repairs`/`reconciliations` carry validated action records with
  before/after fingerprints (lowercase hex or null) and a `validated`
  flag. Dry-run records are never validated.
- `escalations` full records are optional on stdout; the ids in
  `remaining` are mandatory.
- `evidence` is a file path or null. When
  `$MNCS_ENV_SESSION_ARTIFACT_DIR` is set, evidence MUST go there so
  the calling session owns the trail.
- `budget` and `validation` report bounded execution and the
  post-mutation verification verdict.
- Orchestrators ignore unknown fields (forward compatibility).
  Providers MUST NOT remove fields within v1.

## Remediation classes

From `classify_repair` / `classify_stop` / `classify_residual`:

- `safe_automatic`: deterministic problem and repair, validated after
  mutation. Applied without involving the caller.
- `bounded_reconciliation`: the invariant is known but recovery takes
  work (cache regeneration, further converge rounds, granted
  semantically-proven repairs). Bounded, idempotent, validated;
  failure escalates.
- `escalation`: needs intent, judgment, or work outside safe repair.
  Carries `{id, code, target?, severity, action}` only.

Applicability codes: 0=safe, 1=semantically_proven, 2=review,
3=manual. Stop codes: 0=fixpoint, 1=budget_exhausted, 2=oscillation,
3=edit_conflict. Severity codes: 0=error, 1=warning, 2=info. Unknown
codes fail closed to escalation.

## Failure and refusal semantics

Envelope over exit codes: a provider that ran to completion reports
findings, escalations, and even verification failure INSIDE its
envelope. Only a missing or unparsable envelope is an orchestrator
refusal.

Orchestrator refusal codes (closed in v1):

- `remediation-provider-missing` / `remediation-provider-unavailable`
- `remediation-claim-required` / `remediation-adoption-required`
- `remediation-scope-unknown` / `remediation-scope-unsupported`
- `remediation-checkout-missing` / `remediation-checkout-unreadable`
- `remediation-changed-path-invalid`
- `remediation-envelope-invalid` / `remediation-envelope-incompatible`

Provider-side refusals (review edits, unparseable files, oscillation,
budget exhaustion, verification failure) are in-envelope escalations,
never transport failures.

## Claim and effect safety (repository domain)

The orchestrator MUST hold a live whole-scope claim before invoking
remediation, and MUST refuse scopes showing unknown work unless the
claim records explicit adoption or recovery. Path-scoped claims do not
cover whole-tree remediation. Providers trust the orchestrator's
authorization and MUST NOT invent their own claim checks.

## Retry law

`retry_delay_secs` / `retry_eligible` / `retry_verdict` bound repeated
recovery of an unchanged failure. Attempts count consecutive failures
against the SAME failure identity; the orchestrator resets the count
when the identity rotates, so any meaningful change re-enables
recovery immediately. Suppression withholds only the repeated recovery
ACTION; live observation still reports the degraded verdict, and
blockers are never hidden. Defaults live in
`family/remediation-policy-v1.json` (base 60s, max 900s).

Failure identity material (hashed by the host, in order): service
identity, status, code, canonical observation bytes, provider revision
identity, recovery-capability availability.

## Compatibility

- `schema_version` exact match is required; anything else refuses with
  `remediation-envelope-incompatible`.
- v1 fixes the repository domain, the envelope, the classes, the
  refusal codes, and the retry law. New domains and new optional
  envelope fields arrive as minor additions through Commons; breaking
  changes require `mncs.remediation/2`.

## Provider conformance

To implement the contract:

1. Speak the argv request and print one schema-valid envelope.
2. Honor `--dry-run` (no mutation), `--changed-path` (no out-of-hint
   repair), and `--budget` (bounded prefix + `budget-exhausted`
   escalations).
3. Route evidence to `$MNCS_ENV_SESSION_ARTIFACT_DIR` when set.
4. Classify every outcome through the native law (or provably
   equivalent vectors); unknown inputs escalate.
5. Stay quiet on re-runs: repaired state MUST report zero new repairs.

`mncs-doctor remediate` is the reference implementation.
`tests/test_remediation_conformance.py` runs the scenario battery
against a provider binary (`DOCTOR_BINARY`, defaulting to the sibling
checkout build) and validates each envelope against the schema.
