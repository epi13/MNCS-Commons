# Synthetic integration scenarios

These scenarios are deliberately synthetic. They exercise the protocol shape without claiming
that the measurements, compiler behavior, provider behavior, or semantic lowering are real.

## Execution placement

The test scenario combines an MNEL-style diagnostic observation, a Forge work request, a scoped
claim, a failed replication, and independent trust-domain dispositions. Resource values are
machine-scoped and remain observations rather than generalized recommendations.

## Semantic identity

The test scenario imports an MNCS Language semantic graph identity, keeps the machine-intent and
lowering obligation opaque to Commons, and supersedes the first observation after the graph
identity changes.

Run the scenario tests with `pytest -q`.
