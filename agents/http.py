"""
HTTP adapter for direct API agents (OpenAI, Anthropic, xAI, etc.)

No gateway needed — connects directly to provider APIs using
OpenAI-compatible chat completions format.

Supports: OpenAI, xAI/Grok, any OpenAI-compatible endpoint.
Anthropic uses a slightly different format (messages API).
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Awaitable, Callable
from urllib.parse import urlparse

from agents.base import AgentConfig, BaseAgent

try:
    import aiohttp
    _AIOHTTP = True
except ImportError:
    _AIOHTTP = False


class HttpAgent(BaseAgent):
    """Direct HTTP API agent — no gateway, no WebSocket."""

    def __init__(self, config: AgentConfig, response_timeout: float = 60.0):
        super().__init__(config)
        self.response_timeout = response_timeout
        self._session: aiohttp.ClientSession | None = None

    async def connect(self) -> None:
        if not _AIOHTTP:
            raise RuntimeError("pip install aiohttp")
        if self._connected:
            return
        if not self.config.url:
            raise ValueError(f"Agent '{self.name}' missing API url")
        if not self.config.token:
            raise ValueError(f"Agent '{self.name}' missing API token")

        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.response_timeout),
        )
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False
        if self._session:
            await self._session.close()
            self._session = None

    async def send(self, message: str) -> None:
        await self.send_and_receive(message)

    async def send_and_receive(self, message: str, use_full_session: bool = True) -> str:
        """Send message to API and return response text."""
        if not self._connected or not self._session:
            raise RuntimeError(f"Agent '{self.name}' not connected")

        url = self.config.url
        model = getattr(self.config, 'model', '') or self._infer_model()

        # Detect provider from URL
        is_anthropic = "anthropic.com" in url

        if is_anthropic:
            return await self._call_anthropic(message, model)
        else:
            return await self._call_openai_compat(message, model)

    async def _call_openai_compat(self, message: str, model: str) -> str:
        """OpenAI-compatible chat completions (works for OpenAI, xAI, local, etc.)"""
        headers = {
            "Authorization": f"Bearer {self.config.token}",
            "Content-Type": "application/json",
        }

        body = {
            "model": model,
            "messages": [{"role": "user", "content": message}],
            "temperature": 0.7,
        }

        async with self._session.post(self.config.url, headers=headers, json=body) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"API {resp.status}: {text[:200]}")

            data = await resp.json()
            choices = data.get("choices", [])
            if not choices:
                raise RuntimeError(f"API returned no choices: {json.dumps(data)[:200]}")

            return choices[0].get("message", {}).get("content", "").strip()

    async def _call_anthropic(self, message: str, model: str) -> str:
        """Anthropic messages API."""
        headers = {
            "x-api-key": self.config.token,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

        body = {
            "model": model,
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": message}],
        }

        async with self._session.post(self.config.url, headers=headers, json=body) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"Anthropic {resp.status}: {text[:200]}")

            data = await resp.json()
            content = data.get("content", [])
            if isinstance(content, list):
                parts = [b.get("text", "") for b in content if isinstance(b, dict)]
                return "\n".join(p for p in parts if p).strip()
            return str(content).strip()

    def _infer_model(self) -> str:
        """Infer model from URL/config when not explicitly set."""
        url = self.config.url
        if "x.ai" in url:
            return "grok-4"
        if "openai.com" in url:
            return "gpt-4o"
        if "anthropic.com" in url:
            return "claude-sonnet-4-5"
        return "gpt-4o"  # safe default for OpenAI-compat endpoints

    async def listen(self, callback: Callable[[str], Awaitable[None]]) -> None:
        """HTTP agents don't have persistent connections — listen is a no-op."""
        while self._connected:
            await asyncio.sleep(1)
