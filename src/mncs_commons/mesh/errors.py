"""Shared mesh error type with stable machine-readable codes."""

from __future__ import annotations


class MeshError(ValueError):
    """A bounded Commons Mesh boundary error; the code is the contract."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}
