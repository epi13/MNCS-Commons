# MNCS debugger integration campaign evidence

This is the Commons coordination record for the 2026-09 integration campaign.
It records evidence and lifecycle outcomes; it does not execute providers or
claim that an available capability is universally complete.

The exact owner revisions used for consumer verification are recorded in the
machine-readable companion file
[`mncs-debug-integration-2026-09.json`](mncs-debug-integration-2026-09.json).
The local debugger pressures retain their historical `MNCS-DEBUG-P-*` IDs and
map to canonical Commons pressure records rather than being copied as a
second pressure database.

## Established vertical path

The live fixture proves:

```text
Profile 0.17 source
  -> compiler inventory
  -> mncs-test TestResult/1 + CheckResult/1
  -> mncs-debug witness/trace/inspection/provenance/replay projections
  -> mncs-actions receipt/evidence manifest
  -> Forge consumes the Actions handoff, diagnoses, and applies bounded exact repair
  -> canonical mncs-test verification PASS
```

Test semantics remain in `mncs-test`; debug semantics remain in `mncs-debug`;
Actions only transports/validates/packages artifacts; Forge only orchestrates,
correlates identities, consumes the structured Actions handoff, applies
authorized exact edits, and preserves layered truth. A test `FAIL` with
unavailable debug evidence remains `FAIL` plus debug `UNKNOWN`.

The final fixed-revision canary passed at carrier revision
`15484764abde772001359fd34ac84e997578e3d8` (run
[`34795486359`](https://github.com/epi13/mncs-actions/actions/runs/34795486359));
its retained `mncs-fixed-development-loop-evidence` artifact is 6,778,924 bytes
and unexpired. The Forge consumer verification is
`test_failure_loop_consumes_actions_handoff_and_verifies_exact_repair` at
`dbece72fae723a93e9f7df636ab4ea47245b23be`.

The five-run debugger overhead baseline measured a direct median of 7.5669 ms,
a recording median of 1065.7882 ms, and a 1058.2213 ms median overhead
(140.85×). This is bootstrap/static-evidence overhead, not a claim about native
in-runtime tracing. The bounded policy therefore leaves normal PASS runs
lightweight and captures failure evidence only when requested/selected.

## Lifecycle outcome

Commons resolved only the three pressures whose original reproducers and every
affected consumer verification are PASS:

- `MNCS-DEBUG-P-006` → `MNCS-VERIFY-54B12B4A78DF` (`resolved`)
- `MNCS-DEBUG-P-007` → `MNCS-TOOLING-0C870FCAFFEB` (`resolved`)
- `MNCS-DEBUG-P-009` → `MNCS-COMPILER-94428E41EEAC` (`resolved`)

P-001, P-002, P-003, and P-008 remain partially resolved. P-004, P-005,
P-010, and P-011 remain open. P-012 is deferred as a platform/storage
boundary. No live stepping, frames, watchpoints, or deterministic replay claim
was fabricated, and no new language syntax or runtime primitive was added
without a reproducer establishing that it was necessary.
