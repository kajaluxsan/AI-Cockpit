"""Generic REST API client for syncing with external customer applications.

All endpoint paths and authentication parameters are configurable via .env so
the same client can talk to any REST API.
"""

from __future__ import annotations

from typing import Any

import httpx
from loguru import logger

from app.config import get_settings


class ExternalApiClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    @property
    def base_url(self) -> str:
        return (self.settings.external_api_base_url or "").rstrip("/")

    def _build_auth(self) -> tuple[dict[str, str], httpx.BasicAuth | None]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        auth: httpx.BasicAuth | None = None
        atype = self.settings.external_api_auth_type
        if atype == "bearer" and self.settings.external_api_auth_token:
            headers["Authorization"] = f"Bearer {self.settings.external_api_auth_token}"
        elif atype == "basic" and self.settings.external_api_auth_user:
            auth = httpx.BasicAuth(
                self.settings.external_api_auth_user,
                self.settings.external_api_auth_password or "",
            )
        elif atype == "api_key" and self.settings.external_api_key_value:
            headers[self.settings.external_api_key_header] = (
                self.settings.external_api_key_value
            )
        return headers, auth

    def _url(self, path: str, **path_params: Any) -> str:
        formatted = path.format(**path_params) if path_params else path
        return f"{self.base_url}{formatted}"

    async def _request(
        self,
        method: str,
        url: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any] | list[Any] | None:
        headers, auth = self._build_auth()
        try:
            async with httpx.AsyncClient(timeout=30, auth=auth) as client:
                resp = await client.request(
                    method, url, headers=headers, json=json, params=params
                )
                resp.raise_for_status()
                if resp.headers.get("content-type", "").startswith("application/json"):
                    return resp.json()
                return None
        except httpx.HTTPError as exc:
            logger.exception(f"External API {method} {url} failed: {exc}")
            return None

    # ---------- Candidates ----------
    async def list_candidates(self) -> list[dict[str, Any]]:
        url = self._url(self.settings.external_api_candidates_get)
        result = await self._request("GET", url)
        if isinstance(result, list):
            return result
        if isinstance(result, dict) and "data" in result:
            return result["data"]
        return []

    async def create_candidate(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        url = self._url(self.settings.external_api_candidates_post)
        return await self._request("POST", url, json=payload)  # type: ignore[return-value]

    async def update_candidate(
        self, candidate_id: str | int, payload: dict[str, Any]
    ) -> dict[str, Any] | None:
        url = self._url(self.settings.external_api_candidates_put, id=candidate_id)
        return await self._request("PUT", url, json=payload)  # type: ignore[return-value]

    # ---------- Jobs ----------
    async def list_jobs(self) -> list[dict[str, Any]]:
        url = self._url(self.settings.external_api_jobs_get)
        result = await self._request("GET", url)
        if isinstance(result, list):
            return result
        if isinstance(result, dict) and "data" in result:
            return result["data"]
        return []

    async def create_job(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        url = self._url(self.settings.external_api_jobs_post)
        return await self._request("POST", url, json=payload)  # type: ignore[return-value]

    # ---------- Matches ----------
    async def list_matches(self) -> list[dict[str, Any]]:
        url = self._url(self.settings.external_api_matches_get)
        result = await self._request("GET", url)
        if isinstance(result, list):
            return result
        if isinstance(result, dict) and "data" in result:
            return result["data"]
        return []

    async def create_match(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        url = self._url(self.settings.external_api_matches_post)
        return await self._request("POST", url, json=payload)  # type: ignore[return-value]


def get_external_api_client() -> ExternalApiClient:
    return ExternalApiClient()
