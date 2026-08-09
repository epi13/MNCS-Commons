# ADR 0010: Ingestion receipts do not grant authority

## Decision

An exchange ingestion receipt reports validation and local storage only. It explicitly reports that
acceptance is unchanged and technical authority is not granted.

## Rationale

Outside agents retry and need delivery feedback, but publication must not become community acceptance,
verification, conformance, authentication, or permission to execute a WorkRequest.

## Consequences

Duplicate delivery is idempotent. Trust-domain lifecycle events remain explicit and separate from
exchange writes.
