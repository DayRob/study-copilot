-- Cyber-security watch: parallel to source_files/chunks rather than an
-- extension of them, since SQLite can't cleanly add an "exactly one parent
-- FK" constraint to an existing table without rebuilding it, and this keeps
-- the course-ingestion pipeline untouched.

CREATE TABLE IF NOT EXISTS cyber_items (
    id INTEGER PRIMARY KEY,
    connector TEXT NOT NULL,
    url TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    published_at TEXT,
    fetched_at TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    raw_text TEXT NOT NULL,
    summary TEXT NOT NULL,
    content_type TEXT NOT NULL,
    technical_domain TEXT NOT NULL,
    level TEXT NOT NULL,
    authority_source TEXT NOT NULL,
    referentiel TEXT,
    tags_json TEXT NOT NULL,
    generation_model TEXT NOT NULL,
    last_synced_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cyber_chunks (
    id INTEGER PRIMARY KEY,
    cyber_item_id INTEGER NOT NULL REFERENCES cyber_items(id) ON DELETE CASCADE,
    content_type TEXT NOT NULL CHECK(content_type IN ('prose')),
    text TEXT NOT NULL,
    chunk_index INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_cyber_chunks_item ON cyber_chunks(cyber_item_id);
