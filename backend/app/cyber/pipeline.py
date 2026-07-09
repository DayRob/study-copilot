import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

import sqlite_vec

from app.config import get_settings
from app.cyber.connectors import anssi, cert_fr
from app.cyber.connectors.base import RawItemRef
from app.cyber.taxonomy import Taxonomy, load_taxonomy
from app.db.connection import get_connection
from app.ingestion.chunking import OVERLAP_WORDS, TARGET_WORDS, _split_words
from app.ingestion.embed import embed_documents
from app.llm.base import LLMProvider
from app.llm.factory import get_llm_provider

CONNECTORS = {
    "anssi": anssi,
    "cert_fr": cert_fr,
}

TAGGING_SYSTEM_PROMPT = (
    "Tu es un expert en cybersécurité qui classe des publications selon une taxonomie fixe. "
    "Réponds uniquement avec les valeurs autorisées pour content_type, technical_domain et level. "
    "Rédige un résumé reformulé de 2 à 4 phrases -- jamais une copie du texte source."
)


@dataclass
class SyncStats:
    items_found: int = 0
    items_added: int = 0
    items_updated: int = 0
    items_skipped: int = 0
    errors: int = 0


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _build_tagging_schema(taxonomy: Taxonomy) -> dict:
    return {
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": "Résumé reformulé en 2 à 4 phrases, jamais une copie du texte source",
            },
            "content_type": {"type": "string", "enum": taxonomy.content_types},
            "technical_domain": {"type": "string", "enum": taxonomy.technical_domains},
            "level": {"type": "string", "enum": taxonomy.levels},
            "referentiel": {
                "type": "string",
                "description": "Référentiel associé si pertinent (ex: CIS Control 5, MITRE ATT&CK T1078), chaîne vide sinon",
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "3 à 6 mots-clés libres",
            },
        },
        "required": ["summary", "content_type", "technical_domain", "level", "tags"],
    }


async def sync_all(progress_cb=None) -> SyncStats:
    settings = get_settings()
    stats = SyncStats()
    taxonomy = load_taxonomy()
    llm = get_llm_provider()
    schema = _build_tagging_schema(taxonomy)
    active = [CONNECTORS[c] for c in settings.cyber_connectors if c in CONNECTORS]

    refs: list[tuple] = []
    for connector in active:
        for ref in connector.list_items():
            refs.append((connector, ref))
    stats.items_found = len(refs)

    with get_connection() as conn:
        for i, (connector, ref) in enumerate(refs):
            if progress_cb:
                progress_cb(i + 1, len(refs), ref.title)
            try:
                added = await _sync_one(conn, connector, ref, schema, llm)
            except Exception:
                stats.errors += 1
                continue
            if added is None:
                stats.items_skipped += 1
            elif added:
                stats.items_added += 1
            else:
                stats.items_updated += 1

    _sync_obsidian_export()
    return stats


async def _sync_one(
    conn: sqlite3.Connection, connector, ref: RawItemRef, schema: dict, llm: LLMProvider
) -> bool | None:
    """Returns True if the item was newly added, False if updated, None if
    skipped as unchanged."""
    existing = conn.execute("SELECT id, content_hash FROM cyber_items WHERE url = ?", (ref.url,)).fetchone()

    item = connector.fetch_item(ref)
    content_hash = _hash_text(item.text)
    if existing and existing["content_hash"] == content_hash:
        return None

    prompt = f"Titre : {item.title}\n\nTexte :\n{item.text[:6000]}"
    tags = await llm.complete_structured(TAGGING_SYSTEM_PROMPT, prompt, schema, fast=True)

    settings = get_settings()
    now = datetime.now(timezone.utc).isoformat()
    published_at = item.published_at.isoformat() if item.published_at else None
    referentiel = tags.get("referentiel") or None
    model_used = settings.ollama_model if settings.llm_provider == "ollama" else settings.llm_fast_model

    cur = conn.execute(
        """
        INSERT INTO cyber_items
            (connector, url, title, published_at, fetched_at, content_hash, raw_text, summary,
             content_type, technical_domain, level, authority_source, referentiel, tags_json,
             generation_model, last_synced_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(url) DO UPDATE SET
            title = excluded.title,
            published_at = excluded.published_at,
            fetched_at = excluded.fetched_at,
            content_hash = excluded.content_hash,
            raw_text = excluded.raw_text,
            summary = excluded.summary,
            content_type = excluded.content_type,
            technical_domain = excluded.technical_domain,
            level = excluded.level,
            referentiel = excluded.referentiel,
            tags_json = excluded.tags_json,
            generation_model = excluded.generation_model,
            last_synced_at = excluded.last_synced_at
        RETURNING id
        """,
        (
            connector.name, ref.url, item.title, published_at, now, content_hash, item.text,
            tags["summary"], tags["content_type"], tags["technical_domain"], tags["level"],
            connector.authority_source, referentiel, json.dumps(tags.get("tags", [])),
            model_used, now,
        ),
    )
    cyber_item_id = cur.fetchone()["id"]
    conn.execute("DELETE FROM cyber_chunks WHERE cyber_item_id = ?", (cyber_item_id,))

    pieces = _split_words(item.text, TARGET_WORDS, OVERLAP_WORDS) or ([item.text] if item.text.strip() else [])
    embeddings = embed_documents(pieces)
    for idx, (piece, vector) in enumerate(zip(pieces, embeddings)):
        chunk_cur = conn.execute(
            "INSERT INTO cyber_chunks (cyber_item_id, content_type, text, chunk_index) VALUES (?, 'prose', ?, ?)",
            (cyber_item_id, piece, idx),
        )
        chunk_id = chunk_cur.lastrowid
        conn.execute(
            "INSERT INTO cyber_chunk_embeddings (chunk_id, embedding) VALUES (?, ?)",
            (chunk_id, sqlite_vec.serialize_float32(vector.tolist())),
        )
    conn.commit()

    return existing is None


def _sync_obsidian_export() -> None:
    """Best-effort, mirrors ingestion/pipeline.py::_sync_obsidian_export --
    never fails the sync itself."""
    try:
        from app.obsidian.cyber_export import export_cyber_to_obsidian

        export_cyber_to_obsidian()
    except Exception:
        pass
