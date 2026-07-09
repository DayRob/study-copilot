from datetime import datetime, timezone

import numpy as np
import pytest

import app.rag.retriever as retriever_module
from app.config import get_settings
from app.cyber import pipeline
from app.cyber.connectors.base import RawItem, RawItemRef
from app.db.connection import init_db
from app.rag.retriever import retrieve


class FakeConnector:
    name = "fake"
    authority_source = "ANSSI"

    def __init__(self, items: list[RawItem]):
        self._items = {item.url: item for item in items}

    def list_items(self) -> list[RawItemRef]:
        return [RawItemRef(url=i.url, title=i.title, published_at=i.published_at) for i in self._items.values()]

    def fetch_item(self, ref: RawItemRef) -> RawItem:
        return self._items[ref.url]


class FakeLLMProvider:
    async def complete(self, system, user, *, fast=False):
        raise NotImplementedError

    async def stream(self, system, user, *, fast=False):
        raise NotImplementedError

    async def complete_structured(self, system, user, schema, *, fast=False):
        return {
            "summary": "Resume reformule de test.",
            "content_type": "guide_bonnes_pratiques",
            "technical_domain": "reseau",
            "level": "fondamental",
            "referentiel": "",
            "tags": ["tls", "durcissement"],
        }


@pytest.fixture
def cyber_env(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    get_settings.cache_clear()
    init_db()

    dim = get_settings().embedding_dim

    def fake_embed_documents(texts: list[str]):
        return [np.ones(dim, dtype=np.float32) for _ in texts]

    def fake_embed_query(text: str):
        return np.ones(dim, dtype=np.float32)

    monkeypatch.setattr(pipeline, "embed_documents", fake_embed_documents)
    monkeypatch.setattr(pipeline, "get_llm_provider", lambda: FakeLLMProvider())
    monkeypatch.setattr(retriever_module, "embed_query", fake_embed_query)
    yield
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_pipeline_produced_chunk_is_retrievable_end_to_end(cyber_env, monkeypatch):
    item = RawItem(
        url="https://example.org/item-integration",
        title="Guide integration pipeline-retriever",
        published_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        text="Un texte distinctif sur le durcissement TLS pour verifier la chaine complete.",
    )
    monkeypatch.setattr(pipeline, "CONNECTORS", {"fake": FakeConnector([item])})
    monkeypatch.setattr(get_settings(), "cyber_connectors", ["fake"])

    stats = await pipeline.sync_all()
    assert stats.items_added == 1
    assert stats.errors == 0

    results = retrieve("durcissement TLS", top_k=10)

    matching = [r for r in results if r.absolute_path == item.url]
    assert matching, "pipeline-produced item was not retrievable via retrieve()"
    result = matching[0]
    assert result.subject_name == "ANSSI"
    assert result.absolute_path == item.url
    assert result.subject_id is None
