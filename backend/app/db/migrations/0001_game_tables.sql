ALTER TABLE attempts ADD COLUMN session_id INTEGER REFERENCES game_sessions(id);
ALTER TABLE exercises ADD COLUMN style TEXT;

CREATE TABLE IF NOT EXISTS game_sessions (
    id INTEGER PRIMARY KEY,
    subject_id INTEGER REFERENCES subjects(id),
    status TEXT NOT NULL DEFAULT 'generating' CHECK(status IN ('generating','active','completed','game_over','failed')),
    started_at TEXT NOT NULL,
    ended_at TEXT,
    score INTEGER NOT NULL DEFAULT 0,
    lives_remaining INTEGER NOT NULL DEFAULT 3,
    current_streak INTEGER NOT NULL DEFAULT 0,
    wrong_streak INTEGER NOT NULL DEFAULT 0,
    best_streak INTEGER NOT NULL DEFAULT 0,
    difficulty_tier TEXT NOT NULL DEFAULT 'easy' CHECK(difficulty_tier IN ('easy','medium','hard')),
    questions_answered INTEGER NOT NULL DEFAULT 0,
    questions_correct INTEGER NOT NULL DEFAULT 0,
    xp_earned INTEGER NOT NULL DEFAULT 0,
    error TEXT
);

CREATE TABLE IF NOT EXISTS player_progress (
    subject_id INTEGER,
    xp INTEGER NOT NULL DEFAULT 0,
    level INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL,
    UNIQUE(subject_id)
);
