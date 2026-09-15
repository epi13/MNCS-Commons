#!/usr/bin/env python3
"""Generate reviewable provider facts from language-owned ABI metadata.

The ABI is the authority for callable/module identity.  Contract ownership and
consumer intent remain explicit command-free inputs; this tool only emits the
fact that a repository exports the named contract through the supplied ABI.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


SCHEMA = "commons.mncs.generated-provider-metadata/v1"
GENERATOR_VERSION = "mncs-provider-facts/0.1"


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--abi", type=Path, required=True)
    parser.add_argument("--repository-id", required=True)
    parser.add_argument("--contract-identity", action="append", required=True)
    parser.add_argument("--contract-revision", action="append", required=True)
    parser.add_argument("--exported-identity", action="append", required=True)
    parser.add_argument("--evidence", action="append", required=True)
    parser.add_argument("--binding-content-identity", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    abi = json.loads(args.abi.read_text(encoding="utf-8"))
    if not isinstance(abi, dict):
        raise SystemExit("ABI metadata must be an object")
    lengths = {
        len(args.contract_identity),
        len(args.contract_revision),
        len(args.exported_identity),
        len(args.evidence),
    }
    if len(lengths) != 1:
        raise SystemExit("provider fact lists must have equal lengths")
    if not isinstance(abi.get("module"), str) or not isinstance(abi.get("interface_identity"), str):
        raise SystemExit("ABI metadata must contain module and interface_identity")
    if len(abi["interface_identity"]) != 64:
        raise SystemExit("ABI interface_identity must be a SHA-256 identity")
    if len(args.binding_content_identity) != 64 or any(
        character not in "0123456789abcdef" for character in args.binding_content_identity
    ):
        raise SystemExit("binding content identity must be a lowercase SHA-256 identity")
    material = {
        "binding_language": "provider-facts",
        "generator_version": GENERATOR_VERSION,
        "module_identity": abi["module"],
        "interface_identity": abi["interface_identity"],
        "typed_call_schema_version": abi.get("typed_call_schema_version", "mncs.typed-call/1"),
        "functions": abi.get("functions", {}),
        "composites": abi.get("composites", {}),
    }
    import hashlib

    provider_fact_identity = hashlib.sha256(canonical(material).encode("utf-8")).hexdigest()
    providers = [
        {
            "contract_identity": contract,
            "contract_revision": revision,
            "exported_identity": exported,
            "evidence": evidence,
        }
        for contract, revision, exported, evidence in zip(
            args.contract_identity,
            args.contract_revision,
            args.exported_identity,
            args.evidence,
        )
    ]
    output = {
        "schema_version": SCHEMA,
        "repository_id": args.repository_id,
        "authority": {
            "kind": "language-owned-abi",
            "module_identity": abi["module"],
            "interface_identity": abi["interface_identity"],
            "typed_call_schema_version": material["typed_call_schema_version"],
            "generator_version": GENERATOR_VERSION,
            "binding_content_identity": args.binding_content_identity,
            "provider_fact_identity": provider_fact_identity,
        },
        "providers": sorted(providers, key=lambda item: item["contract_identity"]),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
