from typing import Any, AsyncIterator

from anthropic import AsyncAnthropic

from app.config import get_settings

MAX_TOKENS = 4096


class AnthropicProvider:
    def __init__(self) -> None:
        settings = get_settings()
        self._client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        self._model = settings.llm_model
        self._fast_model = settings.llm_fast_model

    async def complete(self, system: str, user: str, *, fast: bool = False) -> str:
        response = await self._client.messages.create(
            model=self._fast_model if fast else self._model,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(block.text for block in response.content if block.type == "text")

    async def complete_structured(
        self, system: str, user: str, schema: dict[str, Any], *, fast: bool = False
    ) -> dict[str, Any]:
        response = await self._client.messages.create(
            model=self._fast_model if fast else self._model,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": user}],
            tools=[{"name": "submit", "description": "Submit the structured result.", "input_schema": schema}],
            tool_choice={"type": "tool", "name": "submit"},
        )
        for block in response.content:
            if block.type == "tool_use":
                return block.input
        raise ValueError("Anthropic response contained no tool_use block")

    async def stream(self, system: str, user: str, *, fast: bool = False) -> AsyncIterator[str]:
        async with self._client.messages.stream(
            model=self._fast_model if fast else self._model,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": user}],
        ) as stream:
            async for text in stream.text_stream:
                yield text


_provider: AnthropicProvider | None = None


def get_anthropic_provider() -> AnthropicProvider:
    global _provider
    if _provider is None:
        _provider = AnthropicProvider()
    return _provider
