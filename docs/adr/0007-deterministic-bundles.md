# ADR 0007: Deterministic Commons Bundles

Status: accepted for the 0.2 development iteration

Commons uses a bounded ZIP interchange artifact with canonical JSON members and a digest-bearing
manifest. Export order, ZIP timestamps, paths, and member bytes are deterministic. Import verifies
the complete bundle before adding records locally. Bundles carry information and unresolved
references; they do not fetch, execute, authenticate, or grant authority.
