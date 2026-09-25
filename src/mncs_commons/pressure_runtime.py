"""Artifact-bound runtime bridge for the Commons pressure MNCS kernel.

The Python side owns compiler process startup and JSON transport. Record
contracts, nominal identities, typed values, and query behavior come from the
loaded compiler artifact through the stable mncs-embed C ABI.
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Any

from .mesh.executor import find_toolchain


class PressureKernelError(RuntimeError):
    """The compiler-owned pressure projection could not be executed."""


class _EmbedRuntime:
    def __init__(self, checkout: Path, source: Path) -> None:
        self.checkout = checkout
        self.source = source
        self._lock = threading.RLock()
        self._source_digest = hashlib.sha256(source.read_bytes()).hexdigest()
        self.library = self._load_library(checkout)
        self.handle, self.artifact_bytes = self._compile_and_open()
        self.composites = self._read(self.library.mncs_session_composite_types(self.handle))
        self.artifact_identity = self._artifact_identity()
        self.types = self._resolve_types()

    @staticmethod
    def _load_library(checkout: Path) -> ctypes.CDLL:
        requested = os.environ.get("MNCS_EMBED_LIBRARY")
        candidates = [Path(requested)] if requested else []
        candidates.extend(
            checkout / "target" / "debug" / name
            for name in ("libmncs_embed.so", "libmncs_embed.dylib", "mncs_embed.dll")
        )
        for candidate in candidates:
            if candidate.is_file():
                library = ctypes.CDLL(str(candidate.resolve()))
                library.mncs_session_open.argtypes = [
                    ctypes.POINTER(ctypes.c_ubyte), ctypes.c_size_t
                ]
                library.mncs_session_open.restype = ctypes.c_void_p
                library.mncs_session_close.argtypes = [ctypes.c_void_p]
                library.mncs_session_close.restype = None
                for symbol in (
                    "mncs_session_composite_types",
                    "mncs_session_info",
                ):
                    getattr(library, symbol).argtypes = [ctypes.c_void_p]
                    getattr(library, symbol).restype = ctypes.c_void_p
                for symbol in (
                    "mncs_session_project_value",
                    "mncs_session_serialize_value",
                    "mncs_session_call_batch",
                ):
                    getattr(library, symbol).argtypes = [ctypes.c_void_p, ctypes.c_char_p]
                    getattr(library, symbol).restype = ctypes.c_void_p
                library.mncs_response_text.argtypes = [ctypes.c_void_p]
                library.mncs_response_text.restype = ctypes.c_char_p
                library.mncs_response_free.argtypes = [ctypes.c_void_p]
                library.mncs_response_free.restype = None
                library.mncs_last_error.argtypes = []
                library.mncs_last_error.restype = ctypes.c_char_p
                return library
        raise PressureKernelError(
            "mncs-embed library is unavailable; build mncs-embed or set MNCS_EMBED_LIBRARY"
        )

    def _compile_and_open(self) -> tuple[int, bytes]:
        binary = self.checkout / "target" / "debug" / "mncs"
        if not binary.is_file():
            raise PressureKernelError(f"MNCS compiler is missing: {binary}")
        environment = dict(os.environ)
        mesh_mncs = Path(__file__).resolve().parent / "mesh" / "mncs"
        environment["MNCS_LIBRARY_PATH"] = os.pathsep.join(
            (str(self.checkout / "library"), str(mesh_mncs))
        )
        with tempfile.TemporaryDirectory(prefix="mncs-pressure-kernel-") as directory:
            output = Path(directory)
            completed = subprocess.run(
                [
                    str(binary),
                    "compile",
                    str(self.source),
                    "--emit",
                    "backend",
                    "--target",
                    "research-bytecode",
                    "--output-dir",
                    str(output),
                ],
                cwd=self.source.parent,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            artifact_path = output / "backend.json"
            if completed.returncode != 0 or not artifact_path.is_file():
                detail = completed.stderr.strip() or completed.stdout.strip()
                raise PressureKernelError(
                    "cannot compile Commons pressure kernel"
                    + (f": {detail[-4000:]}" if detail else "")
                )
            artifact_bytes = artifact_path.read_bytes()
        buffer = (ctypes.c_ubyte * len(artifact_bytes)).from_buffer_copy(artifact_bytes)
        self._artifact_buffer = buffer
        handle = self.library.mncs_session_open(buffer, len(artifact_bytes))
        if not handle:
            raise PressureKernelError(self._last_error())
        return handle, artifact_bytes

    def _last_error(self) -> str:
        value = self.library.mncs_last_error()
        return value.decode("utf-8", errors="replace") if value else "unknown embed error"

    def _read(self, response: int) -> Any:
        if not response:
            raise PressureKernelError(self._last_error())
        try:
            raw = self.library.mncs_response_text(response)
            if not raw:
                raise PressureKernelError("mncs-embed returned an empty response")
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise PressureKernelError(f"mncs-embed returned invalid JSON: {error}") from error
        finally:
            self.library.mncs_response_free(response)

    def _artifact_identity(self) -> str:
        info = self._read(self.library.mncs_session_info(self.handle))
        if not isinstance(info, dict) or not isinstance(info.get("artifact_identity"), str):
            raise PressureKernelError("loaded MNCS artifact did not report its identity")
        return info["artifact_identity"]

    def _resolve_types(self) -> dict[str, dict[str, Any]]:
        if not isinstance(self.composites, list):
            raise PressureKernelError("compiler composite metadata is malformed")
        by_name: dict[str, list[dict[str, Any]]] = {}
        for item in self.composites:
            if isinstance(item, dict) and isinstance(item.get("name"), str):
                by_name.setdefault(item["name"], []).append(item)
        names = (
            "PressureQueryRequest",
            "PressureQueryResult",
            "PressureStatus",
            "PressureViewRequest",
            "PressureViewSelector",
        )
        resolved: dict[str, dict[str, Any]] = {}
        for name in names:
            matches = by_name.get(name, [])
            if len(matches) != 1:
                raise PressureKernelError(
                    f"compiler artifact must declare exactly one {name} contract"
                )
            item = matches[0]
            reference = item.get("reference")
            if (
                not isinstance(reference, dict)
                or reference.get("artifact_identity") != self.artifact_identity
                or not isinstance(reference.get("type_identity"), str)
            ):
                raise PressureKernelError(f"compiler identity for {name} is malformed or stale")
            resolved[name] = item
        return resolved

    def _reference(self, name: str) -> dict[str, str]:
        reference = self.types[name]["reference"]
        return {
            "artifact_identity": reference["artifact_identity"],
            "type_identity": reference["type_identity"],
        }

    def pressure_view_selectors(self) -> list[str]:
        variants = self.types["PressureViewSelector"].get("variants")
        if (
            not isinstance(variants, list)
            or not variants
            or any(not isinstance(item, str) or not item for item in variants)
            or len(set(variants)) != len(variants)
        ):
            raise PressureKernelError("compiler pressure view selector metadata is malformed")
        return list(variants)

    def project(self, name: str, structured: Any) -> dict[str, Any]:
        request = {"reference": self._reference(name), "value": structured}
        with self._lock:
            return self._read(
                self.library.mncs_session_project_value(
                    self.handle, json.dumps(request, separators=(",", ":")).encode()
                )
            )

    def transition_allowed(self, current: str, target: str) -> bool:
        output = self.call_typed(
            "transition_allowed_state",
            [
                {"finite": {"variant": current.upper()}},
                {"finite": {"variant": target.upper()}},
            ],
        )
        value = output["returned"][0]
        if not isinstance(value, dict) or not isinstance(value.get("boolean"), dict):
            raise PressureKernelError("native lifecycle policy returned a non-boolean value")
        return bool(value["boolean"].get("value"))

    def resolution_ready(
        self, affected: int, passed: int, failed: int, unknown: int, removed: int
    ) -> bool:
        arguments = [
            {"integer": {"value": value}}
            for value in (affected, passed, failed, unknown, removed)
        ]
        output = self.call_typed("resolution_ready", arguments)
        value = output["returned"][0]
        if not isinstance(value, dict) or not isinstance(value.get("boolean"), dict):
            raise PressureKernelError("native resolution policy returned a non-boolean value")
        return bool(value["boolean"].get("value"))

    def verification_state(
        self, affected: int, passed: int, failed: int, unknown: int, removed: int
    ) -> int:
        arguments = [
            {"integer": {"value": value}}
            for value in (affected, passed, failed, unknown, removed)
        ]
        output = self.call_typed("verification_state", arguments)
        value = output["returned"][0]
        if not isinstance(value, dict) or not isinstance(value.get("integer"), dict):
            raise PressureKernelError("native verification classifier returned a non-integer value")
        return int(value["integer"].get("value"))

    def available_awaiting_consumer(self, status: int, current_validation: bool) -> bool:
        output = self.call_typed(
            "available_awaiting_consumer",
            [
                {"integer": {"value": status}},
                {"boolean": {"value": current_validation}},
            ],
        )
        value = output["returned"][0]
        if not isinstance(value, dict) or not isinstance(value.get("boolean"), dict):
            raise PressureKernelError("native availability classifier returned a non-boolean value")
        return bool(value["boolean"].get("value"))

    def unresolved(self, status: int) -> bool:
        output = self.call_typed(
            "unresolved", [{"integer": {"value": status}}]
        )
        value = output["returned"][0]
        if not isinstance(value, dict) or not isinstance(value.get("boolean"), dict):
            raise PressureKernelError("native unresolved classifier returned a non-boolean value")
        return bool(value["boolean"].get("value"))

    def requires_revalidation(self, unresolved: bool, current_validation: bool) -> bool:
        output = self.call_typed(
            "requires_revalidation",
            [
                {"boolean": {"value": unresolved}},
                {"boolean": {"value": current_validation}},
            ],
        )
        value = output["returned"][0]
        if not isinstance(value, dict) or not isinstance(value.get("boolean"), dict):
            raise PressureKernelError("native revalidation classifier returned a non-boolean value")
        return bool(value["boolean"].get("value"))

    def call(self, function: str, arguments: list[dict[str, Any]]) -> dict[str, Any]:
        request = [
            {
                "module": "commons.pressure.lifecycle",
                "function": function,
                "args": arguments,
                "step_budget": 8_000_000,
            }
        ]
        with self._lock:
            values = self._read(
                self.library.mncs_session_call_batch(
                    self.handle, json.dumps(request, separators=(",", ":")).encode()
                )
            )
        if not isinstance(values, list) or len(values) != 1 or not isinstance(values[0], dict):
            raise PressureKernelError("native pressure call returned a malformed batch")
        output = values[0]
        if output.get("status") != "returned" or not output.get("returned"):
            raise PressureKernelError(
                str(output.get("failure_reason") or output.get("status") or "native call failed")
            )
        return output

    def call_typed(self, function: str, arguments: list[dict[str, Any]]) -> dict[str, Any]:
        request = [
            {
                "module": "commons.pressure.lifecycle",
                "function": function,
                "typed_args": arguments,
                "step_budget": 8_000_000,
            }
        ]
        with self._lock:
            values = self._read(
                self.library.mncs_session_call_batch(
                    self.handle, json.dumps(request, separators=(",", ":")).encode()
                )
            )
        if not isinstance(values, list) or len(values) != 1 or not isinstance(values[0], dict):
            raise PressureKernelError("native pressure call returned a malformed batch")
        output = values[0]
        if output.get("status") != "returned" or not output.get("returned"):
            raise PressureKernelError(
                str(output.get("failure_reason") or output.get("status") or "native call failed")
            )
        return output

    def serialize(self, name: str, value: dict[str, Any]) -> dict[str, Any]:
        request = {"reference": self._reference(name), "value": value}
        with self._lock:
            result = self._read(
                self.library.mncs_session_serialize_value(
                    self.handle, json.dumps(request, separators=(",", ":")).encode()
                )
            )
        if not isinstance(result, dict):
            raise PressureKernelError("native pressure result is not a structured record")
        return result


_RUNTIME: _EmbedRuntime | None = None
_RUNTIME_LOCK = threading.Lock()


def pressure_kernel() -> _EmbedRuntime:
    """Return the cached kernel session for the current source artifact."""

    global _RUNTIME
    checkout = find_toolchain()
    if checkout is None:
        raise PressureKernelError("a built mncs-language checkout is required")
    source = (
        Path(__file__).resolve().parent
        / "mesh"
        / "mncs"
        / "commons"
        / "pressure"
        / "lifecycle.mncs"
    )
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    with _RUNTIME_LOCK:
        if _RUNTIME is None or _RUNTIME.checkout != checkout or _RUNTIME._source_digest != digest:
            _RUNTIME = _EmbedRuntime(checkout, source)
        return _RUNTIME
