# Changelog

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
