"""Shared result contract for inert producer translations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ..models import Diagnostic


@dataclass(frozen=True, slots=True)
class AdapterResult:
    record: Mapping[str, Any] | None
    diagnostics: tuple[Diagnostic, ...] = ()
    source_version: str | None = None
    recognized: bool = False
    unresolved_fields: tuple[str, ...] = ()

    @property
    def valid(self) -> bool:
        return self.record is not None and not any(
            item.severity == "error" for item in self.diagnostics
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "record": self.record,
            "diagnostics": [item.as_dict() for item in self.diagnostics],
            "sourceVersion": self.source_version,
            "recognized": self.recognized,
            "unresolvedFields": list(self.unresolved_fields),
            "valid": self.valid,
        }
