from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    # Absolute path so the backend finds its .env regardless of the process's
    # current working directory (matters when launched from the repo root).
    model_config = SettingsConfigDict(
        env_file=str(BACKEND_DIR / ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    course_roots: list[Path] = []
    db_path: Path = Path("data/study_copilot.db")

    llm_provider: str = "ollama"  # "ollama" (local, free) | "anthropic" (API, paid)

    anthropic_api_key: str | None = None
    llm_model: str = "claude-sonnet-4-5"
    llm_fast_model: str = "claude-haiku-4-5"

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"

    embedding_model: str = "intfloat/multilingual-e5-base"
    embedding_dim: int = 768

    retrieval_top_k: int = 10

    cors_origins: list[str] = ["http://localhost:5173"]

    # Obsidian integration: if set, subject fiches are auto-exported as
    # markdown notes here after every ingestion/regeneration, and this path
    # is also where the personal "Mes Notes" folder lives for round-trip
    # note-taking (see obsidian/export.py, ingestion/watcher.py).
    obsidian_vault_path: Path | None = None

    # Debounce window (seconds) before a detected file change triggers a
    # re-ingestion -- avoids re-syncing on every keystroke while a note is
    # being saved repeatedly by an editor.
    watch_debounce_seconds: float = 8.0

    @property
    def resolved_db_path(self) -> Path:
        path = self.db_path
        if not path.is_absolute():
            path = BACKEND_DIR / path
        path.parent.mkdir(parents=True, exist_ok=True)
        return path


@lru_cache
def get_settings() -> Settings:
    return Settings()
