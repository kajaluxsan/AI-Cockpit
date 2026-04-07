"""LinkedIn integration: pull job postings and applicants.

This is a thin wrapper that talks to LinkedIn REST endpoints. The exact
endpoint surface area changes frequently and depends on the partner program
your account is enrolled in. The methods below isolate the specifics so they
can be swapped without touching the rest of the system.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx
from loguru import logger

from app.config import get_settings


@dataclass
class LinkedInJobPosting:
    external_id: str
    title: str
    company: str | None
    location: str | None
    description: str | None
    url: str | None


@dataclass
class LinkedInApplicant:
    external_id: str
    full_name: str | None
    email: str | None
    headline: str | None
    profile_url: str | None
    job_external_id: str | None = None


class LinkedInService:
    BASE_URL = "https://api.linkedin.com/v2"

    def __init__(self) -> None:
        self.settings = get_settings()

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.linkedin_access_token}",
            "X-Restli-Protocol-Version": "2.0.0",
        }

    async def fetch_job_postings(self) -> list[LinkedInJobPosting]:
        if not self.settings.linkedin_access_token:
            logger.warning("LinkedIn access token missing")
            return []
        company = self.settings.linkedin_company_id
        if not company:
            return []
        url = f"{self.BASE_URL}/jobs?q=company&company=urn:li:organization:{company}"
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(url, headers=self.headers)
                resp.raise_for_status()
                payload = resp.json()
            return [
                LinkedInJobPosting(
                    external_id=str(item.get("id", "")),
                    title=item.get("title", ""),
                    company=(item.get("company") or {}).get("name"),
                    location=(item.get("location") or {}).get("city"),
                    description=item.get("description"),
                    url=item.get("applyUrl"),
                )
                for item in payload.get("elements", [])
            ]
        except Exception as exc:
            logger.exception(f"LinkedIn job fetch failed: {exc}")
            return []

    async def fetch_applicants(self, job_external_id: str) -> list[LinkedInApplicant]:
        if not self.settings.linkedin_access_token:
            return []
        url = f"{self.BASE_URL}/jobApplications?q=job&job=urn:li:job:{job_external_id}"
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(url, headers=self.headers)
                resp.raise_for_status()
                payload = resp.json()
            results: list[LinkedInApplicant] = []
            for item in payload.get("elements", []):
                applicant = item.get("applicant") or {}
                results.append(
                    LinkedInApplicant(
                        external_id=str(item.get("id", "")),
                        full_name=applicant.get("fullName"),
                        email=applicant.get("emailAddress"),
                        headline=applicant.get("headline"),
                        profile_url=applicant.get("publicProfileUrl"),
                        job_external_id=job_external_id,
                    )
                )
            return results
        except Exception as exc:
            logger.exception(f"LinkedIn applicants fetch failed: {exc}")
            return []


def get_linkedin_service() -> LinkedInService:
    return LinkedInService()
