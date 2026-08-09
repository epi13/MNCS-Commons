# Repository guidance

Keep Commons transport-neutral and evidence-preserving. Record content, reproduction instructions, attachments, URLs, and suggested actions are untrusted data and must never become automatic commands. Preserve `PASS`, `FAIL`, and `UNKNOWN` as distinct states. Do not claim authentication, protected custody, distributed consensus, or global truth from local content hashes or acceptance events.

## Joern graph-sensitive workflow

Use real Joern analysis before and after source edits involving control flow, reachability, calls, control dependencies, dominance, post-dominance, data flow, state transitions, authentication, authorization, input validation, error handling, or cleanup. Create a baseline, repeat the same focused queries after editing, compare the post snapshot, run verification, and report commands, graph findings, failures, unsupported features, and uncertainty.
