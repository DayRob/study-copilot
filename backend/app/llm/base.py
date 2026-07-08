from typing import Any, AsyncIterator, Protocol


class LLMProvider(Protocol):
    async def complete(self, system: str, user: str, *, fast: bool = False) -> str:
        """Return a full completion for the given prompt."""
        ...

    async def stream(self, system: str, user: str, *, fast: bool = False) -> AsyncIterator[str]:
        """Yield text deltas as they arrive."""
        ...

    async def complete_structured(
        self, system: str, user: str, schema: dict[str, Any], *, fast: bool = False
    ) -> dict[str, Any]:
        """Return a JSON object conforming to `schema` (forced tool-call output,
        avoids relying on the model to emit valid JSON in free text)."""
        ...
