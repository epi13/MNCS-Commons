"""Deterministic, inert Commons Bundle interchange artifacts."""

from __future__ import annotations

import json
import stat
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from .canonical import canonical_digest, canonical_json
from .diagnostics import Diagnostic
from .store import CommonsStore, StoreError
from .validation import validate_event, validate_record

BUNDLE_VERSION = "commons-bundle/v0alpha1"
MAX_BUNDLE_FILES = 2_000
MAX_BUNDLE_MEMBER_BYTES = 8 * 1024 * 1024
MAX_BUNDLE_BYTES = 64 * 1024 * 1024


class BundleError(ValueError):
    """A malformed, unsafe, or incompatible bundle."""


@dataclass(frozen=True, slots=True)
class BundleVerification:
    valid: bool
    manifest: Mapping[str, Any] | None
    diagnostics: tuple[Diagnostic, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "valid": self.valid,
            "manifest": self.manifest,
            "diagnostics": [item.as_dict() for item in self.diagnostics],
        }


def _bundle_digest(manifest: Mapping[str, Any]) -> str:
    value = dict(manifest)
    value.pop("bundleDigest", None)
    return canonical_digest(value, projected=False)


def _zip_info(path: str, data: bytes) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_STORED
    info.external_attr = (stat.S_IFREG | 0o644) << 16
    info.file_size = len(data)
    return info


def _safe_member_name(name: str) -> bool:
    path = Path(name)
    return bool(name) and not path.is_absolute() and ".." not in path.parts and "\\" not in name


def _record_ref(value: Mapping[str, Any]) -> str:
    return str(value.get("contentDigest"))


def _closure(
    records: list[Mapping[str, Any]], roots: Iterable[str] | None, max_depth: int
) -> list[Mapping[str, Any]]:
    by_ref: dict[str, Mapping[str, Any]] = {}
    for record in records:
        by_ref[_record_ref(record)] = record
        metadata = record.get("metadata")
        if isinstance(metadata, Mapping) and metadata.get("recordId"):
            by_ref[str(metadata["recordId"])] = record
    selected = set(roots or [_record_ref(record) for record in records])
    queue = [(item, 0) for item in sorted(selected)]
    found: dict[str, Mapping[str, Any]] = {}
    while queue:
        reference, depth = queue.pop(0)
        candidate_record = by_ref.get(reference)
        if candidate_record is None:
            continue
        digest = _record_ref(candidate_record)
        if digest in found:
            continue
        found[digest] = candidate_record
        if depth >= max_depth:
            continue
        for relation in candidate_record.get("relationships", []):
            if isinstance(relation, Mapping) and isinstance(relation.get("target"), str):
                queue.append((relation["target"], depth + 1))
    return sorted(found.values(), key=_record_ref)


def create_bundle(
    store: CommonsStore,
    output: Path | str,
    *,
    roots: Iterable[str] | None = None,
    max_depth: int = 2,
) -> Mapping[str, Any]:
    """Write a deterministic ZIP bundle; no source content is fetched or run."""

    if max_depth < 0:
        raise BundleError("bundle graph depth cannot be negative")
    destination = Path(output)
    if destination.exists():
        raise BundleError(f"bundle already exists: {destination}")
    root_refs = tuple(sorted(set(roots))) if roots is not None else None
    records = _closure(list(store.records()), root_refs, max_depth)
    selected = {_record_ref(record) for record in records}
    events = [
        event
        for event in store.events()
        if str(event.get("target", {}).get("contentDigest")) in selected
    ]
    members: list[dict[str, Any]] = []
    content: dict[str, bytes] = {}
    for record in records:
        digest = _record_ref(record)
        path = f"records/{digest.removeprefix('sha256:')}.json"
        data = canonical_json(record)
        content[path] = data
        members.append({"path": path, "kind": "record", "contentDigest": digest, "size": len(data)})
    for order, event in enumerate(events):
        digest = str(event.get("contentDigest"))
        path = f"events/{digest.removeprefix('sha256:')}.json"
        data = canonical_json(event)
        content[path] = data
        members.append(
            {
                "path": path,
                "kind": "event",
                "contentDigest": digest,
                "size": len(data),
                "order": order,
            }
        )
    external: set[str] = set()
    if root_refs is not None:
        external.update(reference for reference in root_refs if reference not in selected)
    for record in records:
        for relation in record.get("relationships", []):
            if isinstance(relation, Mapping) and isinstance(relation.get("target"), str):
                if relation["target"] not in selected:
                    external.add(relation["target"])
        for evidence in record.get("evidence", []):
            if isinstance(evidence, Mapping) and isinstance(evidence.get("id"), str):
                external.add(evidence["id"])
    manifest: dict[str, Any] = {
        "bundleVersion": BUNDLE_VERSION,
        "roots": list(root_refs) if root_refs is not None else sorted(selected),
        "maxDepth": max_depth,
        "members": sorted(members, key=lambda item: str(item["path"])),
        "externalReferences": sorted(external),
        "security": {
            "instructionsAreUntrusted": True,
            "fetchExternalReferences": False,
            "executeContent": False,
        },
    }
    manifest["bundleDigest"] = _bundle_digest(manifest)
    manifest_bytes = canonical_json(manifest)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", allowZip64=False) as archive:
        archive.writestr(_zip_info("manifest.json", manifest_bytes), manifest_bytes)
        for path in sorted(content):
            archive.writestr(_zip_info(path, content[path]), content[path])
    return manifest


def _read_members(bundle: Path) -> tuple[Mapping[str, Any], dict[str, bytes]]:
    if bundle.stat().st_size > MAX_BUNDLE_BYTES:
        raise BundleError("bundle exceeds total size limit")
    with zipfile.ZipFile(bundle, "r") as archive:
        infos = archive.infolist()
        if len(infos) > MAX_BUNDLE_FILES:
            raise BundleError("bundle exceeds file-count limit")
        names: set[str] = set()
        data: dict[str, bytes] = {}
        total = 0
        for info in infos:
            if not _safe_member_name(info.filename) or info.filename in names:
                raise BundleError(f"unsafe or duplicate bundle path: {info.filename!r}")
            names.add(info.filename)
            mode = (info.external_attr >> 16) & 0o170000
            if mode == stat.S_IFLNK:
                raise BundleError(f"symbolic links are not allowed in bundles: {info.filename}")
            if info.file_size > MAX_BUNDLE_MEMBER_BYTES:
                raise BundleError(f"bundle member exceeds size limit: {info.filename}")
            total += info.file_size
            if total > MAX_BUNDLE_BYTES:
                raise BundleError("bundle members exceed total size limit")
            data[info.filename] = archive.read(info)
    if set(data) != {"manifest.json"} and "manifest.json" not in data:
        raise BundleError("bundle manifest is missing")
    manifest_value = json.loads(data["manifest.json"].decode("utf-8"))
    if not isinstance(manifest_value, Mapping):
        raise BundleError("bundle manifest must be an object")
    if canonical_json(manifest_value) != data["manifest.json"]:
        raise BundleError("bundle manifest is not canonical JSON")
    return manifest_value, data


def verify_bundle(bundle: Path | str) -> BundleVerification:
    path = Path(bundle)
    try:
        manifest, data = _read_members(path)
        diagnostics: list[Diagnostic] = []
        if manifest.get("bundleVersion") != BUNDLE_VERSION:
            diagnostics.append(
                Diagnostic(
                    "UNSUPPORTED_BUNDLE_VERSION",
                    "bundleVersion",
                    "bundle version is unsupported",
                )
            )
        if manifest.get("bundleDigest") != _bundle_digest(manifest):
            diagnostics.append(
                Diagnostic("BUNDLE_DIGEST_MISMATCH", "bundleDigest", "manifest digest is wrong")
            )
        members = manifest.get("members")
        if not isinstance(members, list) or len(members) > MAX_BUNDLE_FILES:
            raise BundleError("bundle members must be a bounded list")
        seen: set[str] = set()
        for member in members:
            if not isinstance(member, Mapping):
                raise BundleError("bundle member must be an object")
            member_path = str(member.get("path", ""))
            if not _safe_member_name(member_path) or member_path in seen:
                raise BundleError(f"invalid bundle member path: {member_path!r}")
            seen.add(member_path)
            if member_path == "manifest.json" or member_path not in data:
                raise BundleError(f"bundle member is missing: {member_path}")
            member_kind = member.get("kind")
            if member_kind not in {"record", "event"}:
                raise BundleError(f"unsupported bundle member kind: {member_kind!r}")
            expected_prefix = "events/" if member_kind == "event" else "records/"
            if not member_path.startswith(expected_prefix):
                raise BundleError(f"bundle member path does not match kind: {member_path}")
            raw = data[member_path]
            if len(raw) != member.get("size"):
                raise BundleError(f"bundle member size mismatch: {member_path}")
            value = json.loads(raw.decode("utf-8"))
            if not isinstance(value, Mapping) or canonical_json(value) != raw:
                raise BundleError(f"bundle member is not canonical JSON: {member_path}")
            expected = str(member.get("contentDigest"))
            if canonical_digest(value) != expected:
                raise BundleError(f"bundle member digest mismatch: {member_path}")
            report = (
                validate_event(value)
                if member_kind == "event"
                else validate_record(value)
            )
            if not report.valid:
                diagnostics.extend(
                    Diagnostic(item.code, f"{member_path}.{item.path}", item.message)
                    for item in report.diagnostics
                )
        if seen != set(data) - {"manifest.json"}:
            raise BundleError("bundle contains unlisted content")
        return BundleVerification(not diagnostics, manifest, tuple(diagnostics))
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        zipfile.BadZipFile,
        json.JSONDecodeError,
    ) as error:
        return BundleVerification(
            False, None, (Diagnostic("BUNDLE_INVALID", str(path), str(error)),)
        )


def import_bundle(bundle: Path | str, store: CommonsStore) -> BundleVerification:
    verification = verify_bundle(bundle)
    if not verification.valid or verification.manifest is None:
        return verification
    try:
        manifest, data = _read_members(Path(bundle))
        members = list(manifest["members"])
        for member in sorted(
            members,
            key=lambda item: (
                item.get("kind") != "record",
                item.get("order", -1),
                item["path"],
            ),
        ):
            value = json.loads(data[member["path"]].decode("utf-8"))
            if member["kind"] == "event":
                store.add_event(value)
            else:
                store.add_record(value)
        return verification
    except (
        OSError,
        StoreError,
        ValueError,
        KeyError,
        TypeError,
        json.JSONDecodeError,
    ) as error:
        return BundleVerification(
            False,
            verification.manifest,
            (Diagnostic("BUNDLE_IMPORT_FAILED", str(bundle), str(error)),),
        )
