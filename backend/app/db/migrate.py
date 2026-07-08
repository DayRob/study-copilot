import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
VERSION_PATTERN = re.compile(r"^(\d+)_")


def _migration_files() -> list[Path]:
    if not MIGRATIONS_DIR.exists():
        return []
    return sorted(MIGRATIONS_DIR.glob("*.sql"))


def run_migrations(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """
    )
    applied = {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}

    for path in _migration_files():
        match = VERSION_PATTERN.match(path.name)
        if not match:
            continue
        version = int(match.group(1))
        if version in applied:
            continue
        try:
            conn.executescript(path.read_text(encoding="utf-8"))
        except sqlite3.Error as exc:
            # A partial failure here (e.g. one ALTER of several succeeds, the
            # next fails) leaves the version unrecorded, so a plain re-raise
            # would make every future startup retry the same script from
            # scratch and immediately fail again on the already-applied
            # statement ("duplicate column"), permanently blocking boot with
            # no clue which migration or statement was at fault. Fail loudly
            # and specifically instead.
            raise RuntimeError(
                f"Migration '{path.name}' (version {version}) failed partway through: {exc}. "
                "The database may be partially migrated -- inspect it manually before retrying "
                "(e.g. check which of this file's statements already applied)."
            ) from exc
        conn.execute(
            "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
            (version, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
