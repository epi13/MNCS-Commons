"""Canonical family-wide MNCS development-pressure registry.

The pressure exchange is deliberately separate from the transport-neutral
Commons record protocol.  A pressure is a family coordination object with a
stable human-facing id; observations, verifications, and lifecycle changes are
append-only documents around that object.  This keeps Git merges small and
preserves every reporter's evidence instead of rewriting one shared ledger.

The module is intentionally conservative.  Record content is data, not
authority: reproduction instructions, URLs, source attachments, and suggested
actions are never executed here.  PASS, FAIL, and UNKNOWN remain distinct.
"""

from __future__ import annotations

import copy
import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from .canonical import canonical_json
from .family_registry import canonical_project_identity

PRESSURE_SCHEMA = "commons.mncs.dev/family-pressure/v1"
OBSERVATION_SCHEMA = "commons.mncs.dev/family-pressure-observation/v1"
EVENT_SCHEMA = "commons.mncs.dev/family-pressure-event/v1"
REPOSITORY_SCHEMA = "commons.mncs.dev/family-repository/v1"
PRESSURE_VERSION = "1"

TARGETS = frozenset(
    {
        "language",
        "compiler",
        "runtime",
        "library",
        "tooling",
        "backend",
        "verification",
        "profile",
        "ecosystem",
    }
)
SEVERITIES = frozenset({"blocker", "blocking", "critical", "major", "moderate", "minor"})
STATUSES = frozenset(
    {
        "discovered",
        "confirmed",
        "accepted",
        "implementing",
        "available",
        "verifying",
        "resolved",
        "duplicate",
        "rejected",
        "superseded",
        "deferred",
        "obsolete",
        "conflicted",
    }
)
TERMINAL_STATUSES = frozenset({"resolved", "duplicate", "rejected", "superseded", "obsolete"})
EVIDENCE_STATUSES = frozenset({"PASS", "FAIL", "UNKNOWN"})
# These are deliberately projection vocabulary, not lifecycle states.  A
# pressure remains append-only and its lifecycle still answers whether the
# declaration is open; reconciliation answers what the latest current
# evidence says about the declaration's relationship to today's language.
RECONCILIATION_CLASSES = frozenset(
    {
        "STILL_REPRODUCES",
        "PARTIALLY_RESOLVED",
        "CAPABILITY_AVAILABLE_CONSUMER_NOT_MIGRATED",
        "BACKEND_ONLY",
        "CONSUMER_DEBT",
        "OBSOLETE",
        "DUPLICATE",
        "RESOLVED",
        "UNRECONCILED",
    }
)
_RECONCILIATION_ALIASES = {
    "still_real": "STILL_REPRODUCES",
    "still_reproduces": "STILL_REPRODUCES",
    "partially_resolved": "PARTIALLY_RESOLVED",
    "resolved_upstream": "RESOLVED",
    "reframed": "PARTIALLY_RESOLVED",
}
RELATIONS = frozenset(
    {
        "duplicate_of",
        "duplicate_candidate",
        "same_root_cause",
        "related_to",
        "parent_of",
        "child_of",
        "blocked_by",
        "supersedes",
        "implements",
        "reframes",
    }
)
PREFIXES = {
    "language": "LANG",
    "compiler": "COMPILER",
    "runtime": "RUNTIME",
    "library": "LIB",
    "tooling": "TOOLING",
    "backend": "BACKEND",
    "verification": "VERIFY",
    "profile": "PROFILE",
    "ecosystem": "ECO",
}

_ID_RE = re.compile(r"^MNCS-[A-Z0-9]+-[A-F0-9]{12}$")
_ALIAS_RE = re.compile(r"^[A-Za-z0-9_.:/-]{1,180}$")
_INSTANT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")
_MARKER_RE = re.compile(r"(?im)\bmncs-pressure\s*:\s*(MNCS-[A-Z0-9]+-[A-F0-9]{12})\b")


class PressureError(ValueError):
    """A fail-closed pressure operation error."""


@dataclass(frozen=True, slots=True)
class PressureDiagnostic:
    code: str
    path: str
    message: str
    severity: str = "error"

    def as_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "path": self.path,
            "message": self.message,
            "severity": self.severity,
        }


@dataclass(frozen=True, slots=True)
class PressureValidationReport:
    diagnostics: tuple[PressureDiagnostic, ...] = ()

    @property
    def valid(self) -> bool:
        return not any(item.severity == "error" for item in self.diagnostics)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": PRESSURE_SCHEMA,
            "valid": self.valid,
            "diagnostics": [item.as_dict() for item in self.diagnostics],
        }


@dataclass(frozen=True, slots=True)
class PressureProjection:
    """Materialized, read-only view of one declaration and its append-only data."""

    data: Mapping[str, Any]
    events: tuple[Mapping[str, Any], ...]
    observations: tuple[Mapping[str, Any], ...]
    relations: tuple[Mapping[str, Any], ...]
    diagnostics: tuple[PressureDiagnostic, ...] = ()
    transition_material: tuple[Mapping[str, Any], ...] = ()

    @property
    def valid(self) -> bool:
        return not any(item.severity == "error" for item in self.diagnostics)

    @property
    def id(self) -> str:
        return str(self.data["id"])

    @property
    def status(self) -> str:
        return str(self.data.get("status", "conflicted"))

    def as_dict(self) -> dict[str, Any]:
        value = copy.deepcopy(dict(self.data))
        value["events"] = copy.deepcopy(list(self.events))
        value["observations"] = copy.deepcopy(list(self.observations))
        value["relations"] = copy.deepcopy(list(self.relations))
        value["valid"] = self.valid
        value["diagnostics"] = [item.as_dict() for item in self.diagnostics]
        return value


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _instant(value: object, *, allow_none: bool = True) -> bool:
    if value is None and allow_none:
        return True
    if not isinstance(value, str) or not _INSTANT_RE.fullmatch(value):
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _instant_key(value: object) -> datetime:
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
        except ValueError:
            pass
    return datetime.min.replace(tzinfo=timezone.utc)


def _current_verifications(
    observations: Iterable[Mapping[str, Any]],
) -> dict[str, Mapping[str, Any]]:
    """Return one current verification per canonical repository.

    Verification observations remain append-only provenance. Projection and
    resolution describe the current state of each logical consumer, so an
    alias observation followed by its canonical repository observation must
    not count twice.
    """

    current: dict[str, Mapping[str, Any]] = {}
    ordered = sorted(
        (item for item in observations if item.get("kind") == "verification"),
        key=lambda item: (_instant_key(item.get("observedAt")), str(item.get("id", ""))),
    )
    for item in ordered:
        repository = normalize_repository(item.get("repository"))
        if repository is not None:
            current[repository] = item
    return current


def _reconciliation(projection_observations: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Materialize the latest explicit pressure reconciliation.

    Reconciliation is evidence metadata carried by append-only observations;
    it is never inferred from a PASS/FAIL result or used as a lifecycle
    transition.  Older campaign observations used lowercase labels, so the
    projection normalizes those aliases without rewriting historical files.
    """

    candidates: list[tuple[datetime, str, str, Mapping[str, Any]]] = []
    for item in projection_observations:
        metadata = item.get("metadata")
        if not isinstance(metadata, Mapping):
            continue
        raw = metadata.get("classification")
        if not isinstance(raw, str):
            continue
        normalized = _RECONCILIATION_ALIASES.get(raw.strip().lower(), raw.strip().upper())
        if normalized not in RECONCILIATION_CLASSES or normalized == "UNRECONCILED":
            continue
        candidates.append(
            (_instant_key(item.get("observedAt")), str(item.get("id", "")), normalized, item)
        )
    if not candidates:
        return {"classification": "UNRECONCILED"}
    _when, observation_id, classification, item = max(
        candidates, key=lambda value: (value[0], value[1])
    )
    return {
        "classification": classification,
        "observationId": observation_id,
        "observedAt": item.get("observedAt"),
        "repository": item.get("repository"),
        "summary": item.get("summary", ""),
    }


def _text(value: object, field: str, *, required: bool = True, maximum: int = 4096) -> str | None:
    if not isinstance(value, str):
        if required:
            raise PressureError(f"{field} must be a non-empty string")
        return None
    result = value.strip()
    if required and not result:
        raise PressureError(f"{field} must be a non-empty string")
    if len(result) > maximum:
        raise PressureError(f"{field} exceeds {maximum} characters")
    return result or None


def _list(value: object, field: str, *, maximum: int = 256) -> list[Any]:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > maximum:
        raise PressureError(f"{field} must be a list with at most {maximum} entries")
    return list(value)


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "unknown"


def _digest_id(prefix: str, payload: Mapping[str, Any]) -> str:
    digest = hashlib.sha256(canonical_json(payload)).hexdigest()[:12].upper()
    return f"MNCS-{prefix}-{digest}"


def pressure_id(target: str, domain: str, capability: str, reproducer_signature: str) -> str:
    """Derive an allocation-free global id from stable pressure identity fields."""

    if target not in PREFIXES:
        raise PressureError(f"unknown pressure target: {target}")
    return _digest_id(
        PREFIXES[target],
        {
            "target": target,
            "domain": domain.strip(),
            "capability": capability.strip(),
            "reproducerSignature": reproducer_signature.strip(),
        },
    )


def _repository_aliases() -> dict[str, str]:
    # The existing family registry is authoritative for its projects.  The
    # pressure exchange adds the downstream consumers that are intentionally
    # not work-queue members of the older v0alpha1 registry.
    aliases: dict[str, str] = {}
    extras = {
        "mncs-compiler": "mncs-compiler",
        "mncs-numerics": "mncs-numerics",
        "mncs-store": "mncs-store",
        "mncs-ingest": "mncs-ingest",
        "mncs-web": "mncs-web",
        "mncs-doctor": "mncs-doctor",
        "mncs-ravel": "ravel",
        "mncs-forge": "mncs-forge",
        "mncs-signal": "mncs-signal",
        "mncs-data": "mncs-data",
        "mncs-engine": "mncs-engine",
        "mncs-index": "mncs-index",
        "mncs-geometry": "mncs-geometry",
        "mncs-math": "mncs-math",
        "mncs-physics": "mncs-physics",
        "mncs-doc": "mncs-doc",
        "mncs-test": "mncs-test",
        "mncs-debug": "mncs-debug",
        "mncs-actions": "mncs-actions",
        "mncs-fabric": "mncs-fabric",
        "mncs-lab": "mncs-lab",
        "mncs-commons": "mncs-commons",
        "ravel": "ravel",
        "forge": "mncs-forge",
    }
    aliases.update(extras)
    for project_id in (
        "mncs",
        "mncds",
        "mncs-rights-provenance",
        "mncs-language",
        "mncs-language-service",
        "mncs-validator-rs",
        "mncs-forge",
        "mncs-fabric",
        "mncs-commons",
        "mncs-harness",
        "mncs-control-mcp",
        "mncs-atlas",
        "mncs-reference-studies",
        "ravel",
        "mnel",
        "mncs-lineage",
        "mncs-tui",
        "mncs-test",
        "mncs-debug",
        "mncs-actions",
        "mncs-doc",
    ):
        aliases[project_id] = project_id
    aliases.update(
        {
            "mncs-forge-mcp": "mncs-forge",
            "mncs-control-mcp": "mncs-control-mcp",
            "RAVEL": "ravel",
        }
    )
    return aliases


def normalize_repository(value: object) -> str | None:
    """Resolve a family spelling without accepting arbitrary command input."""

    if not isinstance(value, str) or not value.strip():
        return None
    submitted = value.strip()
    identity = canonical_project_identity(submitted)
    if identity is not None:
        return str(identity["projectId"])
    aliases = _repository_aliases()
    if submitted in aliases:
        return aliases[submitted]
    lowered = submitted.lower().removesuffix(".git")
    if lowered in aliases:
        return aliases[lowered]
    if lowered.startswith("epi13/"):
        repo = lowered.split("/", 1)[1]
        if repo in aliases:
            return aliases[repo]
    return None


def known_repositories() -> list[dict[str, Any]]:
    """Return the pressure protocol's broad, descriptive family identity view."""

    import json
    from importlib import resources

    try:
        value = json.loads(
            resources.files("mncs_commons")
            .joinpath("data/pressure-repositories-v1.json")
            .read_text(encoding="utf-8")
        )
        repositories = value.get("repositories") if isinstance(value, Mapping) else None
        if isinstance(repositories, list) and all(
            isinstance(item, Mapping) for item in repositories
        ):
            return copy.deepcopy(repositories)
    except (OSError, ValueError, TypeError):
        pass
    names = sorted(set(_repository_aliases().values()))
    return [
        {
            "id": name,
            "repository": f"epi13/{'RAVEL' if name == 'ravel' else name}",
            "role": "family participant",
            "authority": "descriptive-only",
        }
        for name in names
    ]


def _require_repository(value: object, field: str = "repository") -> str:
    result = normalize_repository(value)
    if result is None:
        raise PressureError(f"{field} is not a known MNCS family repository: {value!r}")
    return result


def source_marker(pressure: str) -> str:
    """Return the lightweight source comment used to link a workaround."""

    if not _ID_RE.fullmatch(pressure):
        raise PressureError(f"invalid pressure id: {pressure}")
    return f"mncs-pressure: {pressure}"


def extract_pressure_markers(text: str) -> tuple[str, ...]:
    """Extract inert source markers; this function never dereferences them."""

    return tuple(sorted(set(_MARKER_RE.findall(text))))


def _evidence_status(entry: Mapping[str, Any]) -> str | None:
    value = entry.get("status", entry.get("verdict"))
    return str(value) if value in EVIDENCE_STATUSES else None


def _hash_document(document: Mapping[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(document)).hexdigest()


def _with_digest(document: dict[str, Any]) -> dict[str, Any]:
    document["contentDigest"] = _hash_document(
        {key: value for key, value in document.items() if key != "contentDigest"}
    )
    return document


def _read_json(path: Path) -> Mapping[str, Any]:
    import json

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise PressureError(f"cannot read {path}: {error}") from error
    if not isinstance(value, Mapping):
        raise PressureError(f"{path} must contain a JSON object")
    return value


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    import json

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )


def _sorted_unique_strings(values: Iterable[object]) -> list[str]:
    return sorted({str(item).strip() for item in values if isinstance(item, str) and item.strip()})


def _observation_id(pressure: str, value: Mapping[str, Any]) -> str:
    return f"{pressure}--OBS-{hashlib.sha256(canonical_json(value)).hexdigest()[:12].upper()}"


def _event_id(value: Mapping[str, Any]) -> str:
    return f"EVT-{hashlib.sha256(canonical_json(value)).hexdigest()[:16].upper()}"


def _load_legacy_sections(text: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    matches = list(re.finditer(r"(?m)^##?\s+(.+?)\s*$", text))
    for index, match in enumerate(matches):
        heading = match.group(1).strip().lower()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[match.end() : end].strip()
        sections[heading] = body
    return sections


_LEGACY_ID_RE = re.compile(r"\b[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*-\d+\b", re.IGNORECASE)


def _legacy_entries(text: str) -> list[tuple[str, str, str]]:
    """Return pressure entries from a file without interpreting their prose.

    Older family ledgers use both one-file-per-pressure documents and a single
    Markdown ledger containing one ``## PRESSURE-ID`` section per finding.  The
    importer recognizes identifiers only in headings, so an identifier in a
    code block or historical paragraph cannot accidentally create a record.
    """

    headings: list[tuple[str, str, int, int]] = []
    for match in re.finditer(r"(?im)^(?:#{1,3})\s+(.+?)\s*$", text):
        heading = match.group(1).strip()
        identifier = _LEGACY_ID_RE.search(heading)
        if identifier is not None and identifier.group(0).lower() not in {"stage-0", "stage-1"}:
            headings.append((identifier.group(0), heading, match.start(), match.end()))
    entries: list[tuple[str, str, str]] = []
    for index, (legacy_id, heading, start, _end) in enumerate(headings):
        next_start = headings[index + 1][2] if index + 1 < len(headings) else len(text)
        entry_text = text[start:next_start].strip()
        title = re.sub(
            rf"(?i)^(?:pressure\s+finding\s+)?{re.escape(legacy_id)}\s*[—:-]?\s*",
            "",
            heading,
        ).strip()
        if title == heading:
            title = re.sub(rf"(?i)\b{re.escape(legacy_id)}\b\s*[—:-]?\s*", "", heading).strip()
        entries.append((legacy_id, title or legacy_id, entry_text))
    return entries


def _legacy_status(text: str) -> str | None:
    match = re.search(r"(?im)^\s*(?:[-*]\s*)?status\s*:\s*(.+?)\s*$", text)
    return match.group(1).strip() if match else None


def _legacy_labeled(text: str, label: str) -> str:
    """Extract a legacy ``Label: body`` paragraph without executing its text."""

    match = re.search(
        rf"(?im)^{re.escape(label)}(?:\s*\([^\n)]*\))?\s*:\s*",
        text,
    )
    if match is None:
        return ""
    tail = text[match.end() :]
    boundary = re.search(r"(?m)^(?:[A-Z][A-Za-z0-9 /()._-]{2,80}:|#{1,3}\s+)", tail)
    return tail[: boundary.start() if boundary else len(tail)].strip()


def _legacy_title(text: str, fallback: str) -> str:
    entries = _legacy_entries(text)
    if entries:
        return entries[0][1]
    return fallback


def _legacy_domain(title: str, filename: str) -> str:
    haystack = f"{title} {filename}".lower()
    for token, domain in (
        ("filesystem", "io.filesystem"),
        ("file", "io.filesystem"),
        ("effect", "effects"),
        ("backend", "backend"),
        ("generic", "type-system.generics"),
        ("record", "type-system.records"),
        ("view", "type-system.views"),
        ("hash", "integrity.hashing"),
        ("identity", "identity"),
        ("iteration", "control-flow.iteration"),
    ):
        if token in haystack:
            return domain
    return "language-semantics"


def _legacy_capability(legacy_id: str, title: str) -> str:
    # Titles are editorial wording and may be corrected during migration. The
    # local id is the only stable identity available from a legacy document;
    # repository scope is already part of the reproducer signature.
    del title
    return f"legacy.{_slug(legacy_id)}"


def _legacy_severity(text: str) -> str:
    match = re.search(r"(?im)^\s*(?:[-*]\s*)?severity\s*:\s*([^\s#(]+)", text)
    value = match.group(1).lower() if match else ""
    if value in {"blocker", "blocking", "critical"}:
        return value
    if value in {"major", "high"}:
        return "major"
    if value in {"moderate", "medium"}:
        return "moderate"
    if value in {"minor", "low"}:
        return "minor"
    return "blocker" if re.search(r"(?i)\bblocker\b", text) else "major"


def _legacy_fallback_language(text: str) -> str | None:
    """Extract an explicit host fallback without treating arbitrary prose as code."""

    relevant = re.findall(
        r"(?is)(?:workaround|fallback|host[- ](?:side|language)|implemented outside|implemented in)"
        r".{0,500}",
        text,
    )
    joined = "\n".join(relevant).lower()
    if re.search(r"\bpython\b", joined):
        return "python"
    if re.search(r"\brust\b", joined):
        return "rust"
    return None


def _native_transition_allowed(current: str, target: str) -> bool:
    from .pressure_runtime import PressureKernelError, pressure_kernel

    try:
        return pressure_kernel().transition_allowed(current, target)
    except PressureKernelError as error:
        raise PressureError(f"native lifecycle policy failed closed: {error}") from error


def _native_resolution_ready(
    affected: int, passed: int, failed: int, unknown: int, removed: int
) -> bool:
    from .pressure_runtime import PressureKernelError, pressure_kernel

    try:
        return pressure_kernel().resolution_ready(affected, passed, failed, unknown, removed)
    except PressureKernelError as error:
        raise PressureError(f"native resolution policy failed closed: {error}") from error


def _native_verification_state(
    affected: int, passed: int, failed: int, unknown: int, removed: int
) -> int:
    from .pressure_runtime import PressureKernelError, pressure_kernel

    try:
        return pressure_kernel().verification_state(affected, passed, failed, unknown, removed)
    except PressureKernelError as error:
        raise PressureError(f"native verification classification failed closed: {error}") from error


def _native_requires_revalidation(unresolved: bool, current_validation: bool) -> bool:
    from .pressure_runtime import PressureKernelError, pressure_kernel

    try:
        return pressure_kernel().requires_revalidation(unresolved, current_validation)
    except PressureKernelError as error:
        raise PressureError(f"native revalidation classification failed closed: {error}") from error


def _native_available_awaiting_consumer(status: int, current_validation: bool) -> bool:
    from .pressure_runtime import PressureKernelError, pressure_kernel

    try:
        return pressure_kernel().available_awaiting_consumer(status, current_validation)
    except PressureKernelError as error:
        raise PressureError(f"native availability classification failed closed: {error}") from error


def _native_unresolved(status: int) -> bool:
    from .pressure_runtime import PressureKernelError, pressure_kernel

    try:
        return pressure_kernel().unresolved(status)
    except PressureKernelError as error:
        raise PressureError(f"native unresolved classification failed closed: {error}") from error


def _is_current_validation(observation: Mapping[str, Any]) -> bool:
    metadata = observation.get("metadata")
    return isinstance(metadata, Mapping) and metadata.get("currentValidation") is True


def _fallback_languages(projection: "PressureProjection") -> set[str]:
    languages: set[str] = set()
    signals = projection.data.get("signals")
    if isinstance(signals, Mapping):
        language = signals.get("fallbackLanguage")
        if isinstance(language, str) and language.strip():
            languages.add(language.lower().strip())
    for observation in projection.observations:
        workaround = observation.get("workaround")
        if not isinstance(workaround, Mapping):
            continue
        language = workaround.get("fallbackLanguage")
        if isinstance(language, str) and language.strip():
            languages.add(language.lower().strip())
        description = str(workaround.get("description", "")).lower()
        for candidate in ("python", "rust"):
            if re.search(rf"\b{candidate}\b", description):
                languages.add(candidate)
    return languages


def _bounded_identity_bytes(value: object, field: str) -> list[int]:
    """Encode one open-vocabulary identity; the artifact contract enforces bounds."""

    if not isinstance(value, str):
        raise PressureError(f"{field} must be text at the transport boundary")
    return list(value.encode("utf-8"))


def _projection_row(projection: PressureProjection) -> dict[str, Any]:
    data = projection.as_dict()
    summary = data.get("verificationSummary", {})
    verification = data.get("verificationCurrent", [])
    reconciliation = data.get("reconciliation", {}).get("classification", "UNRECONCILED")
    fallback = _fallback_languages(projection)
    observations = data.get("observations", [])
    profile = data.get("languageProfile")
    profiles = sorted(
        {
            item["languageProfile"]
            for item in observations
            if isinstance(item, Mapping) and isinstance(item.get("languageProfile"), str)
        }
    )
    removed = sum(
        item.get("workaround", {}).get("removed", "not_needed") in {True, "not_needed"}
        for item in verification
        if isinstance(item, Mapping)
    )
    workaround_active = any(
        item.get("workaround", {}).get("active", True) is not False
        for item in data.get("workarounds", [])
        if isinstance(item, Mapping)
    )
    affected = sorted(data.get("affectedRepositories", []))
    reporters = sorted(data.get("reporters", []))
    return {
        "pressure_identity": _bounded_identity_bytes(projection.id, "pressure id"),
        "target": str(data.get("target", "language")).upper(),
        "domain_identity": _bounded_identity_bytes(str(data.get("domain", "")), "domain"),
        "severity": str(data.get("severity", "minor")).upper(),
        "initial_status": str(data.get("initialStatus", "discovered")).upper(),
        "transitions": [
            {
                "event_identity": _bounded_identity_bytes(
                    str(event.get("id", "")), "pressure event id"
                ),
                "previous_event_identity": _bounded_identity_bytes(
                    str(event.get("previousEvent") or ""), "previous pressure event id"
                ),
                "from_status": str(event.get("from", "discovered")).upper(),
                "to_status": str(event.get("to", "discovered")).upper(),
            }
            for event in projection.transition_material
        ],
        "affected_repositories": [
            _bounded_identity_bytes(item, "affected repository") for item in affected
        ],
        "reporters": [_bounded_identity_bytes(item, "reporter") for item in reporters],
        "verification_affected": int(summary.get("affected", 0)),
        "verification_pass": int(summary.get("pass", 0)),
        "verification_fail": int(summary.get("fail", 0)),
        "verification_unknown": int(summary.get("unknown", 0)),
        "workarounds_removed": removed,
        "current_validation": any(
            _is_current_validation(item)
            for item in observations
            if isinstance(item, Mapping)
        ),
        "workaround_active": workaround_active,
        "fallback_rust": "rust" in fallback,
        "fallback_python": "python" in fallback,
        "language_profile": _bounded_identity_bytes(profile or "", "language profile"),
        "observation_language_profiles": [
            _bounded_identity_bytes(item, "observation language profile") for item in profiles
        ],
        "reconciliation": str(reconciliation).upper(),
        "valid": projection.valid,
    }


def _projection_filter(
    *,
    status: str | None,
    target: str | None,
    domain: str | None,
    repository: str | None,
    severity: str | Iterable[str] | None,
    unresolved: bool,
    multi_repository: bool,
    awaiting_verification: bool,
    workaround_active: bool,
    language_profile: str | None,
    rust_fallback: bool,
    python_fallback: bool,
    needs_revalidation: bool,
) -> dict[str, Any]:
    severities = [severity] if isinstance(severity, str) else list(severity or ())
    return {
        "status_enabled": status is not None,
        "status": str(status or "discovered").upper(),
        "target_enabled": target is not None,
        "target": str(target or "language").upper(),
        "domain_enabled": domain is not None,
        "domain_identity": _bounded_identity_bytes(domain or "", "domain selector"),
        "repository_enabled": repository is not None,
        "repository_identity": _bounded_identity_bytes(repository or "", "repository selector"),
        "severities": [str(item).upper() for item in severities],
        "unresolved": unresolved,
        "multi_repository": multi_repository,
        "awaiting_verification": awaiting_verification,
        "workaround_active": workaround_active,
        "language_profile_enabled": language_profile is not None,
        "language_profile": _bounded_identity_bytes(language_profile or "", "profile selector"),
        "rust_fallback": rust_fallback,
        "python_fallback": python_fallback,
        "needs_revalidation": needs_revalidation,
    }


def _materialize_native_rows(
    projections: tuple[PressureProjection, ...], serialized: Mapping[str, Any]
) -> list[dict[str, Any]]:
    source_by_id = {item.id: item for item in projections}

    def decode(value: object) -> str:
        if not isinstance(value, list) or any(
            not isinstance(part, int) or part < 0 or part > 255 for part in value
        ):
            raise PressureError("native pressure kernel returned malformed bounded identity")
        try:
            return bytes(value).decode("utf-8")
        except UnicodeDecodeError as error:
            raise PressureError("native pressure kernel returned invalid identity UTF-8") from error

    native_rows = serialized.get("rows")
    if not isinstance(native_rows, list):
        raise PressureError("native pressure kernel returned malformed query rows")
    result: list[dict[str, Any]] = []
    for row in native_rows:
        if not isinstance(row, Mapping):
            raise PressureError("native pressure kernel returned a malformed row")
        record_id = decode(row.get("pressure_identity"))
        source = source_by_id.get(record_id)
        if source is None:
            raise PressureError("native pressure kernel returned an unknown pressure identity")
        data = source.data
        verification = row.get("verification_summary")
        if not isinstance(verification, Mapping):
            raise PressureError("native pressure kernel omitted verification summary")
        fallback_languages = sorted(
            language
            for language, field in (("rust", "fallback_rust"), ("python", "fallback_python"))
            if row.get(field) is True
        )
        classification = str(row.get("reconciliation", "UNRECONCILED")).lower()
        reconciliation = copy.deepcopy(
            data.get("reconciliation", {"classification": "UNRECONCILED"})
        )
        reconciliation["classification"] = classification.upper()
        result.append(
            {
                "id": record_id,
                "title": data["title"],
                "target": str(row["target"]).lower(),
                "domain": decode(row["domain_identity"]),
                "capability": data["capability"],
                "severity": str(row["severity"]).lower(),
                "status": str(row["status"]).lower(),
                "affectedRepositories": [decode(value) for value in row["affected_repositories"]],
                "reporters": [decode(value) for value in row["reporters"]],
                "verificationSummary": {
                    "affected": verification["affected"],
                    "pass": verification["pass"],
                    "fail": verification["failed"],
                    "unknown": verification["unknown"],
                },
                "verificationState": str(row["verification_state"]).lower(),
                "reconciliation": reconciliation,
                "classification": classification.upper(),
                "unresolved": row["unresolved"],
                "fallbackLanguages": fallback_languages,
                "currentValidation": row["current_validation"],
                "revalidationRequired": row["revalidation_required"],
                "valid": row["valid"],
            }
        )
    return result


class PressureRegistry:
    """Filesystem-backed pressure exchange and deterministic projections."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.records_dir = self.root / "records"
        self.observations_dir = self.root / "observations"
        self.events_dir = self.root / "events"
        self.views_dir = self.root / "views"

    def init(self) -> dict[str, Any]:
        for directory in (self.records_dir, self.observations_dir, self.events_dir, self.views_dir):
            directory.mkdir(parents=True, exist_ok=True)
        _write_json(
            self.root / "repositories.json",
            {
                "schema": REPOSITORY_SCHEMA,
                "version": PRESSURE_VERSION,
                "repositories": known_repositories(),
            },
        )
        return {"initialized": str(self.root), "schema": PRESSURE_SCHEMA}

    def _files(self, directory: Path) -> list[Path]:
        if not directory.exists():
            return []
        return sorted(path for path in directory.glob("*.json") if path.is_file())

    def _documents(
        self,
    ) -> tuple[
        dict[str, Mapping[str, Any]], dict[str, Mapping[str, Any]], dict[str, Mapping[str, Any]]
    ]:
        records = {path.stem: _read_json(path) for path in self._files(self.records_dir)}
        observations = {path.stem: _read_json(path) for path in self._files(self.observations_dir)}
        events = {path.stem: _read_json(path) for path in self._files(self.events_dir)}
        return records, observations, events

    def _write_document(self, directory: Path, filename: str, value: Mapping[str, Any]) -> None:
        _write_json(directory / filename, _with_digest(dict(value)))

    def add(self, spec: Mapping[str, Any]) -> dict[str, Any]:
        self.init()
        target = str(_text(spec.get("target"), "target"))
        if target not in TARGETS:
            raise PressureError(f"target must be one of {sorted(TARGETS)}")
        domain = str(_text(spec.get("domain"), "domain"))
        capability = str(_text(spec.get("capability"), "capability"))
        title = str(_text(spec.get("title"), "title", maximum=240))
        summary = str(_text(spec.get("summary"), "summary"))
        required = str(
            _text(spec.get("requiredBehavior", spec.get("required_behavior")), "requiredBehavior")
        )
        reproducer = spec.get("reproducer")
        if not isinstance(reproducer, Mapping):
            reproducer = {
                "signature": str(_text(spec.get("reproducerSignature"), "reproducerSignature"))
            }
        signature = str(_text(reproducer.get("signature"), "reproducer.signature", maximum=1000))
        severity = str(spec.get("severity", "major"))
        if severity not in SEVERITIES:
            raise PressureError(f"unknown severity: {severity}")
        repository = _require_repository(
            spec.get("discoveredBy", spec.get("discovered_by")), "discoveredBy"
        )
        discovered_at = spec.get("discoveredAt", spec.get("discovered_at", _now()))
        if not _instant(discovered_at):
            raise PressureError("discoveredAt must be an RFC3339 UTC instant or null")
        generated_id = pressure_id(target, domain, capability, signature)
        record_id = str(spec.get("id", generated_id))
        if not _ID_RE.fullmatch(record_id):
            raise PressureError(f"id must match {_ID_RE.pattern}")
        if record_id != generated_id and not spec.get("allowCustomId"):
            raise PressureError(
                "custom ids require allowCustomId=true; generated ids are safer under concurrency"
            )
        destination = self.records_dir / f"{record_id}.json"
        if destination.exists():
            raise PressureError(f"pressure already exists: {record_id}")
        aliases = _list(spec.get("legacyIds", spec.get("legacy_ids")), "legacyIds")
        if any(not isinstance(item, str) or not _ALIAS_RE.fullmatch(item) for item in aliases):
            raise PressureError("legacyIds must contain only bounded identifier strings")
        affected = _sorted_unique_strings(
            spec.get("affectedRepositories", spec.get("affected_repositories", []))
        )
        affected = sorted(set(affected) | {repository})
        for item in affected:
            _require_repository(item, "affectedRepositories")
        identity = {
            "target": target,
            "domain": domain,
            "capability": capability,
            "reproducerSignature": signature,
        }
        record: dict[str, Any] = {
            "schema": PRESSURE_SCHEMA,
            "version": PRESSURE_VERSION,
            "id": record_id,
            "identity": identity,
            "title": title,
            "target": target,
            "domain": domain,
            "capability": capability,
            "severity": severity,
            "initialStatus": "discovered",
            "discoveredBy": repository,
            "discoveredAt": discovered_at,
            "summary": summary,
            "requiredBehavior": required,
            "reproducer": dict(reproducer),
            "affectedRepositories": affected,
            "legacyIds": sorted(set(aliases)),
            "sourceRef": copy.deepcopy(spec.get("sourceRef", spec.get("source_ref", {}))),
            "languageProfile": spec.get("languageProfile", spec.get("language_profile")),
            "signals": copy.deepcopy(spec.get("signals", {})),
            "notes": spec.get("notes"),
        }
        if record_id != generated_id:
            record["allowCustomId"] = True
        if "legacy" in spec:
            record["legacy"] = copy.deepcopy(spec["legacy"])
        self._write_document(self.records_dir, f"{record_id}.json", record)
        observation_spec = spec.get("observation")
        if observation_spec is None:
            observation_spec = {
                "repository": repository,
                "observedAt": discovered_at,
                "summary": summary,
                "reproduction": {
                    "status": "UNKNOWN",
                    "instructions": signature,
                },
                "evidence": [],
            }
        try:
            if not isinstance(observation_spec, Mapping):
                raise PressureError("observation must be an object")
            observation = self.observe(record_id, observation_spec)
        except Exception:
            # Do not leave a declaration behind when its required first
            # observation cannot be appended.  This keeps ``add`` atomic at
            # the single-record boundary without introducing a lock file.
            destination.unlink(missing_ok=True)
            raise
        return {"id": record_id, "record": record, "observation": observation}

    def observe(self, record_id: str, spec: Mapping[str, Any]) -> dict[str, Any]:
        self.init()
        records, _observations, _events = self._documents()
        record = records.get(record_id)
        if record is None:
            raise PressureError(f"pressure not found: {record_id}")
        repository = _require_repository(spec.get("repository"))
        observed_at = spec.get("observedAt", spec.get("observed_at", _now()))
        if not _instant(observed_at):
            raise PressureError("observedAt must be an RFC3339 UTC instant or null")
        reproduction = spec.get("reproduction", {})
        if not isinstance(reproduction, Mapping):
            raise PressureError("reproduction must be an object")
        reproduction_status = reproduction.get("status", "UNKNOWN")
        if reproduction_status not in EVIDENCE_STATUSES:
            raise PressureError("reproduction.status must be PASS, FAIL, or UNKNOWN")
        evidence = _list(spec.get("evidence", []), "evidence")
        for index, entry in enumerate(evidence):
            if not isinstance(entry, Mapping):
                raise PressureError(f"evidence[{index}] must be an object")
            if not _text(entry.get("id"), f"evidence[{index}].id", maximum=240):
                raise PressureError(f"evidence[{index}].id is required")
            if _evidence_status(entry) is None:
                raise PressureError(f"evidence[{index}].status must be PASS, FAIL, or UNKNOWN")
        value: dict[str, Any] = {
            "schema": OBSERVATION_SCHEMA,
            "version": PRESSURE_VERSION,
            "kind": str(spec.get("kind", "observation")),
            "pressureId": record_id,
            "repository": repository,
            "observedAt": observed_at,
            "sourceRef": copy.deepcopy(spec.get("sourceRef", spec.get("source_ref", {}))),
            "agent": copy.deepcopy(spec.get("agent")),
            "runId": spec.get("runId", spec.get("run_id")),
            "languageProfile": spec.get("languageProfile", spec.get("language_profile")),
            "compiler": copy.deepcopy(spec.get("compiler")),
            "summary": str(_text(spec.get("summary", ""), "summary", required=False) or ""),
            "reproduction": copy.deepcopy(dict(reproduction)),
            "evidence": copy.deepcopy(evidence),
            "workaround": copy.deepcopy(spec.get("workaround", {})),
            "metadata": copy.deepcopy(spec.get("metadata", {})),
        }
        observation_id = str(spec.get("id", _observation_id(record_id, value)))
        if not re.fullmatch(r"MNCS-[A-Z0-9]+-[A-F0-9]{12}--OBS-[A-F0-9]{12}", observation_id):
            raise PressureError("observation id is malformed")
        value["id"] = observation_id
        value["contentDigest"] = _hash_document(
            {key: item for key, item in value.items() if key != "contentDigest"}
        )
        destination = self.observations_dir / f"{observation_id}.json"
        if destination.exists():
            existing = _read_json(destination)
            if existing == value:
                return value
            raise PressureError(f"observation already exists: {observation_id}")
        _write_json(destination, value)
        return value

    def verify(
        self,
        record_id: str,
        *,
        repository: str,
        status: str,
        evidence: Iterable[Mapping[str, Any]] = (),
        workaround_removed: bool | str = "not_needed",
        summary: str = "",
        source_ref: Mapping[str, Any] | None = None,
        language_profile: str | None = None,
        compiler: Mapping[str, Any] | None = None,
        observed_at: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if status not in EVIDENCE_STATUSES:
            raise PressureError("verification status must be PASS, FAIL, or UNKNOWN")
        if workaround_removed not in {True, False, "not_needed"}:
            raise PressureError("workaround_removed must be true, false, or not_needed")
        return self.observe(
            record_id,
            {
                "kind": "verification",
                "repository": repository,
                "observedAt": observed_at or _now(),
                "sourceRef": source_ref or {},
                "languageProfile": language_profile,
                "compiler": compiler,
                "summary": summary,
                "reproduction": {
                    "status": status,
                    "instructions": "re-run the originating consumer reproducer",
                },
                "evidence": list(evidence),
                "workaround": {"removed": workaround_removed},
                "metadata": dict(metadata or {}),
            },
        )

    def relate(
        self,
        record_id: str,
        relation: str,
        target_id: str,
        *,
        actor: str,
        evidence_refs: Iterable[str] = (),
        details: Mapping[str, Any] | None = None,
        occurred_at: str | None = None,
    ) -> dict[str, Any]:
        self.init()
        records, _observations, _events = self._documents()
        if record_id not in records or target_id not in records:
            raise PressureError("relation endpoints must name existing pressures")
        if relation not in RELATIONS:
            raise PressureError(f"unknown relation: {relation}")
        if record_id == target_id:
            raise PressureError("a pressure cannot relate to itself")
        actor_repo = _require_repository(actor, "actor")
        value: dict[str, Any] = {
            "schema": EVENT_SCHEMA,
            "version": PRESSURE_VERSION,
            "kind": "PressureRelation",
            "id": "",
            "sourcePressure": record_id,
            "relation": relation,
            "targetPressure": target_id,
            "occurredAt": occurred_at or _now(),
            "actor": actor_repo,
            "evidenceRefs": _sorted_unique_strings(evidence_refs),
            "details": copy.deepcopy(dict(details or {})),
        }
        if not _instant(value["occurredAt"], allow_none=False):
            raise PressureError("occurredAt must be an RFC3339 UTC instant")
        value["id"] = _event_id({key: item for key, item in value.items() if key != "id"})
        self._write_document(self.events_dir, f"{value['id']}.json", value)
        report = self.validate()
        if not report.valid:
            (self.events_dir / f"{value['id']}.json").unlink(missing_ok=True)
            raise PressureError(
                "relation would make the registry invalid: " + _diagnostic_text(report)
            )
        return value

    def transition(
        self,
        record_id: str,
        target: str,
        *,
        actor: str,
        reason: str = "",
        evidence_refs: Iterable[str] = (),
        implementation: Mapping[str, Any] | None = None,
        details: Mapping[str, Any] | None = None,
        expected_previous: str | None = None,
        occurred_at: str | None = None,
    ) -> dict[str, Any]:
        self.init()
        projection = self.show(record_id)
        if not projection.valid:
            raise PressureError(
                "cannot transition an invalid pressure: "
                + _diagnostic_texts(projection.diagnostics)
            )
        current = projection.status
        if target not in STATUSES or target == "conflicted":
            raise PressureError(f"unknown transition target: {target}")
        previous = projection.events[-1]["id"] if projection.events else None
        if expected_previous != previous and expected_previous is not None:
            raise PressureError(
                f"stale pressure head: expected {expected_previous!r}, current is {previous!r}"
            )
        if not _native_transition_allowed(current, target):
            raise PressureError(f"{current} -> {target} is not an allowed transition")
        actor_repo = _require_repository(actor, "actor")
        refs = _sorted_unique_strings(evidence_refs)
        value: dict[str, Any] = {
            "schema": EVENT_SCHEMA,
            "version": PRESSURE_VERSION,
            "kind": "PressureTransition",
            "id": "",
            "pressureId": record_id,
            "previousEvent": previous,
            "from": current,
            "to": target,
            "occurredAt": occurred_at or _now(),
            "actor": actor_repo,
            "reason": str(_text(reason, "reason", required=False, maximum=4000) or ""),
            "evidenceRefs": refs,
            "implementation": copy.deepcopy(dict(implementation or {})),
            "details": copy.deepcopy(dict(details or {})),
        }
        if not _instant(value["occurredAt"], allow_none=False):
            raise PressureError("occurredAt must be an RFC3339 instant")
        validation = self._validate_transition_requirements(projection, value)
        if validation:
            raise PressureError(validation)
        value["id"] = _event_id({key: item for key, item in value.items() if key != "id"})
        self._write_document(self.events_dir, f"{value['id']}.json", value)
        report = self.validate()
        if not report.valid:
            (self.events_dir / f"{value['id']}.json").unlink(missing_ok=True)
            raise PressureError(
                "transition would make the registry invalid: " + _diagnostic_text(report)
            )
        return value

    def _validate_transition_requirements(
        self, projection: PressureProjection, event: Mapping[str, Any]
    ) -> str | None:
        target = str(event["to"])
        refs = set(event.get("evidenceRefs", []))
        observations = {str(item["id"]): item for item in projection.observations}
        if target in {"confirmed", "accepted", "available", "resolved"} and not refs:
            return f"{target} requires evidenceRefs"
        if target == "confirmed":
            if not any(
                item.get("kind") == "observation"
                and item.get("reproduction", {}).get("status") == "PASS"
                for item in projection.observations
            ):
                return "confirmed requires a PASS pressure reproduction observation"
        if target == "accepted" and not str(event.get("reason", "")).strip():
            return "accepted requires a decision reason"
        if target == "implementing" and not str(event.get("reason", "")).strip():
            return "implementing requires a work plan reason"
        if target == "available":
            implementation = event.get("implementation")
            if (
                not isinstance(implementation, Mapping)
                or not str(implementation.get("ref", "")).strip()
            ):
                return "available requires implementation.ref"
        if target == "resolved":
            if not refs or not refs.issubset(observations):
                return "resolved evidenceRefs must point to observations in this pressure"
            verification = _current_verifications(projection.observations)
            affected = set(projection.data.get("affectedRepositories", []))
            if not affected:
                return "resolved requires at least one affected repository"
            missing = sorted(affected - set(verification))
            if missing:
                return (
                    "resolved requires verification from every affected repository: "
                    + ", ".join(missing)
                )
            passed = sum(
                item.get("reproduction", {}).get("status") == "PASS"
                for item in verification.values()
            )
            failed = sum(
                item.get("reproduction", {}).get("status") == "FAIL"
                for item in verification.values()
            )
            unknown = sum(
                item.get("reproduction", {}).get("status") == "UNKNOWN"
                for item in verification.values()
            )
            removed = sum(
                item.get("workaround", {}).get("removed", "not_needed") in {True, "not_needed"}
                for item in verification.values()
            )
            ready = _native_resolution_ready(len(affected), passed, failed, unknown, removed)
            for repository in sorted(affected):
                item = verification[repository]
                if item.get("reproduction", {}).get("status") != "PASS":
                    return f"resolved requires PASS verification from {repository}"
                removed = item.get("workaround", {}).get("removed", "not_needed")
                if removed not in {True, "not_needed"}:
                    return f"resolved requires workaround removal or not_needed from {repository}"
            if not ready:
                return "resolved requires complete PASS verification and workaround closure"
        if target in {"duplicate", "superseded"}:
            required_relation = "duplicate_of" if target == "duplicate" else "supersedes"
            if not any(item.get("relation") == required_relation for item in projection.relations):
                return f"{target} requires a {required_relation} relation first"
        if (
            target in {"rejected", "deferred", "obsolete"}
            and not str(event.get("reason", "")).strip()
        ):
            return f"{target} requires a reason"
        return None

    def _project_one(
        self,
        record_id: str,
        record: Mapping[str, Any],
        observations: Iterable[Mapping[str, Any]],
        events: Iterable[Mapping[str, Any]],
        all_record_ids: set[str],
        *,
        validate_lifecycle: bool = True,
    ) -> PressureProjection:
        diagnostics: list[PressureDiagnostic] = []
        relevant_observations = tuple(
            sorted(
                (item for item in observations if item.get("pressureId") == record_id),
                key=lambda item: str(item.get("id", "")),
            )
        )
        relevant_events = tuple(
            sorted(
                (
                    item
                    for item in events
                    if item.get("pressureId") == record_id
                    or item.get("sourcePressure") == record_id
                    or item.get("targetPressure") == record_id
                ),
                key=lambda item: str(item.get("id", "")),
            )
        )
        relations = tuple(
            item for item in relevant_events if item.get("kind") == "PressureRelation"
        )
        transition_material = tuple(
            item for item in relevant_events if item.get("kind") == "PressureTransition"
        )
        # Read queries transport the append-only transition documents directly
        # to the MNCS fold. The host replay below runs only for explicit history
        # validation and write admission diagnostics.
        transitions = list(transition_material) if validate_lifecycle else []
        state = str(record.get("initialStatus", "discovered"))
        chain: list[Mapping[str, Any]] = []
        by_previous: dict[str | None, list[Mapping[str, Any]]] = {}
        for event in transitions:
            previous = event.get("previousEvent")
            by_previous.setdefault(previous if isinstance(previous, str) else None, []).append(
                event
            )
        current_previous: str | None = None
        seen: set[str] = set()
        while True:
            candidates = by_previous.get(current_previous, [])
            if len(candidates) > 1:
                diagnostics.append(
                    PressureDiagnostic(
                        "CONCURRENT_TRANSITIONS",
                        f"pressure[{record_id}].events",
                        f"{len(candidates)} transitions claim previous event "
                        f"{current_previous!r}; rebase one branch",
                    )
                )
                break
            if not candidates:
                break
            event = candidates[0]
            event_id = str(event.get("id", ""))
            if event_id in seen:
                diagnostics.append(
                    PressureDiagnostic(
                        "EVENT_CYCLE",
                        f"pressure[{record_id}].events",
                        "transition event chain cycles",
                    )
                )
                break
            seen.add(event_id)
            expected = event.get("from")
            if expected != state:
                diagnostics.append(
                    PressureDiagnostic(
                        "STALE_TRANSITION",
                        f"pressure[{record_id}].events[{event_id}].from",
                        f"event expects {expected!r}, projected state is {state!r}",
                    )
                )
                break
            target = str(event.get("to", ""))
            if not _native_transition_allowed(state, target):
                diagnostics.append(
                    PressureDiagnostic(
                        "INVALID_TRANSITION",
                        f"pressure[{record_id}].events[{event_id}]",
                        f"{state} -> {target} is not an allowed transition",
                    )
                )
                break
            pre_data = copy.deepcopy(dict(record))
            pre_data["affectedRepositories"] = sorted(
                {
                    normalize_repository(item) or str(item)
                    for item in record.get("affectedRepositories", [])
                }
                | {
                    normalize_repository(item.get("repository"))
                    or str(item.get("repository"))
                    for item in relevant_observations
                    if isinstance(item.get("repository"), str)
                }
            )
            pre_projection = PressureProjection(
                pre_data,
                tuple(chain),
                relevant_observations,
                relations,
                (),
            )
            requirement = self._validate_transition_requirements(pre_projection, event)
            if requirement:
                diagnostics.append(
                    PressureDiagnostic(
                        "INVALID_TRANSITION_REQUIREMENTS",
                        f"pressure[{record_id}].events[{event_id}]",
                        requirement,
                    )
                )
                break
            chain.append(event)
            state = target
            current_previous = event_id
        if len(seen) != len(transitions):
            diagnostics.append(
                PressureDiagnostic(
                    "DANGLING_TRANSITION",
                    f"pressure[{record_id}].events",
                    "one or more transition events are not on the single append-only head",
                )
            )
        if record_id not in all_record_ids:
            diagnostics.append(
                PressureDiagnostic("MISSING_RECORD", record_id, "pressure declaration is missing")
            )
        data = copy.deepcopy(dict(record))
        reporters = {
            normalize_repository(record.get("discoveredBy"))
            or str(record.get("discoveredBy"))
        }
        affected = {
            normalize_repository(item) or str(item)
            for item in record.get("affectedRepositories", [])
        }
        evidence: list[Mapping[str, Any]] = []
        verifications: list[Mapping[str, Any]] = []
        workarounds: list[Mapping[str, Any]] = []
        for item in relevant_observations:
            repository = item.get("repository")
            if isinstance(repository, str):
                canonical_repository = normalize_repository(repository) or repository
                reporters.add(canonical_repository)
                affected.add(canonical_repository)
            evidence.extend(item.get("evidence", []))
            if item.get("kind") == "verification":
                verifications.append(item)
            workaround = item.get("workaround")
            if isinstance(workaround, Mapping) and workaround:
                workarounds.append(item)
        current_verifications = _current_verifications(relevant_observations)
        reconciliation = _reconciliation(relevant_observations)
        data.update(
            {
            # Python retains detailed admission diagnostics for historical
            # event documents. Production query status is replayed again by
            # the native bounded lifecycle fold.
            "status": state if not diagnostics else "conflicted",
                "reporters": sorted(reporters - {"None"}),
                "affectedRepositories": sorted(affected),
                "evidence": sorted(evidence, key=lambda item: str(item.get("id", ""))),
                "verification": sorted(verifications, key=lambda item: str(item.get("id", ""))),
                "verificationCurrent": [
                    copy.deepcopy(dict(item))
                    for _, item in sorted(current_verifications.items(), key=lambda pair: pair[0])
                ],
                "workarounds": sorted(workarounds, key=lambda item: str(item.get("id", ""))),
                "reconciliation": reconciliation,
                "implementation": next(
                    (
                        copy.deepcopy(dict(item.get("implementation", {})))
                        for item in reversed(chain)
                        if item.get("implementation")
                    ),
                    {},
                ),
                "unresolved": (state if not diagnostics else "conflicted") not in TERMINAL_STATUSES,
                "verificationSummary": {
                    "affected": len(affected),
                    "pass": sum(
                        item.get("reproduction", {}).get("status") == "PASS"
                        for item in current_verifications.values()
                    ),
                    "fail": sum(
                        item.get("reproduction", {}).get("status") == "FAIL"
                        for item in current_verifications.values()
                    ),
                    "unknown": sum(
                        item.get("reproduction", {}).get("status") == "UNKNOWN"
                        for item in current_verifications.values()
                    ),
                },
            }
        )
        return PressureProjection(
            data,
            tuple(chain),
            relevant_observations,
            relations,
            tuple(diagnostics),
            transition_material,
        )

    def projections(self, *, validate_lifecycle: bool = True) -> tuple[PressureProjection, ...]:
        records, observations, events = self._documents()
        return tuple(
            self._project_one(
                record_id,
                records[record_id],
                observations.values(),
                events.values(),
                set(records),
                validate_lifecycle=validate_lifecycle,
            )
            for record_id in sorted(records)
        )

    def show(self, record_id: str) -> PressureProjection:
        projection = next((item for item in self.projections() if item.id == record_id), None)
        if projection is None:
            raise PressureError(f"pressure not found: {record_id}")
        native = next((item for item in self.query() if item["id"] == record_id), None)
        if native is None:
            raise PressureError(f"native pressure projection omitted {record_id}")
        data = copy.deepcopy(dict(projection.data))
        data.update(
            {
                "status": native["status"],
                "unresolved": native["unresolved"],
                "verificationState": native["verificationState"],
                "classification": native["classification"],
                "currentValidation": native["currentValidation"],
                "revalidationRequired": native["revalidationRequired"],
                "valid": native["valid"],
            }
        )
        diagnostics = list(projection.diagnostics)
        if native["status"] == "conflicted" and not any(
            item.code in {
                "CONCURRENT_TRANSITIONS",
                "EVENT_CYCLE",
                "STALE_TRANSITION",
                "INVALID_TRANSITION",
                "DANGLING_TRANSITION",
            }
            for item in diagnostics
        ):
            diagnostics.append(
                PressureDiagnostic(
                    "NATIVE_LIFECYCLE_CONFLICT",
                    f"pressure[{record_id}].events",
                    "the compiler-owned lifecycle fold rejected this event history",
                )
            )
        return PressureProjection(
            data,
            projection.events,
            projection.observations,
            projection.relations,
            tuple(diagnostics),
            projection.transition_material,
        )

    def validate(self) -> PressureValidationReport:
        diagnostics: list[PressureDiagnostic] = []
        required_paths = (
            self.root,
            self.records_dir,
            self.observations_dir,
            self.events_dir,
            self.views_dir,
            self.root / "repositories.json",
        )
        missing = [str(path) for path in required_paths if not path.exists()]
        if missing:
            return PressureValidationReport(
                (
                    PressureDiagnostic(
                        "REGISTRY_INCOMPLETE",
                        str(self.root),
                        "registry is not initialized; missing " + ", ".join(missing),
                    ),
                )
            )
        try:
            repository_manifest = _read_json(self.root / "repositories.json")
            records, observations, events = self._documents()
        except PressureError as error:
            return PressureValidationReport(
                (PressureDiagnostic("INVALID_JSON", str(self.root), str(error)),)
            )
        if (
            repository_manifest.get("schema") != REPOSITORY_SCHEMA
            or repository_manifest.get("version") != PRESSURE_VERSION
            or repository_manifest.get("repositories") != known_repositories()
        ):
            diagnostics.append(
                PressureDiagnostic(
                    "REPOSITORY_MANIFEST_MISMATCH",
                    "repositories.json",
                    "repository identity metadata is not the packaged family view",
                )
            )
        aliases: dict[str, str] = {}
        for filename, record in records.items():
            path = f"records/{filename}.json"
            if record.get("schema") != PRESSURE_SCHEMA or record.get("version") != PRESSURE_VERSION:
                diagnostics.append(
                    PressureDiagnostic(
                        "SCHEMA_MISMATCH", path, "pressure declaration schema/version is invalid"
                    )
                )
            expected_digest = _hash_document(
                {key: item for key, item in record.items() if key != "contentDigest"}
            )
            if record.get("contentDigest") != expected_digest:
                diagnostics.append(
                    PressureDiagnostic(
                        "DIGEST_MISMATCH",
                        path,
                        "pressure declaration contentDigest does not match canonical content",
                    )
                )
            record_id = record.get("id")
            if (
                filename != record_id
                or not isinstance(record_id, str)
                or not _ID_RE.fullmatch(record_id)
            ):
                diagnostics.append(
                    PressureDiagnostic(
                        "INVALID_ID",
                        path,
                        "filename and pressure id must match the global id pattern",
                    )
                )
            identity = record.get("identity")
            expected_identity = {
                "target": record.get("target"),
                "domain": record.get("domain"),
                "capability": record.get("capability"),
                "reproducerSignature": (
                    record.get("reproducer", {}).get("signature")
                    if isinstance(record.get("reproducer"), Mapping)
                    else None
                ),
            }
            if identity != expected_identity:
                diagnostics.append(
                    PressureDiagnostic(
                        "IDENTITY_MISMATCH",
                        f"{path}.identity",
                        "identity must mirror the stable top-level pressure fields",
                    )
                )
            for field in ("title", "target", "domain", "capability", "summary", "requiredBehavior"):
                if not isinstance(record.get(field), str) or not record[field].strip():
                    diagnostics.append(
                        PressureDiagnostic(
                            "MISSING_FIELD", f"{path}.{field}", "required field is missing"
                        )
                    )
            if record.get("target") not in TARGETS or record.get("severity") not in SEVERITIES:
                diagnostics.append(
                    PressureDiagnostic(
                        "INVALID_VOCABULARY",
                        path,
                        "target or severity is not in the protocol vocabulary",
                    )
                )
            if record.get("initialStatus") != "discovered":
                diagnostics.append(
                    PressureDiagnostic(
                        "INVALID_INITIAL_STATE",
                        f"{path}.initialStatus",
                        "initialStatus must be discovered",
                    )
                )
            discovered = normalize_repository(record.get("discoveredBy"))
            if discovered is None:
                diagnostics.append(
                    PressureDiagnostic(
                        "UNKNOWN_REPOSITORY",
                        f"{path}.discoveredBy",
                        "repository is not in the family identity view",
                    )
                )
            if not _instant(record.get("discoveredAt")):
                diagnostics.append(
                    PressureDiagnostic(
                        "INVALID_TIMESTAMP",
                        f"{path}.discoveredAt",
                        "timestamp must be UTC RFC3339 or null",
                    )
                )
            for alias in record.get("legacyIds", []):
                if not isinstance(alias, str) or not _ALIAS_RE.fullmatch(alias):
                    diagnostics.append(
                        PressureDiagnostic(
                            "INVALID_ALIAS", f"{path}.legacyIds", "alias is malformed"
                        )
                    )
                elif alias in aliases and aliases[alias] != record_id:
                    diagnostics.append(
                        PressureDiagnostic(
                            "ALIAS_COLLISION",
                            f"{path}.legacyIds",
                            f"alias {alias!r} is also owned by {aliases[alias]}",
                        )
                    )
                else:
                    aliases[alias] = str(record_id)
            for repository in record.get("affectedRepositories", []):
                if normalize_repository(repository) is None:
                    diagnostics.append(
                        PressureDiagnostic(
                            "UNKNOWN_REPOSITORY",
                            f"{path}.affectedRepositories",
                            f"unknown repository {repository!r}",
                        )
                    )
            expected = (
                pressure_id(
                    str(record.get("target", "")),
                    str(record.get("domain", "")),
                    str(record.get("capability", "")),
                    str(record.get("reproducer", {}).get("signature", "")),
                )
                if record.get("target") in TARGETS and isinstance(record.get("reproducer"), Mapping)
                else None
            )
            if expected and expected != record_id and not record.get("allowCustomId"):
                diagnostics.append(
                    PressureDiagnostic(
                        "ID_NOT_DERIVED",
                        path,
                        "id is not derived from stable pressure identity fields",
                    )
                )
        for filename, observation in observations.items():
            path = f"observations/{filename}.json"
            if (
                observation.get("schema") != OBSERVATION_SCHEMA
                or observation.get("version") != PRESSURE_VERSION
            ):
                diagnostics.append(
                    PressureDiagnostic(
                        "SCHEMA_MISMATCH", path, "observation schema/version is invalid"
                    )
                )
            expected_digest = _hash_document(
                {key: item for key, item in observation.items() if key != "contentDigest"}
            )
            if observation.get("contentDigest") != expected_digest:
                diagnostics.append(
                    PressureDiagnostic(
                        "DIGEST_MISMATCH",
                        path,
                        "observation contentDigest does not match canonical content",
                    )
                )
            observation_id = observation.get("id")
            pressure = observation.get("pressureId")
            if (
                filename != observation_id
                or not isinstance(observation_id, str)
                or not re.fullmatch(
                    r"MNCS-[A-Z0-9]+-[A-F0-9]{12}--OBS-[A-F0-9]{12}", observation_id
                )
            ):
                diagnostics.append(
                    PressureDiagnostic(
                        "INVALID_OBSERVATION_ID", path, "observation id and filename are invalid"
                    )
                )
            if isinstance(observation_id, str) and isinstance(pressure, str):
                expected_observation_id = _observation_id(
                    pressure,
                    {
                        key: item
                        for key, item in observation.items()
                        if key not in {"id", "contentDigest"}
                    },
                )
                if observation_id != expected_observation_id:
                    diagnostics.append(
                        PressureDiagnostic(
                            "OBSERVATION_ID_NOT_DERIVED",
                            path,
                            "observation id is not derived from its immutable content",
                        )
                    )
            if pressure not in records:
                diagnostics.append(
                    PressureDiagnostic(
                        "DANGLING_OBSERVATION", path, "observation points to a missing pressure"
                    )
                )
            if normalize_repository(observation.get("repository")) is None:
                diagnostics.append(
                    PressureDiagnostic(
                        "UNKNOWN_REPOSITORY",
                        f"{path}.repository",
                        "observation repository is not known",
                    )
                )
            if not _instant(observation.get("observedAt")):
                diagnostics.append(
                    PressureDiagnostic(
                        "INVALID_TIMESTAMP",
                        f"{path}.observedAt",
                        "timestamp must be UTC RFC3339 or null",
                    )
                )
            reproduction = observation.get("reproduction")
            if (
                not isinstance(reproduction, Mapping)
                or reproduction.get("status") not in EVIDENCE_STATUSES
            ):
                diagnostics.append(
                    PressureDiagnostic(
                        "INVALID_OBSERVATION_STATUS",
                        f"{path}.reproduction.status",
                        "status must be PASS, FAIL, or UNKNOWN",
                    )
                )
            for index, evidence in enumerate(observation.get("evidence", [])):
                if not isinstance(evidence, Mapping) or _evidence_status(evidence) is None:
                    diagnostics.append(
                        PressureDiagnostic(
                            "INVALID_EVIDENCE",
                            f"{path}.evidence[{index}]",
                            "evidence status must remain PASS, FAIL, or UNKNOWN",
                        )
                    )
        relation_targets: list[tuple[str, str, str]] = []
        transition_events_by_pressure: dict[str, list[Mapping[str, Any]]] = {}
        for filename, event in events.items():
            path = f"events/{filename}.json"
            if event.get("schema") != EVENT_SCHEMA or event.get("version") != PRESSURE_VERSION:
                diagnostics.append(
                    PressureDiagnostic("SCHEMA_MISMATCH", path, "event schema/version is invalid")
                )
            expected_digest = _hash_document(
                {key: item for key, item in event.items() if key != "contentDigest"}
            )
            if event.get("contentDigest") != expected_digest:
                diagnostics.append(
                    PressureDiagnostic(
                        "DIGEST_MISMATCH",
                        path,
                        "event contentDigest does not match canonical content",
                    )
                )
            event_id = event.get("id")
            if (
                filename != event_id
                or not isinstance(event_id, str)
                or not (event_id.startswith("EVT-") and len(event_id) == 20)
            ):
                diagnostics.append(
                    PressureDiagnostic(
                        "INVALID_EVENT_ID", path, "event id and filename are invalid"
                    )
                )
            if isinstance(event_id, str):
                expected_event_id = _event_id(
                    {key: item for key, item in event.items() if key not in {"id", "contentDigest"}}
                )
                if event_id != expected_event_id:
                    diagnostics.append(
                        PressureDiagnostic(
                            "EVENT_ID_NOT_DERIVED",
                            path,
                            "event id is not derived from its immutable content",
                        )
                    )
            if event.get("kind") == "PressureRelation":
                source = event.get("sourcePressure")
                target = event.get("targetPressure")
                relation = event.get("relation")
                if source not in records or target not in records:
                    diagnostics.append(
                        PressureDiagnostic(
                            "DANGLING_RELATION", path, "relation points to a missing pressure"
                        )
                    )
                if relation not in RELATIONS or source == target:
                    diagnostics.append(
                        PressureDiagnostic(
                            "INVALID_RELATION", path, "relation type or endpoint is invalid"
                        )
                    )
                if normalize_repository(event.get("actor")) is None:
                    diagnostics.append(
                        PressureDiagnostic(
                            "UNKNOWN_REPOSITORY", f"{path}.actor", "relation actor is not known"
                        )
                    )
                if not _instant(event.get("occurredAt"), allow_none=False):
                    diagnostics.append(
                        PressureDiagnostic(
                            "INVALID_TIMESTAMP",
                            f"{path}.occurredAt",
                            "relation timestamp must be UTC RFC3339",
                        )
                    )
                relation_targets.append((str(source), str(relation), str(target)))
            elif event.get("kind") == "PressureTransition":
                pressure = event.get("pressureId")
                if pressure not in records:
                    diagnostics.append(
                        PressureDiagnostic(
                            "DANGLING_TRANSITION", path, "transition points to a missing pressure"
                        )
                    )
                transition_events_by_pressure.setdefault(str(pressure), []).append(event)
                if normalize_repository(event.get("actor")) is None:
                    diagnostics.append(
                        PressureDiagnostic(
                            "UNKNOWN_REPOSITORY", f"{path}.actor", "transition actor is not known"
                        )
                    )
                if not _instant(event.get("occurredAt"), allow_none=False):
                    diagnostics.append(
                        PressureDiagnostic(
                            "INVALID_TIMESTAMP",
                            f"{path}.occurredAt",
                            "event timestamp must be UTC RFC3339",
                        )
                    )
                for reference in event.get("evidenceRefs", []):
                    if reference not in observations:
                        diagnostics.append(
                            PressureDiagnostic(
                                "DANGLING_EVIDENCE",
                                f"{path}.evidenceRefs",
                                f"unknown observation {reference}",
                            )
                        )
            else:
                diagnostics.append(
                    PressureDiagnostic("UNKNOWN_EVENT", path, "event kind is not supported")
                )
        duplicate_graph: dict[str, set[str]] = {}
        for source, relation, target in relation_targets:
            if relation == "duplicate_of":
                duplicate_graph.setdefault(source, set()).add(target)
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node: str) -> None:
            if node in visiting:
                diagnostics.append(
                    PressureDiagnostic(
                        "DUPLICATE_CYCLE", "events", "duplicate_of relationships must not cycle"
                    )
                )
                return
            if node in visited:
                return
            visiting.add(node)
            for child in sorted(duplicate_graph.get(node, set())):
                visit(child)
            visiting.remove(node)
            visited.add(node)

        for node in sorted(duplicate_graph):
            visit(node)
        for projection in self.projections():
            diagnostics.extend(projection.diagnostics)
            transitions = transition_events_by_pressure.get(projection.id, [])
            for event in transitions:
                target = event.get("to")
                requirements = self._validate_transition_requirements(projection, event)
                # Requirements are checked against the event's predecessor
                # view below for write-time safety; replay still checks the
                # state transition itself and preserves diagnostics if a
                # history was edited or merged incorrectly.
                if target == "resolved" and requirements:
                    diagnostics.append(
                        PressureDiagnostic(
                            "RESOLUTION_EVIDENCE_REQUIRED", f"events/{event['id']}", requirements
                        )
                    )
        return PressureValidationReport(tuple(diagnostics))

    def _query_rows(
        self,
        projections: tuple[PressureProjection, ...],
        *,
        filter_spec: Mapping[str, Any] | None = None,
        view_selector: str | None = None,
    ) -> list[dict[str, Any]]:
        from .pressure_runtime import pressure_kernel

        kernel = pressure_kernel()
        rows = [_projection_row(item) for item in projections]
        if view_selector is not None:
            request = {"rows": rows, "selector": view_selector}
            projected = kernel.project("PressureViewRequest", request)
            function = "query_pressure_view"
        else:
            request = {"rows": rows, "filter": dict(filter_spec or {})}
            projected = kernel.project("PressureQueryRequest", request)
            function = "query_pressure_rows"
        called = kernel.call(function, [projected["value"]])
        serialized = kernel.serialize("PressureQueryResult", called["returned"][0])
        return _materialize_native_rows(projections, serialized)

    def query(
        self,
        *,
        status: str | None = None,
        target: str | None = None,
        domain: str | None = None,
        repository: str | None = None,
        severity: str | Iterable[str] | None = None,
        unresolved: bool = False,
        multi_repository: bool = False,
        awaiting_verification: bool = False,
        workaround_active: bool = False,
        language_profile: str | None = None,
        rust_fallback: bool = False,
        python_fallback: bool = False,
        needs_revalidation: bool = False,
    ) -> list[dict[str, Any]]:
        projections = self.projections(validate_lifecycle=False)
        return self._query_rows(
            projections,
            filter_spec=_projection_filter(
                status=status,
                target=target,
                domain=domain,
                repository=repository,
                severity=severity,
                unresolved=unresolved,
                multi_repository=multi_repository,
                awaiting_verification=awaiting_verification,
                workaround_active=workaround_active,
                language_profile=language_profile,
                rust_fallback=rust_fallback,
                python_fallback=python_fallback,
                needs_revalidation=needs_revalidation,
            )
        )

    def candidates(
        self, *, target: str, domain: str, capability: str, exclude: str | None = None
    ) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        requested = set(re.findall(r"[a-z0-9]+", capability.lower()))
        for data in self.query():
            if (
                data["id"] == exclude
                or data.get("target") != target
                or data.get("domain") != domain
            ):
                continue
            tokens = set(re.findall(r"[a-z0-9]+", str(data.get("capability", "")).lower()))
            score = 100 if data.get("capability") == capability else len(requested & tokens) * 10
            if score <= 0:
                continue
            candidates.append(
                {
                    "id": data["id"],
                    "score": score,
                    "match": "exact capability" if score == 100 else "shared capability tokens",
                    "title": data.get("title"),
                    "status": data.get("status"),
                    "affectedRepositories": data.get("affectedRepositories", []),
                }
            )
        return sorted(candidates, key=lambda item: (-int(item["score"]), str(item["id"])))

    def generate_views(self) -> dict[str, Any]:
        self.init()
        report = self.validate()
        if not report.valid:
            raise PressureError(
                "cannot generate views for an invalid registry: " + _diagnostic_text(report)
            )
        views: dict[str, Any] = {}
        from .pressure_runtime import pressure_kernel

        projections = self.projections(validate_lifecycle=False)
        for selector in pressure_kernel().pressure_view_selectors():
            name = selector.lower().replace("_", "-")
            pressures = self._query_rows(projections, view_selector=selector)
            classification_counts: dict[str, int] = {}
            for pressure in pressures:
                classification = str(pressure.get("classification", "UNRECONCILED"))
                classification_counts[classification] = (
                    classification_counts.get(classification, 0) + 1
                )
            payload = {
                "schema": "commons.mncs.dev/family-pressure-view/v1",
                "view": name,
                "generatedFrom": PRESSURE_SCHEMA,
                "pressures": pressures,
                "reconciliation": {
                    "classificationCounts": {
                        key: classification_counts[key] for key in sorted(classification_counts)
                    },
                    "unreconciled": classification_counts.get("UNRECONCILED", 0),
                },
            }
            _write_json(self.views_dir / f"{name}.json", payload)
            views[name] = payload
        by_repository: dict[str, list[str]] = {}
        for projection in self.projections():
            for repository in projection.data.get("affectedRepositories", []):
                by_repository.setdefault(repository, []).append(projection.id)
        repository_payload = {
            "schema": "commons.mncs.dev/family-pressure-view/v1",
            "view": "by-repository",
            "generatedFrom": PRESSURE_SCHEMA,
            "repositories": {key: sorted(value) for key, value in sorted(by_repository.items())},
        }
        _write_json(self.views_dir / "by-repository.json", repository_payload)
        views["by-repository"] = repository_payload
        by_domain: dict[str, list[str]] = {}
        for projection in self.projections():
            by_domain.setdefault(str(projection.data.get("domain", "unknown")), []).append(
                projection.id
            )
        domain_payload = {
            "schema": "commons.mncs.dev/family-pressure-view/v1",
            "view": "by-domain",
            "generatedFrom": PRESSURE_SCHEMA,
            "domains": {key: sorted(value) for key, value in sorted(by_domain.items())},
        }
        _write_json(self.views_dir / "by-domain.json", domain_payload)
        views["by-domain"] = domain_payload
        index = {
            "schema": "commons.mncs.dev/family-pressure-view-index/v1",
            "valid": True,
            "views": sorted(views),
        }
        _write_json(self.views_dir / "index.json", index)
        return {**index, "output": str(self.views_dir)}

    def migrate_legacy(
        self,
        repository: str,
        source: str | Path,
        *,
        target: str = "language",
        dry_run: bool = False,
        limit: int | None = None,
        refresh: bool = False,
    ) -> dict[str, Any]:
        repo = _require_repository(repository)
        if target not in TARGETS:
            raise PressureError(f"target must be one of {sorted(TARGETS)}")
        source_root = Path(source)
        files = sorted(source_root.rglob("*.md")) if source_root.is_dir() else [source_root]
        if limit is not None:
            files = files[:limit]
        imported: list[dict[str, Any]] = []
        skipped: list[str] = []
        for path in files:
            text = path.read_text(encoding="utf-8")
            entries = _legacy_entries(text)
            if not entries:
                skipped.append(f"ignored:{path.name}")
                continue
            for entry_index, (legacy_id, title, entry_text) in enumerate(entries):
                sections = _load_legacy_sections(entry_text)
                reproducer = (
                    sections.get("minimal reproducer", "")
                    or sections.get("reproducer", "")
                    or _legacy_labeled(entry_text, "Minimal reproducer")
                )
                required = (
                    sections.get("required semantics", "")
                    or sections.get("desired behavior", "")
                    or sections.get("desired semantics", "")
                    or sections.get(
                        "what the language/stdlib/runtime/compiler should ideally provide", ""
                    )
                    or _legacy_labeled(entry_text, "Required semantics")
                    or _legacy_labeled(entry_text, "Desired behavior")
                    or _legacy_labeled(
                        entry_text,
                        "What the language/stdlib/runtime/compiler should ideally provide",
                    )
                    or "Legacy pressure imported; required behavior requires confirmation."
                )
                workaround_text = (
                    sections.get("workaround used", "")
                    or sections.get("current workaround", "")
                    or _legacy_labeled(entry_text, "Workaround used")
                    or _legacy_labeled(entry_text, "Current workaround")
                )
                identity_signature = f"legacy:{repo}:{legacy_id}"
                domain = _legacy_domain(title, path.name)
                capability = _legacy_capability(legacy_id, title)
                generated = pressure_id(target, domain, capability, identity_signature)
                # Earlier importer versions included the title in the capability
                # slug. Reuse an existing scoped legacy alias so wording changes
                # never fork the canonical pressure or erase its history.
                for existing_path in self._files(self.records_dir):
                    existing = _read_json(existing_path)
                    if f"{repo}:{legacy_id}" in existing.get("legacyIds", []):
                        generated = str(existing.get("id"))
                        break
                if (self.records_dir / f"{generated}.json").exists():
                    skipped.append(
                        f"{generated} (already imported; refresh never rewrites "
                        "append-only history)"
                    )
                    continue
                source_path = (
                    path.name if not source_root.is_dir() else str(path.relative_to(source_root))
                )
                source_ref = f"{repo}:{source_path}"
                fallback = _legacy_fallback_language(entry_text)
                source_digest = "sha256:" + hashlib.sha256(entry_text.encode("utf-8")).hexdigest()
                ledger_digest = "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()
                legacy: dict[str, Any] = {
                    "repository": repo,
                    "legacyId": legacy_id,
                    "sourcePath": source_ref,
                    "historicalStatus": _legacy_status(entry_text),
                    "sourceText": entry_text if len(entries) > 1 else text,
                    "sourceDigest": source_digest
                    if len(entries) > 1
                    else "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest(),
                }
                if len(entries) > 1:
                    legacy["sourceLedgerPath"] = source_ref
                    legacy["sourceLedgerDigest"] = ledger_digest
                workaround: dict[str, Any] = {
                    "description": workaround_text[:4000],
                    "active": True,
                    "legacyStatus": _legacy_status(entry_text),
                }
                if fallback:
                    workaround["fallbackLanguage"] = fallback
                signals: dict[str, Any] = {"migration": "legacy-markdown"}
                if fallback:
                    signals["fallbackLanguage"] = fallback
                spec = {
                    "id": generated,
                    "allowCustomId": True,
                    "target": target,
                    "domain": domain,
                    "capability": capability,
                    "reproducerSignature": identity_signature,
                    "title": title,
                    "severity": _legacy_severity(entry_text),
                    "discoveredBy": repo,
                    "discoveredAt": None,
                    "summary": f"Imported legacy pressure {legacy_id}: {title}.",
                    "requiredBehavior": required[:4000],
                    "reproducer": {"signature": identity_signature, "text": reproducer[:4000]},
                    # Scope local ids by repository. A bare P-001 is not a
                    # family identity and would collide across ledgers.
                    "legacyIds": [f"{repo}:{legacy_id}"],
                    "sourceRef": {"path": source_ref, "kind": "legacy-markdown"},
                    "signals": signals,
                    "legacy": legacy,
                    "observation": {
                        "repository": repo,
                        "observedAt": None,
                        "sourceRef": {"path": source_ref, "kind": "legacy-markdown"},
                        "summary": (
                            "Legacy Markdown preserved verbatim; current lifecycle "
                            "awaits Commons confirmation."
                        ),
                        "reproduction": {"status": "UNKNOWN", "instructions": reproducer[:4000]},
                        "evidence": [
                            {
                                "id": f"legacy:{repo}:{legacy_id}",
                                "kind": "legacy-markdown",
                                "status": "UNKNOWN",
                                "ref": source_ref,
                                "summary": (
                                    "Original pressure wording and evidence are preserved "
                                    "in the legacy snapshot."
                                ),
                            }
                        ],
                        "workaround": workaround,
                        "metadata": {
                            "legacyId": legacy_id,
                            "sourceEntry": entry_index,
                            "sourceLedgerDigest": ledger_digest,
                        },
                    },
                }
                if dry_run:
                    imported.append(
                        {
                            "id": generated,
                            "legacyId": legacy_id,
                            "source": source_ref,
                            "target": target,
                        }
                    )
                else:
                    result = self.add(spec)
                    imported.append(
                        {
                            "id": generated,
                            "legacyId": legacy_id,
                            "source": source_ref,
                            "observation": result["observation"]["id"],
                            "target": target,
                        }
                    )
        return {
            "repository": repo,
            "source": str(source_root),
            "target": target,
            "dryRun": dry_run,
            "refresh": refresh,
            "imported": imported,
            "skipped": skipped,
        }


def _diagnostic_text(report: PressureValidationReport) -> str:
    return "; ".join(
        f"{item.code} at {item.path}: {item.message}" for item in report.diagnostics[:5]
    )


def _diagnostic_texts(diagnostics: Iterable[PressureDiagnostic]) -> str:
    return "; ".join(
        f"{item.code} at {item.path}: {item.message}" for item in list(diagnostics)[:5]
    )
