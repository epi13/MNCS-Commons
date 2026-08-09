"""Structured errors shared by library and CLI boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .models import Diagnostic


@dataclass(frozen=True, slots=True)
class ValidationReport:
    diagnostics: tuple[Diagnostic, ...] = ()

    @property
    def valid(self) -> bool:
        return not any(item.severity == "error" for item in self.diagnostics)

    def extend(self, diagnostics: Iterable[Diagnostic]) -> "ValidationReport":
        return ValidationReport(self.diagnostics + tuple(diagnostics))

    def as_dict(self) -> dict[str, object]:
        return {"valid": self.valid, "diagnostics": [item.as_dict() for item in self.diagnostics]}
