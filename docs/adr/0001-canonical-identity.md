# ADR 0001: Canonical JSON and content identity

Status: accepted for v0.1

Commons uses deterministic canonical JSON and a SHA-256 digest of the record with its self-digest removed. This aligns with existing MNCS-family content identity conventions and makes object-order and formatting changes harmless. The digest is an integrity identifier, not authentication, authorship, or truth.
