#!/usr/bin/env python3
"""Run a bounded native/external identity parity corpus.

The corpus is derived from the checked-in native contract declarations so a
field/type change changes the input set instead of silently leaving an old
hand-written fixture behind. Native ``structured_digest`` now uses the same
type-directed external projection as structured publication; this tool keeps
the two authorities executable and exact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_SOURCE = ROOT / "src/mncs_commons/mesh/mncs/commons/family/contracts/v1.mncs"
PROBE_SOURCE = ROOT / "tests/fixtures/native-contract-identity-probe.mncs"
CORPUS_SCHEMA = "commons.contract-identity-corpus/1"
CASE_TYPES = {
    "verification_plan": "VerificationPlan",
    "semantic_impact": "SemanticImpactContract",
    "test_inventory": "TestInventoryContract",
    "semantic_edge": "SemanticEdgeContract",
    "provider_declaration": "ProviderDeclarationContract",
    "test_result": "TestResultContract",
    "check_result": "CheckResultContract",
    "receipt": "ReceiptContract",
    "evidence_manifest": "EvidenceManifestContract",
    "selected_proof": "SelectedProofContract",
}
SELF_FIELDS = {
    "verification_plan": "plan_id",
    "test_result": "result_identity",
    "check_result": "result_identity",
    "receipt": "receipt_identity",
    "evidence_manifest": "evidence_identity",
    "selected_proof": "proof_identity",
}


def parse_declarations(source: str) -> tuple[dict[str, list[tuple[str, str]]], dict[str, list[str]]]:
    records: dict[str, list[tuple[str, str]]] = {}
    for match in re.finditer(r"record\s+(\w+)\s*\{(.*?)\n\}", source, re.DOTALL):
        fields: list[tuple[str, str]] = []
        for line in match.group(2).splitlines():
            line = line.split("//", 1)[0].strip().rstrip(",")
            if not line or ":" not in line:
                continue
            name, type_name = line.split(":", 1)
            fields.append((name.strip(), type_name.strip()))
        records[match.group(1)] = fields
    enums: dict[str, list[str]] = {}
    for match in re.finditer(r"enum\s+(\w+)\s*\{(.*?)\}", source, re.DOTALL):
        enums[match.group(1)] = [
            item.strip().split("{", 1)[0].strip()
            for item in match.group(2).replace("\n", " ").split(",")
            if item.strip()
        ]
    return records, enums


def split_sequence(type_name: str) -> tuple[str, str] | None:
    if not type_name.startswith("[") or not type_name.endswith("]"):
        return None
    inner = type_name[1:-1]
    depth = 0
    for index, character in enumerate(inner):
        if character == "[":
            depth += 1
        elif character == "]":
            depth -= 1
        elif character == ";" and depth == 0:
            return inner[:index].strip(), inner[index + 1 :].strip()
    raise ValueError(f"invalid sequence type: {type_name}")


def unqualified(type_name: str) -> str:
    return type_name.rsplit(".", 1)[-1]


def bound_size(bound: str) -> tuple[int, bool]:
    if bound.startswith("up_to "):
        return int(bound.removeprefix("up_to ")), True
    return int(bound), False


def readable_bytes(field: str) -> bytes:
    values = {
        "path": b"source.mncs",
        "schema_version": b"mncs.verification-plan/1",
        "required_evidence": b"selected_test_cases_pass",
        "risk_flags": b"high_connectivity",
        "revision": b"phase6",
        "capabilities": b"provider_digest",
        "check_identity": b"mncs-test:check",
        "contract_revision": b"1",
        "provider": b"mncs-test",
        "policy": b"bounded-impact-v1",
    }
    return values.get(field, f"mncs:{field}:phase6".encode())


def external_value(
    type_name: str,
    field: str,
    records: dict[str, list[tuple[str, str]]],
    enums: dict[str, list[str]],
) -> Any:
    sequence = split_sequence(type_name)
    if sequence is not None:
        element, bound = sequence
        size, up_to = bound_size(bound)
        if element == "byte":
            raw = readable_bytes(field)
            if not up_to:
                raw = bytes([0x11]) * size
            elif len(raw) > size:
                raw = raw[:size]
            if not raw:
                raw = b"x"
            if not up_to and size == 32:
                return raw.hex()
            try:
                return raw.decode("ascii")
            except UnicodeDecodeError:
                return list(raw)
        count = 1 if up_to else size
        return [external_value(element, field, records, enums) for _ in range(count)]
    simple = unqualified(type_name)
    if simple == "bool":
        return False
    if simple in {"u64", "i64"}:
        return 1 if field.endswith("count") else 0
    if simple == "byte":
        return 1
    if simple in enums:
        return enums[simple][0]
    if simple in records:
        return {
            name: external_value(nested_type, name, records, enums)
            for name, nested_type in records[simple]
        }
    raise ValueError(f"unknown contract type {type_name!r} for {field}")


def host_value(type_name: str, value: Any, records: dict[str, list[tuple[str, str]]], enums: dict[str, list[str]]) -> Any:
    sequence = split_sequence(type_name)
    if sequence is not None:
        element, bound = sequence
        if isinstance(value, str):
            raw = bytes.fromhex(value) if len(value) == 64 and not any(c not in "0123456789abcdef" for c in value) else value.encode()
            return {"sequence": {"values": [{"byte": {"value": item}} for item in raw]}}
        return {"sequence": {"values": [host_value(element, item, records, enums) for item in value]}}
    simple = unqualified(type_name)
    if simple == "bool":
        return {"boolean": {"value": value}}
    if simple in {"u64", "i64"}:
        return {"integer": {"value": value}}
    if simple == "byte":
        return {"byte": {"value": value}}
    if simple in enums:
        return {"finite": {"type": simple, "variant": value, "payload": {}}}
    if simple in records:
        return {
            "record": {
                "type": simple,
                "fields": {
                    name: host_value(nested_type, value[name], records, enums)
                    for name, nested_type in records[simple]
                },
            }
        }
    raise ValueError(f"unknown host contract type {type_name!r}")


def call_native(mncs: Path, args: dict[str, Any]) -> dict[str, str]:
    environment = dict(os.environ)
    language_root = ROOT.parent / "mncs-language"
    environment["MNCS_LIBRARY_PATH"] = ":".join(
        [str(language_root / "library"), str(ROOT / "src/mncs_commons/mesh")]
    )
    completed = subprocess.run(
        [
            str(mncs),
            "call",
            str(PROBE_SOURCE),
            "--module",
            "tests.native_contract_identity_probe",
            "--function",
            "all",
            "--args-json",
            json.dumps([args], separators=(",", ":")),
            "--library",
            str(language_root / "library"),
            "--library",
            str(ROOT / "src/mncs_commons/mesh"),
            "--grant-structured",
            "contract_digest",
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr or completed.stdout)
    report = json.loads(completed.stdout)
    returned = report["call"]["returned"][0]["record"]["fields"]
    values = {name: value for name, value in returned}
    result: dict[str, str] = {}
    for name in CASE_TYPES:
        bytes_value = [item["byte"]["value"] for item in values[name]["sequence"]["values"]]
        result[name] = bytes(bytes_value).hex()
    return result


def external_identity(name: str, value: dict[str, Any]) -> str:
    projection = json.loads(json.dumps(value))
    if name == "verification_plan":
        projection["schema_version"] = "mncs.verification-plan/1"
    self_field = SELF_FIELDS.get(name)
    if self_field:
        projection.pop(self_field, None)
    encoded = json.dumps(
        projection, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_corpus() -> tuple[dict[str, Any], dict[str, list[tuple[str, str]]], dict[str, list[str]]]:
    contract_source = CONTRACT_SOURCE.read_text(encoding="utf-8")
    probe_source = PROBE_SOURCE.read_text(encoding="utf-8")
    records, enums = parse_declarations(contract_source)
    probe_records, probe_enums = parse_declarations(probe_source)
    records.update(probe_records)
    enums.update(probe_enums)
    corpus: dict[str, Any] = {}
    host_fields: dict[str, Any] = {}
    for name, type_name in CASE_TYPES.items():
        external = external_value(type_name, type_name, records, enums)
        corpus[name] = external
        host_fields[name] = host_value(type_name, external, records, enums)
    return host_fields, corpus, enums


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mncs", required=True, type=Path)
    parser.add_argument("--require-parity", action="store_true")
    args = parser.parse_args()
    host_fields, corpus, _ = build_corpus()
    native = call_native(args.mncs, {"record": {"type": "ContractIdentityCorpus", "fields": host_fields}})
    cases = []
    for name in CASE_TYPES:
        external = external_identity(name, corpus[name])
        cases.append(
            {
                "name": name,
                "external_identity": external,
                "native_identity": native[name],
                "parity": external == native[name],
            }
        )
    report = {
        "schema_version": CORPUS_SCHEMA,
        "external_algorithm": "sha256(canonical-json-contract-projection):hex-lowercase-v1",
        "native_operation": "structured_digest(identity-material)",
        "cases": cases,
        "summary": {
            "case_count": len(cases),
            "parity_count": sum(case["parity"] for case in cases),
            "mismatch_count": sum(not case["parity"] for case in cases),
        },
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    if args.require_parity and report["summary"]["mismatch_count"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
