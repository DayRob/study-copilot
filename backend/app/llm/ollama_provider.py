import json
from typing import Any, AsyncIterator

import httpx

from app.config import get_settings

TIMEOUT = httpx.Timeout(360.0, connect=10.0)
# Ollama's default context window (often 2048-4096 tokens) is too small for the
# numbered-excerpt prompts this app sends (up to ~9-10k tokens for an overview
# or a game question batch) -- an undersized context silently truncates or can
# make structured generation fail outright, so it's set explicitly here.
NUM_CTX = 8192


class OllamaProvider:
    """Talks to a local Ollama server (http://localhost:11434 by default).
    No API key, no per-token cost -- inference just runs on this machine."""

    def __init__(self) -> None:
        settings = get_settings()
        self._base_url = settings.ollama_base_url.rstrip("/")
        self._model = settings.ollama_model

    def _messages(self, system: str, user: str) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

    async def complete(self, system: str, user: str, *, fast: bool = False) -> str:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.post(
                f"{self._base_url}/api/chat",
                json={
                    "model": self._model,
                    "messages": self._messages(system, user),
                    "stream": False,
                    "options": {"num_ctx": NUM_CTX},
                },
            )
            response.raise_for_status()
            return response.json()["message"]["content"]

    async def complete_structured(
        self, system: str, user: str, schema: dict[str, Any], *, fast: bool = False
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.post(
                f"{self._base_url}/api/chat",
                json={
                    "model": self._model,
                    "messages": self._messages(system, user),
                    "stream": False,
                    "format": schema,
                    "options": {"num_ctx": NUM_CTX},
                },
            )
            response.raise_for_status()
            return json.loads(response.json()["message"]["content"])

    async def stream(self, system: str, user: str, *, fast: bool = False) -> AsyncIterator[str]:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            async with client.stream(
                "POST",
                f"{self._base_url}/api/chat",
                json={
                    "model": self._model,
                    "messages": self._messages(system, user),
                    "stream": True,
                    "options": {"num_ctx": NUM_CTX},
                },
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    chunk = json.loads(line)
                    delta = chunk.get("message", {}).get("content", "")
                    if delta:
                        yield delta
                    if chunk.get("done"):
                        break


_provider: OllamaProvider | None = None


def get_ollama_provider() -> OllamaProvider:
    global _provider
    if _provider is None:
        _provider = OllamaProvider()
    return _provider
