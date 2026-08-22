"""Small standard-library remote client for the public Agent Exchange binding."""

from __future__ import annotations

import json
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urljoin, urlparse
from urllib.request import Request, urlopen

from .exchange import EXCHANGE_VERSION, ExchangeError


class RemoteClient:
    def __init__(
        self,
        base_url: str,
        *,
        allow_http: bool = False,
        timeout: float = 15.0,
        max_response_bytes: int = 1 * 1024 * 1024,
    ) -> None:
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("remote URL must include an HTTP(S) scheme and host")
        if parsed.username or parsed.password:
            raise ValueError("remote URL must not contain credentials")
        if parsed.scheme != "https" and not allow_http:
            raise ValueError("HTTPS is required unless --allow-http is explicit")
        self.base_url = base_url.rstrip("/") + "/"
        self.allow_http = allow_http
        self.timeout = timeout
        self.max_response_bytes = max_response_bytes
        self._descriptor: Mapping[str, Any] | None = None

    def _read_bounded(self, response: Any) -> bytes:
        encoding = response.headers.get("Content-Encoding", "identity").lower()
        if encoding not in {"", "identity"}:
            raise ExchangeError("UNSUPPORTED_CONTENT_ENCODING", "remote response is compressed")
        length = response.headers.get("Content-Length")
        if length and (not length.isdigit() or int(length) > self.max_response_bytes):
            raise ExchangeError("RESPONSE_TOO_LARGE", "remote response exceeds client limit")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = response.read(min(64 * 1024, self.max_response_bytes - total + 1))
            if not chunk:
                return b"".join(chunks)
            total += len(chunk)
            if total > self.max_response_bytes:
                raise ExchangeError("RESPONSE_TOO_LARGE", "remote response exceeds client limit")
            chunks.append(chunk)

    def _request(
        self, method: str, path: str, payload: Mapping[str, Any] | None = None
    ) -> dict[str, Any]:
        body = None
        headers = {"Accept": "application/json", "Accept-Encoding": "identity"}
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json"
            headers["Content-Length"] = str(len(body))
        request = Request(
            urljoin(self.base_url, path.lstrip("/")), data=body, headers=headers, method=method
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = self._read_bounded(response)
                status = int(response.status)
        except HTTPError as error:
            raw = self._read_bounded(error)
            status = int(error.code)
        except URLError as error:
            raise ExchangeError(
                "REMOTE_UNAVAILABLE", "remote Commons endpoint unavailable"
            ) from error
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ExchangeError(
                "INVALID_REMOTE_RESPONSE", "remote response was not JSON"
            ) from error
        if not isinstance(value, dict):
            raise ExchangeError("INVALID_REMOTE_RESPONSE", "remote response root was not an object")
        if status >= 400:
            raise ExchangeError(
                str(value.get("error", "REMOTE_ERROR")),
                str(value.get("message", "remote request failed")),
            )
        return value

    def describe(self) -> dict[str, Any]:
        if self._descriptor is None:
            self._descriptor = self._request("GET", "/.well-known/mncs-commons")
        return dict(self._descriptor)

    def vocabulary(self) -> dict[str, Any]:
        return self._request("GET", "/exchange/v0alpha1/vocabulary")

    def validate(self, record: Mapping[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/exchange/v0alpha1/validate", record)

    def publish(
        self, record: Mapping[str, Any], participant: Mapping[str, Any] | None = None
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"record": dict(record)}
        if participant is not None:
            payload["participant"] = dict(participant)
        return self._request("POST", "/exchange/v0alpha1/publish", payload)

    def get(self, digest: str) -> dict[str, Any]:
        return self._request("GET", f"/exchange/v0alpha1/records/{quote(digest, safe='')}")

    def query(self, filters: Mapping[str, Any] | None = None) -> dict[str, Any]:
        return self._request("POST", "/exchange/v0alpha1/query", filters or {})

    def work(self) -> dict[str, Any]:
        return self._request("GET", "/exchange/v0alpha1/work")

    def sync(self, cursor: Mapping[str, Any] | None = None, limit: int = 100) -> dict[str, Any]:
        return self._request("POST", "/exchange/v0alpha1/sync", {"cursor": cursor, "limit": limit})

    def conversation(self, root: str, depth: int = 2, max_nodes: int = 100) -> dict[str, Any]:
        return self._request(
            "POST",
            "/exchange/v0alpha1/conversation",
            {"root": root, "depth": depth, "maxNodes": max_nodes},
        )

    def experiment(
        self, experiment_id: str, depth: int = 3, max_nodes: int = 100
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/exchange/v0alpha1/experiment",
            {"experimentId": experiment_id, "depth": depth, "maxNodes": max_nodes},
        )


__all__ = ["RemoteClient", "EXCHANGE_VERSION"]
