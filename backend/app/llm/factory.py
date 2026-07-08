from app.config import get_settings
from app.llm.base import LLMProvider


def get_llm_provider() -> LLMProvider:
    settings = get_settings()
    if settings.llm_provider == "ollama":
        from app.llm.ollama_provider import get_ollama_provider

        return get_ollama_provider()

    from app.llm.anthropic_provider import get_anthropic_provider

    return get_anthropic_provider()
