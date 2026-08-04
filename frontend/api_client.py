"""Thin HTTP client for the GyanSetu TKP FastAPI backend."""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

_DEFAULT_BASE = "http://localhost:8000"
_API_PREFIX = "/api/v1"
_REPO_ROOT = Path(__file__).resolve().parent.parent


@lru_cache
def _load_env() -> None:
    """Load repo-root ``.env`` once so Streamlit shares ``BACKEND_API_KEY`` with FastAPI."""
    load_dotenv(_REPO_ROOT / ".env", override=False)


def _from_st_secrets(key: str) -> str | None:
    """Read ``key`` from ``st.secrets`` when available (Streamlit Cloud).

    Returns ``None`` when secrets are absent (local dev without ``secrets.toml``),
    Streamlit is not importable, or the key is missing/empty — callers fall back
    to ``os.environ``.
    """
    try:
        import streamlit as st

        secrets = st.secrets
    except Exception:
        return None
    try:
        if key not in secrets:
            return None
        raw = secrets[key]
    except Exception:
        return None
    if raw is None:
        return None
    text = str(raw).strip()
    return text or None


def _config_value(*keys: str, default: str = "") -> str:
    """Prefer ``st.secrets`` for each alias, then ``os.environ``, then ``default``."""
    _load_env()
    for key in keys:
        secret = _from_st_secrets(key)
        if secret:
            return secret
    for key in keys:
        env = (os.environ.get(key) or "").strip()
        if env:
            return env
    return default


def _api_key() -> str:
    # Single canonical name (same as backend Settings.backend_api_key).
    # TKP_API_KEY kept as an optional override for shell/CI only.
    return _config_value("BACKEND_API_KEY", "TKP_API_KEY")


def _base_url() -> str:
    return _config_value("TKP_API_URL", "BACKEND_URL", default=_DEFAULT_BASE).rstrip("/")


class TKPApiClient:
    """Sync httpx wrapper around ``/api/v1`` endpoints."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float = 120.0,
    ) -> None:
        self.base_url = (base_url or _base_url()).rstrip("/")
        self.api_key = api_key if api_key is not None else _api_key()
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Accept": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers

    def _url(self, path: str) -> str:
        return f"{self.base_url}{_API_PREFIX}{path}"

    def health(self) -> dict[str, Any]:
        """GET /api/v1/health (falls back to root /health)."""
        with httpx.Client(timeout=self.timeout) as client:
            try:
                resp = client.get(self._url("/health"), headers=self._headers())
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPError:
                resp = client.get(f"{self.base_url}/health", headers=self._headers())
                resp.raise_for_status()
                return resp.json()

    def upload_document(
        self,
        file_bytes: bytes,
        filename: str,
        hint: str | None = None,
        *,
        auto_start: bool = True,
    ) -> dict[str, Any]:
        """POST /documents/upload — returns document_id, job_id, message."""
        data: dict[str, str] = {"auto_start": "true" if auto_start else "false"}
        if hint:
            data["doc_type_hint"] = hint
        files = {"file": (filename, file_bytes)}
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(
                self._url("/documents/upload"),
                headers=self._headers(),
                data=data,
                files=files,
            )
            resp.raise_for_status()
            return resp.json()

    def get_job(self, job_id: str) -> dict[str, Any]:
        """GET /jobs/{job_id}."""
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.get(self._url(f"/jobs/{job_id}"), headers=self._headers())
            resp.raise_for_status()
            return resp.json()

    def start_job(self, job_id: str) -> dict[str, Any]:
        """POST /jobs/{job_id}/start."""
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(
                self._url(f"/jobs/{job_id}/start"),
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()

    def get_tkp(self, job_id: str) -> dict[str, Any]:
        """GET /jobs/{job_id}/tkp."""
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.get(
                self._url(f"/jobs/{job_id}/tkp"),
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()

    def get_eval_report(self, job_id: str) -> dict[str, Any]:
        """GET /jobs/{job_id}/eval-report."""
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.get(
                self._url(f"/jobs/{job_id}/eval-report"),
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()

    def download_export(self, job_id: str, artifact: str) -> bytes:
        """GET /jobs/{job_id}/export/{artifact} — PDF bytes."""
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.get(
                self._url(f"/jobs/{job_id}/export/{artifact}"),
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.content

    def stream_job_events(self, job_id: str) -> Iterator[dict[str, Any]]:
        """Yield parsed JSON events from GET /jobs/{job_id}/stream (SSE)."""
        with (
            httpx.Client(timeout=None) as client,
            client.stream(
                "GET",
                self._url(f"/jobs/{job_id}/stream"),
                headers={**self._headers(), "Accept": "text/event-stream"},
            ) as resp,
        ):
            resp.raise_for_status()
            event_name = "message"
            data_buf: list[str] = []
            for line in resp.iter_lines():
                if line is None:
                    continue
                if line.startswith(":"):
                    continue
                if line.startswith("event:"):
                    event_name = line[6:].strip()
                elif line.startswith("data:"):
                    data_buf.append(line[5:].lstrip())
                elif line == "":
                    if not data_buf:
                        event_name = "message"
                        continue
                    raw = "\n".join(data_buf)
                    data_buf = []
                    try:
                        payload = json.loads(raw)
                    except json.JSONDecodeError:
                        payload = {
                            "message": raw,
                            "stage": "unknown",
                            "progress": 0.0,
                        }
                    done = event_name == "done"
                    if isinstance(payload, dict):
                        payload["_event"] = event_name
                        yield payload
                        if done or payload.get("status") in {"completed", "failed"}:
                            return
                    event_name = "message"
            if data_buf:
                try:
                    payload = json.loads("\n".join(data_buf))
                except json.JSONDecodeError:
                    payload = {"message": "\n".join(data_buf)}
                if isinstance(payload, dict):
                    payload["_event"] = event_name
                    yield payload

    # Back-compat alias
    stream_events = stream_job_events


def get_client() -> TKPApiClient:
    """Factory that reads URL/key from ``st.secrets`` then the environment (never logs secrets)."""
    return TKPApiClient()
