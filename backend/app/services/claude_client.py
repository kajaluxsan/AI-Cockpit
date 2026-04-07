"""Thin wrapper around the Anthropic Claude SDK."""

from __future__ import annotations

import json
from typing import Any

from anthropic import AsyncAnthropic
from loguru import logger

from app.config import get_settings


class ClaudeClient:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._client: AsyncAnthropic | None = None

    @property
    def client(self) -> AsyncAnthropic:
        if self._client is None:
            if not self.settings.anthropic_api_key:
                raise RuntimeError("ANTHROPIC_API_KEY is not configured")
            self._client = AsyncAnthropic(api_key=self.settings.anthropic_api_key)
        return self._client

    async def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int | None = None,
        temperature: float = 0.3,
    ) -> str:
        try:
            response = await self.client.messages.create(
                model=self.settings.anthropic_model,
                max_tokens=max_tokens or self.settings.anthropic_max_tokens,
                temperature=temperature,
                system=system or "Du bist ein präziser, hilfsbereiter Assistent.",
                messages=[{"role": "user", "content": prompt}],
            )
            text_blocks = [b.text for b in response.content if hasattr(b, "text")]
            return "".join(text_blocks).strip()
        except Exception as exc:
            logger.exception(f"Claude API call failed: {exc}")
            raise

    async def complete_json(
        self,
        prompt: str,
        *,
        system: str | None = None,
        temperature: float = 0.2,
    ) -> dict[str, Any]:
        text = await self.complete(prompt, system=system, temperature=temperature)
        return _safe_json_parse(text)

    async def conversation_turn(
        self,
        system: str,
        history: list[dict[str, str]],
        user_message: str,
        *,
        temperature: float = 0.6,
        max_tokens: int = 300,
    ) -> str:
        """One turn in a multi-turn conversation. `history` follows
        Anthropic message format: [{"role": "user"/"assistant", "content": str}]."""
        messages = list(history) + [{"role": "user", "content": user_message}]
        response = await self.client.messages.create(
            model=self.settings.anthropic_model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=messages,
        )
        return "".join(b.text for b in response.content if hasattr(b, "text")).strip()


def _safe_json_parse(text: str) -> dict[str, Any]:
    """Best-effort JSON parsing — strips markdown fences if present."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        # Strip leading ``` or ```json and trailing ```
        lines = cleaned.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        logger.warning(f"Failed to parse Claude JSON response: {exc}")
        # Attempt to find JSON object substring
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(cleaned[start : end + 1])
            except json.JSONDecodeError:
                pass
        raise


_claude_client: ClaudeClient | None = None


def get_claude_client() -> ClaudeClient:
    global _claude_client
    if _claude_client is None:
        _claude_client = ClaudeClient()
    return _claude_client
