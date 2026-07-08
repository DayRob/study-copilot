-- Study Copilot schema. One SQLite file holds relational data + vectors (sqlite-vec).

CREATE TABLE IF NOT EXISTS subjects (
    id INTEGER PRIMARY KEY,
    year TEXT NOT NULL,                 -- '4A' | '5A'
    semester TEXT,                      -- nullable
    name TEXT NOT NULL,
    root_path TEXT NOT NULL,
    UNIQUE(year, semester, name)
);

CREATE TABLE IF NOT EXISTS source_files (
    id INTEGER PRIMARY KEY,
    subject_id INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    relative_path TEXT NOT NULL,
    absolute_path TEXT NOT NULL,
    file_type TEXT NOT NULL,            -- 'pdf'|'docx'|'code'|'text'
    content_hash TEXT NOT NULL,
    last_ingested_at TEXT NOT NULL,
    UNIQUE(absolute_path)
);

CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY,
    source_file_id INTEGER NOT NULL REFERENCES source_files(id) ON DELETE CASCADE,
    content_type TEXT NOT NULL CHECK(content_type IN ('prose','code')),
    text TEXT NOT NULL,
    page_start INTEGER,
    page_end INTEGER,
    line_start INTEGER,
    line_end INTEGER,
    language TEXT,
    chunk_index INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_chunks_source_file ON chunks(source_file_id);

CREATE TABLE IF NOT EXISTS topics (
    id INTEGER PRIMARY KEY,
    subject_id INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    mastery_score REAL NOT NULL DEFAULT 0.0,
    last_reviewed_at TEXT,
    next_review_due_at TEXT,
    review_count INTEGER NOT NULL DEFAULT 0,
    UNIQUE(subject_id, name)
);

CREATE TABLE IF NOT EXISTS exercises (
    id INTEGER PRIMARY KEY,
    subject_id INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    topic_id INTEGER REFERENCES topics(id),
    topic TEXT,
    type TEXT NOT NULL CHECK(type IN ('mcq','open','code')),
    prompt TEXT NOT NULL,
    options_json TEXT,
    correct_answer TEXT,
    source_chunk_ids TEXT NOT NULL,
    difficulty TEXT CHECK(difficulty IN ('easy','medium','hard')),
    created_at TEXT NOT NULL,
    generation_model TEXT
);

CREATE TABLE IF NOT EXISTS attempts (
    id INTEGER PRIMARY KEY,
    exercise_id INTEGER NOT NULL REFERENCES exercises(id) ON DELETE CASCADE,
    submitted_answer TEXT NOT NULL,
    is_correct INTEGER,
    score REAL,
    feedback TEXT,
    graded_by TEXT,
    attempted_at TEXT NOT NULL,
    time_taken_seconds INTEGER
);

CREATE TABLE IF NOT EXISTS qa_history (
    id INTEGER PRIMARY KEY,
    subject_id INTEGER REFERENCES subjects(id),
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    chunk_ids_used TEXT NOT NULL,
    asked_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ingest_runs (
    id INTEGER PRIMARY KEY,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    files_scanned INTEGER NOT NULL DEFAULT 0,
    files_added INTEGER NOT NULL DEFAULT 0,
    files_updated INTEGER NOT NULL DEFAULT 0,
    files_deleted INTEGER NOT NULL DEFAULT 0,
    files_skipped INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'running' CHECK(status IN ('running','completed','failed')),
    error TEXT
);

CREATE TABLE IF NOT EXISTS subject_overviews (
    subject_id INTEGER PRIMARY KEY REFERENCES subjects(id) ON DELETE CASCADE,
    summary TEXT NOT NULL,
    key_topics TEXT NOT NULL,      -- JSON array of {concept, explanation}
    examples TEXT NOT NULL,        -- JSON array of {text, relative_path, page_start, page_end, line_start, line_end}
    resources TEXT NOT NULL,       -- JSON array of {label, url}
    generated_at TEXT NOT NULL,
    model TEXT NOT NULL
);

-- sqlite-vec virtual table is created separately at runtime (connection.py)
-- because its column dimension depends on the configured embedding model.
