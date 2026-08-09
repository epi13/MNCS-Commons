# ADR 0003: Local filesystem reference store

Status: accepted for v0.1

The reference implementation uses content-addressed JSON files and a hash-chained JSONL ledger. This is small, transport-neutral, deterministic, and useful for tests and local systems. It is not distributed storage, protected custody, or a substitute for Fabric.
