ALTER TABLE game_sessions ADD COLUMN question_pool_json TEXT;
ALTER TABLE game_sessions ADD COLUMN current_index INTEGER NOT NULL DEFAULT 0;
