import json
from datetime import datetime, timezone
from types import SimpleNamespace

import numpy as np
import pytest

from app.config import get_settings
from app.cyber import pipeline
from app.cyber.connectors.base import RawItem, RawItemRef
from app.db.connection import init_db, get_connection


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

    def fake_embed_documents(texts: list[str]):
        return [np.zeros(get_settings().embedding_dim, dtype=np.float32) for _ in texts]

    monkeypatch.setattr(pipeline, "embed_documents", fake_embed_documents)
    monkeypatch.setattr(pipeline, "get_llm_provider", lambda: FakeLLMProvider())
    yield
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_sync_all_adds_new_items_and_chunks(cyber_env, monkeypatch):
    item = RawItem(
        url="https://example.org/item-1",
        title="Guide de durcissement",
        published_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        text="Un texte assez long pour former au moins un chunk de contenu prose.",
    )
    monkeypatch.setattr(pipeline, "CONNECTORS", {"fake": FakeConnector([item])})
    monkeypatch.setattr(get_settings(), "cyber_connectors", ["fake"])

    stats = await pipeline.sync_all()

    assert stats.items_found == 1
    assert stats.items_added == 1
    assert stats.items_updated == 0
    assert stats.errors == 0

    with get_connection() as conn:
        row = conn.execute("SELECT * FROM cyber_items WHERE url = ?", (item.url,)).fetchone()
        assert row["title"] == item.title
        assert row["authority_source"] == "ANSSI"
        assert row["content_type"] == "guide_bonnes_pratiques"
        assert json.loads(row["tags_json"]) == ["tls", "durcissement"]

        chunks = conn.execute("SELECT * FROM cyber_chunks WHERE cyber_item_id = ?", (row["id"],)).fetchall()
        assert len(chunks) >= 1

        embeddings = conn.execute("SELECT COUNT(*) AS n FROM cyber_chunk_embeddings").fetchone()
        assert embeddings["n"] == len(chunks)


@pytest.mark.asyncio
async def test_sync_all_skips_unchanged_item_on_second_run(cyber_env, monkeypatch):
    item = RawItem(
        url="https://example.org/item-2",
        title="Guide inchangé",
        published_at=None,
        text="Texte identique entre les deux syncs.",
    )
    monkeypatch.setattr(pipeline, "CONNECTORS", {"fake": FakeConnector([item])})
    monkeypatch.setattr(get_settings(), "cyber_connectors", ["fake"])

    first = await pipeline.sync_all()
    second = await pipeline.sync_all()

    assert first.items_added == 1
    assert second.items_added == 0
    assert second.items_skipped == 1


@pytest.mark.asyncio
async def test_sync_all_counts_errors_without_aborting_other_items(cyber_env, monkeypatch):
    good_item = RawItem(
        url="https://example.org/item-ok",
        title="Item valide",
        published_at=None,
        text="Contenu valide.",
    )

    class FlakyConnector(FakeConnector):
        def fetch_item(self, ref: RawItemRef) -> RawItem:
            if ref.url.endswith("item-bad"):
                raise ValueError("boom")
            return super().fetch_item(ref)

    connector = FlakyConnector([good_item])
    # Inject a second ref that will fail in fetch_item.
    monkeypatch.setattr(
        connector, "list_items",
        lambda: [
            RawItemRef(url="https://example.org/item-bad", title="Item cassé", published_at=None),
            RawItemRef(url=good_item.url, title=good_item.title, published_at=None),
        ],
    )
    monkeypatch.setattr(pipeline, "CONNECTORS", {"fake": connector})
    monkeypatch.setattr(get_settings(), "cyber_connectors", ["fake"])

    stats = await pipeline.sync_all()

    assert stats.items_found == 2
    assert stats.errors == 1
    assert stats.items_added == 1
