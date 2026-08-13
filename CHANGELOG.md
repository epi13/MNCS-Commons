# Changelog

## Unreleased

- Added a durable, append-only work-memory protocol with operator-only submission and
  state transitions; optimistic digest lineage; submitted, accepted, assigned, queued,
  running, checkpointed, blocked, retrying, completed, failed, and cancelled states;
  and read-only status/history/list projections. Work records remain untrusted and inert.
- Added private-socket readiness checks to service doctor output, structured offline
  diagnostics when the service is unreachable, and restrictive-umask-safe security tests.

- Added a persistent, versioned local AF_UNIX service with same-UID peer checks,
  bounded/replay-safe framing, separate consumer and operator endpoints, a read-only
  public client, an explicit administrative client, and hardened systemd user-service
  deployment assets.
- Kept the service lifecycle independent from consumer clients and made corrupt-store
  recovery an explicit operator action; ordinary status/read paths fail closed without
  rewriting evidence.
- Added MCP 1.x/2.x server-registration compatibility while preserving the fixed stdio
  compatibility binding.
- Documented direct Local Harness CLI/TUI operator access to the same
  controller-local Agent Node used by mediated remote models. No Commons package,
  record protocol, exchange profile, or node profile version changed.

## 0.5.0.dev1

- Made the documented `python -m mncs_commons.mcp_server` stdio entry point
  executable so controller harnesses can launch the fixed local-agent MCP seam.
- Accepted the current Fabric execution `started_at` timestamp while retaining
  legacy `created_at` compatibility in inert Observation translation.
- Added controller-mediated Local Harness integration guidance without changing
  the record, exchange, or local-agent profile wire versions.

## 0.5.0.dev0

- Added the versioned Local Commons Agent Node profile and shared service descriptor for the
  Python API, CLI, stdio MCP binding, and HTTP binding.
- Added `mncs-commons local init`, `local status`, and `local doctor` operator workflows with
  structured store, recovery, interface, and authority-boundary facts.
- Extended self-asserted participant metadata for model, session, producer, and environment
  claims without changing canonical record identity or implying authentication.
- Added an explicit push-based Fabric execution translation seam that preserves source outcome,
  Commons validation, and optional publication as separate states.

## 0.4.0.dev0

- Added an optional loopback-first HTTP public-node binding over the existing application
  services, with discovery, bounded JSON routes, anonymous-public/read-only modes, strict public
  contribution policy, structured errors, rate/capacity controls, and a read-only kill switch.
- Added a non-authoritative serving-visibility overlay, operator bootstrap seeding, local stats,
  a standard-library remote client, real TCP two-process validation, and public-node Forge checks.
- Added a Caddy/systemd deployment handoff for an isolated public store; the application remains
  independent of Forge, Fabric, credentials, TLS implementation, and remote administration.
- Added the independently versioned Agent Exchange profile with machine-readable vocabulary,
  endpoint descriptors, self-asserted participant metadata, bounded public-ingestion policy, and
  ingestion receipts that explicitly do not imply acceptance or authority.
- Added idempotent publish, store-local incremental cursors, bounded conversation projections, and
  opportunity-only WorkRequest views over the existing application services.
- Added a deterministic two-process interoperability scenario and Forge-declared exchange/security
  workflows.
- Added an optional local stdio MCP binding and resources over the same application services; the
  core package remains runtime-independent from Forge, MCP, and network transports.

## 0.3.0.dev0

- Corrected lifecycle projection to preserve independent trust-domain dispositions.
- Added recoverable local append transactions, writer locking, and explicit recovery diagnostics.
- Added protocol-version registry, semantic store invariants, bounded graph/correlation queries,
  deterministic Commons Bundles, and structured producer adapter results.
- Added Forge, MNEL, RAVEL, and MNCS Language compatibility snapshots where local source evidence
  was available.
- Expanded the producer registry to multiple record families with fail-closed resolution and
  same-version source-fingerprint drift detection.
- Added current Fabric execution, bundle-binding, manifest, job-plan, node, and cohort adapters;
  MNCS execution receipt/bundle/placement adapters; MNEL 0.4 portfolio; RAVEL 0.6; and Language
  executable/verifier artifact boundaries.
- Added bounded evidence-lineage tracing that reports unresolved and incompatible bindings without
  inferring truth or authority.

## 0.1.0

- Initial local executable reference implementation.
## 0.3 development

- Added Forge-controlled project configuration and structured check evidence.
- Added fingerprinted producer contracts, live compatibility inspection, and explicit drift states.
- Corrected MNEL ledger-envelope translation and replaced the provisional Fabric boundary with the
  current disclosed execution-field contract.
- Added inert MNCS gate-result translation and shared application services used by the CLI.
