# Veille Culture Cyber Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a cyber-security watch/knowledge-capitalization pipeline (ANSSI + CERT-FR connectors) to Study Copilot, feeding the same RAG index and Obsidian export as the existing course-ingestion pipeline.

**Architecture:** A new `backend/app/cyber/` module (connectors → pipeline → storage) parallel to `ingestion/`, reusing the existing LLM provider abstraction, embedding pipeline, sqlite-vec storage pattern, and Obsidian export conventions. `rag/retriever.py` is extended to merge KNN results from a new `cyber_chunk_embeddings` vec table with the existing `chunk_embeddings` table, so Q&A/citations work unchanged.

**Tech Stack:** Python 3.11+, FastAPI, SQLite + sqlite-vec, `httpx` (already a dependency), `feedparser` (RSS/Atom), `beautifulsoup4` (HTML fallback for ANSSI), `PyYAML` (taxonomy config), `pytest` + `pytest-asyncio` (test infra — new to this repo), React/TypeScript + `@tanstack/react-query` (frontend, matches existing `Subjects.tsx`).

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-08-cyber-veille-design.md` — every requirement in it must map to a task below.
- No live network calls in tests — all connector/HTTP tests use recorded fixtures or hand-built `httpx.Response` objects.
- Respect `robots.txt` and per-domain rate limiting for every real HTTP request (verified: `cyber.gouv.fr/robots.txt` allows `/actualites`; `cert.ssi.gouv.fr/robots.txt` only disallows `/pdf`, `/tar`, `/js`, `/fonts`, `/fiche/`, so `/avis/` and `/alerte/` feeds and pages are allowed).
- Manual trigger only for the MVP (`POST /cyber/sync`), no cron/scheduler.
- Obsidian export folder: `Cours CPE/Culture Cyber/` under the existing vault root (`settings.obsidian_vault_path`), never fails the sync pipeline (best-effort, mirrors `ingestion/pipeline.py::_sync_obsidian_export`).
- No hardcoded taxonomy values in Python — everything comes from `backend/app/cyber/taxonomy.yaml`.
- Deviation from the spec, noted here for the record: the spec's `cyber_sync_runs` table is **dropped**. Inspection of the existing codebase found that `schema.sql`'s `ingest_runs` table is defined but never written to — `ingest.py` only tracks run state in an in-memory dict. To match actual (not aspirational) existing behavior, `/cyber/status` uses the same in-memory pattern as `/ingest/status`, no new table.
- All new backend code follows existing style: plain functions/modules (not classes) for connectors and pipeline steps, matching `ingestion/*.py`.
- Commands below assume the working directory is the repo root unless a task says `cd backend` / `cd frontend`.

---

### Task 1: Test infra, dependencies, and cyber settings

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/app/config.py`
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/conftest.py`
- Test: `backend/tests/test_config.py`

**Interfaces:**
- Produces: `Settings.cyber_connectors: list[str]`, `Settings.cyber_rate_limit_seconds: float`, `Settings.cyber_user_agent: str` (consumed by Tasks 4, 7, 9).
- Produces: `backend/tests/conftest.py` fixture `tmp_settings_env` is NOT needed — tests use `pytest`'s built-in `monkeypatch` fixture directly against `app.config.get_settings` cache, see Step 4.

- [ ] **Step 1: Add new dependencies to `backend/pyproject.toml`**

Edit the `dependencies` list to add:

```toml
    "feedparser>=6.0",
    "beautifulsoup4>=4.12",
    "pyyaml>=6.0",
```

Add a new section for dev/test dependencies:

```toml
[dependency-groups]
dev = [
    "pytest>=8.3",
    "pytest-asyncio>=0.24",
]
```

And add pytest config so `uv run pytest` finds tests without extra flags:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

- [ ] **Step 2: Install dependencies**

Run: `cd backend && uv sync --group dev`
Expected: exits 0, lockfile updated, `pytest` and `feedparser`/`beautifulsoup4`/`pyyaml` importable.

- [ ] **Step 3: Add cyber settings to `backend/app/config.py`**

Add these fields to the `Settings` class (after `watch_debounce_seconds`):

```python
    # Cyber-security watch (ANSSI/CERT-FR/...): which connectors to run on
    # POST /cyber/sync, and the shared HTTP politeness settings for all of them.
    cyber_connectors: list[str] = ["anssi", "cert_fr"]
    cyber_rate_limit_seconds: float = 3.0
    cyber_user_agent: str = "StudyCopilotCyberBot/0.1 (usage personnel, non commercial)"
```

- [ ] **Step 4: Write a test confirming settings load with sane defaults**

Create `backend/tests/__init__.py` (empty file).

Create `backend/tests/conftest.py`:

```python
import pytest

from app.config import get_settings


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    """Settings is an lru_cache singleton; clear it around each test so a
    test that monkeypatches env vars doesn't leak into the next test."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
```

Create `backend/tests/test_config.py`:

```python
from app.config import get_settings


def test_cyber_settings_defaults():
    settings = get_settings()
    assert settings.cyber_connectors == ["anssi", "cert_fr"]
    assert settings.cyber_rate_limit_seconds == 3.0
    assert "StudyCopilotCyberBot" in settings.cyber_user_agent
```

- [ ] **Step 5: Run the test**

Run: `cd backend && uv run pytest tests/test_config.py -v`
Expected: `1 passed`

- [ ] **Step 6: Commit**

```bash
git add backend/pyproject.toml backend/uv.lock backend/app/config.py backend/tests/__init__.py backend/tests/conftest.py backend/tests/test_config.py
git commit -m "feat(cyber): add dependencies, settings, and test infra for cyber veille"
```

---

### Task 2: Database schema for cyber content

**Files:**
- Create: `backend/app/db/migrations/0003_cyber_veille.sql`
- Modify: `backend/app/db/connection.py`
- Test: `backend/tests/test_cyber_schema.py`

**Interfaces:**
- Produces: tables `cyber_items`, `cyber_chunks`; vec0 virtual table `cyber_chunk_embeddings(chunk_id, embedding)`. Consumed by Tasks 7 (pipeline writes), 8 (retriever reads), 10 (API reads), 11 (Obsidian export reads).

- [ ] **Step 1: Write the migration**

Create `backend/app/db/migrations/0003_cyber_veille.sql`:

```sql
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
```

- [ ] **Step 2: Register the vec0 table and cleanup trigger in `connection.py`**

In `backend/app/db/connection.py`, inside `init_db()`, right after the existing `chunk_embeddings` virtual table + `trg_chunks_delete_embeddings` trigger block (before `conn.commit()`), add:

```python
        conn.execute(
            f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS cyber_chunk_embeddings USING vec0(
                chunk_id INTEGER PRIMARY KEY,
                embedding FLOAT[{settings.embedding_dim}]
            )
            """
        )
        conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS trg_cyber_chunks_delete_embeddings
            AFTER DELETE ON cyber_chunks
            BEGIN
                DELETE FROM cyber_chunk_embeddings WHERE chunk_id = OLD.id;
            END
            """
        )
```

- [ ] **Step 3: Write a test that the new tables and vec0 table exist and enforce their constraints**

Create `backend/tests/test_cyber_schema.py`:

```python
import sqlite3

import pytest

from app.config import get_settings
from app.db.connection import init_db, get_connection


@pytest.fixture
def cyber_db(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    get_settings.cache_clear()
    init_db()
    yield
    get_settings.cache_clear()


def test_cyber_items_and_chunks_tables_exist(cyber_db):
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO cyber_items
                (connector, url, title, fetched_at, content_hash, raw_text, summary,
                 content_type, technical_domain, level, authority_source, tags_json,
                 generation_model, last_synced_at)
            VALUES ('anssi', 'https://example.org/a', 'Titre', '2026-01-01T00:00:00Z', 'hash',
                    'texte', 'resume', 'guide_bonnes_pratiques', 'reseau', 'fondamental',
                    'ANSSI', '[]', 'llama3.1:8b', '2026-01-01T00:00:00Z')
            """
        )
        item_id = conn.execute("SELECT id FROM cyber_items WHERE url = ?", ("https://example.org/a",)).fetchone()["id"]
        conn.execute(
            "INSERT INTO cyber_chunks (cyber_item_id, content_type, text, chunk_index) VALUES (?, 'prose', 'chunk', 0)",
            (item_id,),
        )
        conn.commit()

        rows = conn.execute("SELECT * FROM cyber_chunks WHERE cyber_item_id = ?", (item_id,)).fetchall()
        assert len(rows) == 1


def test_cyber_chunk_content_type_check_constraint(cyber_db):
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO cyber_items
                (connector, url, title, fetched_at, content_hash, raw_text, summary,
                 content_type, technical_domain, level, authority_source, tags_json,
                 generation_model, last_synced_at)
            VALUES ('anssi', 'https://example.org/b', 'Titre', '2026-01-01T00:00:00Z', 'hash',
                    'texte', 'resume', 'guide_bonnes_pratiques', 'reseau', 'fondamental',
                    'ANSSI', '[]', 'llama3.1:8b', '2026-01-01T00:00:00Z')
            """
        )
        item_id = conn.execute("SELECT id FROM cyber_items WHERE url = ?", ("https://example.org/b",)).fetchone()["id"]
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO cyber_chunks (cyber_item_id, content_type, text, chunk_index) VALUES (?, 'code', 'x', 0)",
                (item_id,),
            )


def test_cyber_chunk_embeddings_vec_table_exists(cyber_db):
    with get_connection() as conn:
        # A functioning vec0 table accepts a query against `embedding MATCH ?`
        # without raising -- this is the simplest way to confirm the virtual
        # table (not a regular table) was created with the right shape.
        rows = conn.execute(
            "SELECT COUNT(*) AS n FROM cyber_chunk_embeddings"
        ).fetchall()
        assert rows[0]["n"] == 0
```

- [ ] **Step 4: Run the tests**

Run: `cd backend && uv run pytest tests/test_cyber_schema.py -v`
Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/app/db/migrations/0003_cyber_veille.sql backend/app/db/connection.py backend/tests/test_cyber_schema.py
git commit -m "feat(cyber): add cyber_items/cyber_chunks tables and cyber_chunk_embeddings vec0 table"
```

---

### Task 3: Taxonomy config and loader

**Files:**
- Create: `backend/app/cyber/__init__.py`
- Create: `backend/app/cyber/taxonomy.yaml`
- Create: `backend/app/cyber/taxonomy.py`
- Test: `backend/tests/cyber/test_taxonomy.py`
- Create: `backend/tests/cyber/__init__.py`

**Interfaces:**
- Produces: `Taxonomy` dataclass (`content_types`, `technical_domains`, `levels`, `authority_sources`: all `list[str]`) and `load_taxonomy() -> Taxonomy`. Consumed by Task 7 (pipeline tagging schema).

- [ ] **Step 1: Create the package and taxonomy config**

Create `backend/app/cyber/__init__.py` (empty file).

Create `backend/app/cyber/taxonomy.yaml`:

```yaml
content_type:
  - referentiel_norme
  - guide_bonnes_pratiques
  - alerte_vulnerabilite
  - fiche_protocole
  - fiche_outil
  - actualite

technical_domain:
  - reseau
  - cryptographie
  - iam
  - infrastructure
  - cloud
  - applicatif_dev
  - gouvernance_conformite
  - reponse_incident

level:
  - fondamental
  - avance

authority_source:
  - ANSSI
  - CERT-FR
  - ENISA
  - NIST
  - MITRE
  - OWASP
  - CIS
```

- [ ] **Step 2: Write the failing test**

Create `backend/tests/cyber/__init__.py` (empty file).

Create `backend/tests/cyber/test_taxonomy.py`:

```python
from app.cyber.taxonomy import load_taxonomy


def test_load_taxonomy_returns_all_axes():
    taxonomy = load_taxonomy()
    assert "guide_bonnes_pratiques" in taxonomy.content_types
    assert "reseau" in taxonomy.technical_domains
    assert taxonomy.levels == ["fondamental", "avance"]
    assert "ANSSI" in taxonomy.authority_sources
    assert "CERT-FR" in taxonomy.authority_sources
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/cyber/test_taxonomy.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.cyber.taxonomy'`

- [ ] **Step 4: Implement the loader**

Create `backend/app/cyber/taxonomy.py`:

```python
from dataclasses import dataclass
from pathlib import Path

import yaml

TAXONOMY_PATH = Path(__file__).parent / "taxonomy.yaml"


@dataclass
class Taxonomy:
    content_types: list[str]
    technical_domains: list[str]
    levels: list[str]
    authority_sources: list[str]


def load_taxonomy(path: Path = TAXONOMY_PATH) -> Taxonomy:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return Taxonomy(
        content_types=data["content_type"],
        technical_domains=data["technical_domain"],
        levels=data["level"],
        authority_sources=data["authority_source"],
    )
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd backend && uv run pytest tests/cyber/test_taxonomy.py -v`
Expected: `1 passed`

- [ ] **Step 6: Commit**

```bash
git add backend/app/cyber/__init__.py backend/app/cyber/taxonomy.yaml backend/app/cyber/taxonomy.py backend/tests/cyber/__init__.py backend/tests/cyber/test_taxonomy.py
git commit -m "feat(cyber): add externalized taxonomy config and loader"
```

---

### Task 4: Connector protocol and shared HTTP client (robots.txt + rate limit)

**Files:**
- Create: `backend/app/cyber/connectors/__init__.py`
- Create: `backend/app/cyber/connectors/base.py`
- Create: `backend/app/cyber/http_client.py`
- Test: `backend/tests/cyber/test_http_client.py`

**Interfaces:**
- Produces: `RawItemRef(url, title, published_at)`, `RawItem(url, title, published_at, text)` dataclasses (consumed by Tasks 5, 6, 7). `fetch(url: str) -> httpx.Response` and `is_allowed(robots_txt: str, user_agent: str, url: str) -> bool` (consumed by Tasks 5, 6).

- [ ] **Step 1: Write the connector data model**

Create `backend/app/cyber/connectors/__init__.py` (empty file).

Create `backend/app/cyber/connectors/base.py`:

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass
class RawItemRef:
    url: str
    title: str
    published_at: datetime | None


@dataclass
class RawItem:
    url: str
    title: str
    published_at: datetime | None
    text: str


class Connector(Protocol):
    """Documents the shape every connector module (anssi.py, cert_fr.py,
    ...) must expose. Connectors are plain modules, not classes -- matches
    the rest of this codebase's style (ingestion/*.py)."""

    name: str
    authority_source: str

    def list_items(self) -> list[RawItemRef]: ...
    def fetch_item(self, ref: RawItemRef) -> RawItem: ...
```

- [ ] **Step 2: Write the failing tests for the HTTP client's pure logic**

Create `backend/tests/cyber/test_http_client.py`:

```python
from app.cyber.http_client import is_allowed, _sleep_duration


ROBOTS_TXT = """User-agent: *
Disallow: /pdf
Disallow: /fiche/
"""


def test_is_allowed_true_for_unrestricted_path():
    assert is_allowed(ROBOTS_TXT, "StudyCopilotCyberBot/0.1", "https://example.org/avis/x") is True


def test_is_allowed_false_for_disallowed_path():
    assert is_allowed(ROBOTS_TXT, "StudyCopilotCyberBot/0.1", "https://example.org/fiche/x") is False


def test_sleep_duration_zero_on_first_request():
    assert _sleep_duration(last_request_monotonic=None, now=100.0, min_interval=3.0) == 0.0


def test_sleep_duration_waits_remaining_time():
    assert _sleep_duration(last_request_monotonic=100.0, now=101.0, min_interval=3.0) == 2.0


def test_sleep_duration_zero_once_interval_elapsed():
    assert _sleep_duration(last_request_monotonic=100.0, now=105.0, min_interval=3.0) == 0.0
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/cyber/test_http_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.cyber.http_client'`

- [ ] **Step 4: Implement the HTTP client**

Create `backend/app/cyber/http_client.py`:

```python
import time
import urllib.robotparser as robotparser
from urllib.parse import urlparse

import httpx

from app.config import get_settings

_last_request_at: dict[str, float] = {}
_robots_parsers: dict[str, robotparser.RobotFileParser | None] = {}


def is_allowed(robots_txt: str, user_agent: str, url: str) -> bool:
    """Pure function (no network) so it's directly unit-testable: parses a
    robots.txt string and checks whether `user_agent` may fetch `url`."""
    parser = robotparser.RobotFileParser()
    parser.parse(robots_txt.splitlines())
    return parser.can_fetch(user_agent, url)


def _sleep_duration(last_request_monotonic: float | None, now: float, min_interval: float) -> float:
    """Pure function: how long to sleep before the next request to a domain
    we've already hit, given `now` and the last request's monotonic time."""
    if last_request_monotonic is None:
        return 0.0
    elapsed = now - last_request_monotonic
    return max(0.0, min_interval - elapsed)


def _get_robots_txt(domain: str) -> str | None:
    if domain in _robots_parsers:
        pass
    try:
        response = httpx.get(f"https://{domain}/robots.txt", timeout=10)
        return response.text if response.status_code == 200 else None
    except httpx.HTTPError:
        return None


def fetch(url: str) -> httpx.Response:
    """GET a URL, respecting robots.txt and a per-domain rate limit. Raises
    PermissionError if robots.txt disallows the path for our User-Agent."""
    settings = get_settings()
    domain = urlparse(url).netloc

    if domain not in _robots_parsers:
        robots_txt = _get_robots_txt(domain)
        _robots_parsers[domain] = robots_txt
    robots_txt = _robots_parsers[domain]
    if robots_txt is not None and not is_allowed(robots_txt, settings.cyber_user_agent, url):
        raise PermissionError(f"robots.txt disallows fetching {url} for {settings.cyber_user_agent}")

    now = time.monotonic()
    wait = _sleep_duration(_last_request_at.get(domain), now, settings.cyber_rate_limit_seconds)
    if wait > 0:
        time.sleep(wait)
    _last_request_at[domain] = time.monotonic()

    response = httpx.get(url, headers={"User-Agent": settings.cyber_user_agent}, timeout=20, follow_redirects=True)
    response.raise_for_status()
    return response
```

(Note: `_robots_parsers` here caches the raw robots.txt text per domain, not a `RobotFileParser` object — simpler, and `is_allowed` re-parses it fresh each call. Fine at this call volume.)

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/cyber/test_http_client.py -v`
Expected: `5 passed`

- [ ] **Step 6: Commit**

```bash
git add backend/app/cyber/connectors/__init__.py backend/app/cyber/connectors/base.py backend/app/cyber/http_client.py backend/tests/cyber/test_http_client.py
git commit -m "feat(cyber): add connector protocol and robots.txt/rate-limit-aware HTTP client"
```

---

### Task 5: CERT-FR connector (RSS-based)

**Files:**
- Create: `backend/app/cyber/connectors/cert_fr.py`
- Create: `backend/tests/cyber/fixtures/cert_fr_avis_feed.xml`
- Create: `backend/tests/cyber/fixtures/cert_fr_article.html`
- Test: `backend/tests/cyber/test_cert_fr_connector.py`

**Interfaces:**
- Consumes: `RawItemRef`, `RawItem` (Task 4), `app.cyber.http_client.fetch` (Task 4, monkeypatched in tests).
- Produces: `cert_fr.name = "cert_fr"`, `cert_fr.authority_source = "CERT-FR"`, `cert_fr.list_items() -> list[RawItemRef]`, `cert_fr.fetch_item(ref) -> RawItem`. Consumed by Task 7 (pipeline connector registry).

- [ ] **Step 1: Create fixtures**

Create `backend/tests/cyber/fixtures/cert_fr_avis_feed.xml` (a synthetic 2-item feed, structurally identical to the real CERT-FR RSS 2.0 feed confirmed at `https://www.cert.ssi.gouv.fr/avis/feed/`):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>CERT-FR</title>
    <link>https://www.cert.ssi.gouv.fr/avis/</link>
    <description>Centre gouvernemental de veille, d'alerte et de reponse aux attaques informatiques.</description>
    <item>
      <title>Multiples vulnerabilites dans un exemple de produit (01 janvier 2026)</title>
      <link>https://www.cert.ssi.gouv.fr/avis/CERTFR-2026-AVI-0001/</link>
      <description>Description synthetique de l'avis de test.</description>
      <pubDate>Thu, 01 Jan 2026 00:00:00 +0000</pubDate>
      <guid>CERTFR-2026-AVI-0001</guid>
    </item>
    <item>
      <title>Vulnerabilite critique dans un autre produit (02 janvier 2026)</title>
      <link>https://www.cert.ssi.gouv.fr/avis/CERTFR-2026-AVI-0002/</link>
      <description>Autre description synthetique.</description>
      <pubDate>Fri, 02 Jan 2026 00:00:00 +0000</pubDate>
      <guid>CERTFR-2026-AVI-0002</guid>
    </item>
  </channel>
</rss>
```

Create `backend/tests/cyber/fixtures/cert_fr_article.html`:

```html
<!DOCTYPE html>
<html lang="fr">
<head><title>CERTFR-2026-AVI-0001</title></head>
<body>
  <nav>Menu de navigation a ignorer</nav>
  <main>
    <h1>Multiples vulnerabilites dans un exemple de produit</h1>
    <p>Une vulnerabilite permet a un attaquant de provoquer une execution de code arbitraire a distance.</p>
    <p>Solution : appliquer le correctif fourni par l'editeur des que possible.</p>
  </main>
  <footer>Pied de page a ignorer</footer>
</body>
</html>
```

- [ ] **Step 2: Write the failing test**

Create `backend/tests/cyber/test_cert_fr_connector.py`:

```python
from pathlib import Path

import httpx
import pytest

from app.cyber.connectors import cert_fr
from app.cyber.connectors.base import RawItemRef

FIXTURES = Path(__file__).parent / "fixtures"


def _fake_fetch(fixture_name: str):
    text = (FIXTURES / fixture_name).read_text(encoding="utf-8")

    def _fetch(url: str) -> httpx.Response:
        return httpx.Response(200, content=text.encode("utf-8"))

    return _fetch


def test_list_items_parses_rss_feed(monkeypatch):
    monkeypatch.setattr(cert_fr, "FEED_URLS", ["https://www.cert.ssi.gouv.fr/avis/feed/"])
    monkeypatch.setattr(cert_fr, "fetch", _fake_fetch("cert_fr_avis_feed.xml"))

    items = cert_fr.list_items()

    assert len(items) == 2
    assert items[0].url == "https://www.cert.ssi.gouv.fr/avis/CERTFR-2026-AVI-0001/"
    assert "exemple de produit" in items[0].title
    assert items[0].published_at.year == 2026
    assert items[0].published_at.month == 1
    assert items[0].published_at.day == 1


def test_fetch_item_extracts_article_text(monkeypatch):
    monkeypatch.setattr(cert_fr, "fetch", _fake_fetch("cert_fr_article.html"))
    ref = RawItemRef(
        url="https://www.cert.ssi.gouv.fr/avis/CERTFR-2026-AVI-0001/",
        title="Multiples vulnerabilites dans un exemple de produit (01 janvier 2026)",
        published_at=None,
    )

    item = cert_fr.fetch_item(ref)

    assert "execution de code arbitraire" in item.text
    assert "Menu de navigation" not in item.text
    assert "Pied de page" not in item.text
    assert item.url == ref.url
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/cyber/test_cert_fr_connector.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.cyber.connectors.cert_fr'`

- [ ] **Step 4: Implement the connector**

Create `backend/app/cyber/connectors/cert_fr.py`:

```python
from datetime import datetime, timezone

import feedparser

from app.cyber.connectors.base import RawItem, RawItemRef
from app.cyber.http_client import fetch

name = "cert_fr"
authority_source = "CERT-FR"

# CERT-FR publishes separate RSS feeds per bulletin category; both are
# allowed by https://www.cert.ssi.gouv.fr/robots.txt (only /pdf, /tar, /js,
# /fonts, /fiche/ are disallowed there).
FEED_URLS = [
    "https://www.cert.ssi.gouv.fr/avis/feed/",
    "https://www.cert.ssi.gouv.fr/alerte/feed/",
]


def list_items() -> list[RawItemRef]:
    items: list[RawItemRef] = []
    for feed_url in FEED_URLS:
        response = fetch(feed_url)
        parsed = feedparser.parse(response.text)
        for entry in parsed.entries:
            items.append(
                RawItemRef(url=entry.link, title=entry.title, published_at=_entry_published_at(entry))
            )
    return items


def _entry_published_at(entry) -> datetime | None:
    if getattr(entry, "published_parsed", None) is None:
        return None
    return datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)


def fetch_item(ref: RawItemRef) -> RawItem:
    response = fetch(ref.url)
    text = _extract_article_text(response.text)
    return RawItem(url=ref.url, title=ref.title, published_at=ref.published_at, text=text)


def _extract_article_text(html: str) -> str:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer"]):
        tag.decompose()
    main = soup.find("main") or soup.find("article") or soup
    return "\n".join(line.strip() for line in main.get_text("\n").splitlines() if line.strip())
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/cyber/test_cert_fr_connector.py -v`
Expected: `2 passed`

- [ ] **Step 6: Commit**

```bash
git add backend/app/cyber/connectors/cert_fr.py backend/tests/cyber/fixtures/cert_fr_avis_feed.xml backend/tests/cyber/fixtures/cert_fr_article.html backend/tests/cyber/test_cert_fr_connector.py
git commit -m "feat(cyber): add CERT-FR connector (RSS-based)"
```

---

### Task 6: ANSSI connector (HTML scraping fallback)

**Files:**
- Create: `backend/app/cyber/connectors/anssi.py`
- Create: `backend/tests/cyber/fixtures/anssi_listing.html`
- Create: `backend/tests/cyber/fixtures/anssi_article.html`
- Test: `backend/tests/cyber/test_anssi_connector.py`

**Interfaces:**
- Consumes: `RawItemRef`, `RawItem` (Task 4), `app.cyber.http_client.fetch` (Task 4, monkeypatched in tests).
- Produces: `anssi.name = "anssi"`, `anssi.authority_source = "ANSSI"`, `anssi.list_items() -> list[RawItemRef]`, `anssi.fetch_item(ref) -> RawItem`. Consumed by Task 7.

ANSSI (cyber.gouv.fr) has no RSS/Atom feed (confirmed by inspecting the homepage), so this connector scrapes the `/actualites` listing HTML — the documented last-resort per the design. Confirmed against the real page: each card's title is an `<a>` inside an `<h3>` linking to `/actualites/<slug>/`, and a "Publié le <date>" text sits nearby in the same card. `/actualites` is not disallowed by `cyber.gouv.fr/robots.txt`.

- [ ] **Step 1: Create fixtures**

Create `backend/tests/cyber/fixtures/anssi_listing.html` (a synthetic 2-card listing, structurally modeled on the real page):

```html
<!DOCTYPE html>
<html lang="fr">
<body>
  <main>
    <div class="listing">
      <article class="card">
        <img src="/img1.png" alt="" />
        <h3><a href="/actualites/exemple-de-publication-test/">Exemple de publication de test</a></h3>
        <p class="meta">Publié le 03/01/2026</p>
      </article>
      <article class="card">
        <img src="/img2.png" alt="" />
        <h3><a href="/actualites/second-exemple-de-test/">Second exemple de test</a></h3>
        <p class="meta">Publié le 4 janvier 2026</p>
      </article>
      <h3><a href="/actualites">Toutes les actualites</a></h3>
    </div>
  </main>
</body>
</html>
```

Create `backend/tests/cyber/fixtures/anssi_article.html`:

```html
<!DOCTYPE html>
<html lang="fr">
<head><title>Exemple de publication de test</title></head>
<body>
  <header>Menu ANSSI a ignorer</header>
  <article>
    <h1>Exemple de publication de test</h1>
    <p>Ce guide decrit une bonne pratique de durcissement reseau pour les administrateurs systeme.</p>
  </article>
  <footer>Pied de page a ignorer</footer>
</body>
</html>
```

- [ ] **Step 2: Write the failing test**

Create `backend/tests/cyber/test_anssi_connector.py`:

```python
from pathlib import Path

import httpx

from app.cyber.connectors import anssi
from app.cyber.connectors.base import RawItemRef

FIXTURES = Path(__file__).parent / "fixtures"


def _fake_fetch(fixture_name: str):
    text = (FIXTURES / fixture_name).read_text(encoding="utf-8")

    def _fetch(url: str) -> httpx.Response:
        return httpx.Response(200, content=text.encode("utf-8"))

    return _fetch


def test_list_items_parses_listing_and_skips_the_nav_link(monkeypatch):
    monkeypatch.setattr(anssi, "fetch", _fake_fetch("anssi_listing.html"))

    items = anssi.list_items()

    assert len(items) == 2
    assert items[0].url == "https://www.cyber.gouv.fr/actualites/exemple-de-publication-test/"
    assert items[0].title == "Exemple de publication de test"
    assert items[0].published_at.year == 2026
    assert items[0].published_at.month == 1
    assert items[0].published_at.day == 3
    # Second card's date is in the French "4 janvier 2026" long form.
    assert items[1].published_at.month == 1
    assert items[1].published_at.day == 4


def test_fetch_item_extracts_article_text(monkeypatch):
    monkeypatch.setattr(anssi, "fetch", _fake_fetch("anssi_article.html"))
    ref = RawItemRef(
        url="https://www.cyber.gouv.fr/actualites/exemple-de-publication-test/",
        title="Exemple de publication de test",
        published_at=None,
    )

    item = anssi.fetch_item(ref)

    assert "durcissement reseau" in item.text
    assert "Menu ANSSI" not in item.text
    assert "Pied de page" not in item.text
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/cyber/test_anssi_connector.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.cyber.connectors.anssi'`

- [ ] **Step 4: Implement the connector**

Create `backend/app/cyber/connectors/anssi.py`:

```python
import re
from datetime import datetime

from app.cyber.connectors.base import RawItem, RawItemRef
from app.cyber.http_client import fetch

name = "anssi"
authority_source = "ANSSI"

LISTING_URL = "https://www.cyber.gouv.fr/actualites"
BASE_URL = "https://www.cyber.gouv.fr"

_MONTHS_FR = {
    "janvier": 1, "février": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
    "juillet": 7, "août": 8, "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12,
}


def list_items() -> list[RawItemRef]:
    response = fetch(LISTING_URL)
    return _parse_listing(response.text)


def _parse_listing(html: str) -> list[RawItemRef]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    items: list[RawItemRef] = []
    seen_urls: set[str] = set()

    for link in soup.select("h3 a[href*='/actualites/']"):
        href = link.get("href", "")
        if not href or href.rstrip("/") == "/actualites":
            continue
        url = href if href.startswith("http") else f"{BASE_URL}{href}"
        if url in seen_urls:
            continue
        seen_urls.add(url)
        title = link.get_text(strip=True)
        published_at = _find_published_date(link)
        items.append(RawItemRef(url=url, title=title, published_at=published_at))
    return items


def _find_published_date(link_tag) -> datetime | None:
    """The 'Publié le ...' text sits near the link inside the same card, not
    inside the <a> itself -- walk up to the enclosing card and search its
    text. Handles both numeric (03/01/2026) and French long-form (4 janvier
    2026) dates, both seen on the real site."""
    card = link_tag.find_parent(["article", "div", "li"])
    if card is None:
        return None
    card_text = card.get_text()

    numeric = re.search(r"Publié le (\d{1,2})/(\d{1,2})/(\d{4})", card_text)
    if numeric:
        day, month, year = numeric.groups()
        return datetime(int(year), int(month), int(day))

    long_form = re.search(
        r"Publié le (\d{1,2}) (" + "|".join(_MONTHS_FR) + r") (\d{4})", card_text
    )
    if long_form:
        day, month_name, year = long_form.groups()
        return datetime(int(year), _MONTHS_FR[month_name], int(day))

    return None


def fetch_item(ref: RawItemRef) -> RawItem:
    response = fetch(ref.url)
    text = _extract_article_text(response.text)
    return RawItem(url=ref.url, title=ref.title, published_at=ref.published_at, text=text)


def _extract_article_text(html: str) -> str:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer"]):
        tag.decompose()
    main = soup.find("main") or soup.find("article") or soup
    return "\n".join(line.strip() for line in main.get_text("\n").splitlines() if line.strip())
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/cyber/test_anssi_connector.py -v`
Expected: `2 passed`

- [ ] **Step 6: Commit**

```bash
git add backend/app/cyber/connectors/anssi.py backend/tests/cyber/fixtures/anssi_listing.html backend/tests/cyber/fixtures/anssi_article.html backend/tests/cyber/test_anssi_connector.py
git commit -m "feat(cyber): add ANSSI connector (HTML scraping fallback, no RSS feed available)"
```

**Note for whoever runs this against the live site:** if ANSSI's markup has changed since this was written, only `_parse_listing`/`_find_published_date` need updating — re-fetch `https://www.cyber.gouv.fr/actualites` by hand, save it over `anssi_listing.html`-style fixture, and adjust the CSS selector in `_parse_listing`.

---

### Task 7: Sync pipeline (dedup, tagging, chunk, embed, store)

**Files:**
- Create: `backend/app/cyber/pipeline.py`
- Test: `backend/tests/cyber/test_pipeline.py`

**Interfaces:**
- Consumes: `Taxonomy`/`load_taxonomy` (Task 3), `RawItemRef`/`RawItem` (Task 4), connector modules (Tasks 5, 6), `app.ingestion.chunking._split_words`/`TARGET_WORDS`/`OVERLAP_WORDS`, `app.ingestion.embed.embed_documents`, `app.llm.factory.get_llm_provider`, `app.llm.base.LLMProvider`.
- Produces: `SyncStats(items_found, items_added, items_updated, items_skipped, errors)`, `async def sync_all(progress_cb=None) -> SyncStats`. Consumed by Task 10 (API layer).

- [ ] **Step 1: Write the failing test**

Create `backend/tests/cyber/test_pipeline.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/cyber/test_pipeline.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.cyber.pipeline'`

- [ ] **Step 3: Implement the pipeline**

Create `backend/app/cyber/pipeline.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/cyber/test_pipeline.py -v`
Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/app/cyber/pipeline.py backend/tests/cyber/test_pipeline.py
git commit -m "feat(cyber): add sync pipeline (dedup, LLM tagging, chunk, embed, store)"
```

---

### Task 8: Merge cyber content into the RAG retriever

**Files:**
- Modify: `backend/app/rag/retriever.py`
- Test: `backend/tests/cyber/test_retriever_merge.py`

**Interfaces:**
- Consumes: `cyber_items`/`cyber_chunks`/`cyber_chunk_embeddings` (Task 2), `app.ingestion.embed.embed_query`.
- Produces: `retrieve(query, top_k=10, subject_id=None) -> list[RetrievedChunk]` now also returns cyber-origin rows (mapped onto the existing field names so `rag/qa.py` and the frontend need no changes: `subject_name` = authority_source, `relative_path` = item title, `absolute_path` = item URL, `subject_id`/`year`/`semester`/`page_*`/`line_*` = `None`). When `subject_id` is provided, cyber rows are excluded (they have no `subject_id`, so they can never match a specific subject scope) -- this is exactly the "no cyber/course scope toggle needed" behavior from the spec.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/cyber/test_retriever_merge.py`:

```python
import numpy as np
import pytest

import app.rag.retriever as retriever_module
from app.config import get_settings
from app.db.connection import init_db, get_connection
from app.rag.retriever import retrieve


@pytest.fixture
def rag_db(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    get_settings.cache_clear()
    init_db()

    dim = get_settings().embedding_dim

    def fake_embed_query(text: str):
        return np.ones(dim, dtype=np.float32)

    # Chunk embeddings are seeded directly below (see _seed_course_chunk /
    # _seed_cyber_chunk) rather than via embed_documents(), since the test
    # only needs a fixed vector for both course and cyber chunks so the KNN
    # match is deterministic -- only the query-side embed_query() is patched.
    monkeypatch.setattr(retriever_module, "embed_query", fake_embed_query)
    yield
    get_settings.cache_clear()


def _seed_course_chunk(conn, text="Un chunk de cours."):
    import sqlite_vec

    conn.execute("INSERT INTO subjects (year, semester, name, root_path) VALUES ('4A', NULL, 'Réseaux', '/tmp')")
    subject_id = conn.execute("SELECT id FROM subjects WHERE name = 'Réseaux'").fetchone()["id"]
    conn.execute(
        """
        INSERT INTO source_files (subject_id, relative_path, absolute_path, file_type, content_hash, last_ingested_at)
        VALUES (?, 'cours.pdf', '/tmp/cours.pdf', 'pdf', 'h', '2026-01-01T00:00:00Z')
        """,
        (subject_id,),
    )
    source_file_id = conn.execute("SELECT id FROM source_files WHERE relative_path = 'cours.pdf'").fetchone()["id"]
    cur = conn.execute(
        "INSERT INTO chunks (source_file_id, content_type, text, chunk_index) VALUES (?, 'prose', ?, 0)",
        (source_file_id, text),
    )
    chunk_id = cur.lastrowid
    conn.execute(
        "INSERT INTO chunk_embeddings (chunk_id, embedding) VALUES (?, ?)",
        (chunk_id, sqlite_vec.serialize_float32([1.0] * get_settings().embedding_dim)),
    )
    conn.commit()
    return subject_id


def _seed_cyber_chunk(conn, text="Un chunk de veille cyber."):
    import sqlite_vec

    conn.execute(
        """
        INSERT INTO cyber_items
            (connector, url, title, fetched_at, content_hash, raw_text, summary,
             content_type, technical_domain, level, authority_source, tags_json,
             generation_model, last_synced_at)
        VALUES ('anssi', 'https://example.org/x', 'Titre cyber', '2026-01-01T00:00:00Z', 'h',
                'texte', 'resume', 'guide_bonnes_pratiques', 'reseau', 'fondamental',
                'ANSSI', '[]', 'llama3.1:8b', '2026-01-01T00:00:00Z')
        """
    )
    item_id = conn.execute("SELECT id FROM cyber_items WHERE url = 'https://example.org/x'").fetchone()["id"]
    cur = conn.execute(
        "INSERT INTO cyber_chunks (cyber_item_id, content_type, text, chunk_index) VALUES (?, 'prose', ?, 0)",
        (item_id, text),
    )
    chunk_id = cur.lastrowid
    conn.execute(
        "INSERT INTO cyber_chunk_embeddings (chunk_id, embedding) VALUES (?, ?)",
        (chunk_id, sqlite_vec.serialize_float32([1.0] * get_settings().embedding_dim)),
    )
    conn.commit()


def test_retrieve_merges_course_and_cyber_chunks(rag_db):
    with get_connection() as conn:
        _seed_course_chunk(conn)
        _seed_cyber_chunk(conn)

    results = retrieve("question", top_k=10)

    origins = {(r.subject_name, r.relative_path) for r in results}
    assert ("Réseaux", "cours.pdf") in origins
    assert ("ANSSI", "Titre cyber") in origins
    cyber_result = next(r for r in results if r.subject_name == "ANSSI")
    assert cyber_result.absolute_path == "https://example.org/x"
    assert cyber_result.subject_id is None


def test_retrieve_excludes_cyber_when_subject_id_scoped(rag_db):
    with get_connection() as conn:
        subject_id = _seed_course_chunk(conn)
        _seed_cyber_chunk(conn)

    results = retrieve("question", top_k=10, subject_id=subject_id)

    assert all(r.subject_id == subject_id for r in results)
    assert all(r.subject_name != "ANSSI" for r in results)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/cyber/test_retriever_merge.py -v`
Expected: FAIL (assertion errors -- cyber rows missing from results, since `retrieve()` doesn't query `cyber_chunk_embeddings` yet).

- [ ] **Step 3: Rewrite `retrieve()` to merge both vec tables**

Replace the full contents of `backend/app/rag/retriever.py` with:

```python
from dataclasses import dataclass

import sqlite_vec

from app.db.connection import get_connection
from app.ingestion.embed import embed_query


@dataclass
class RetrievedChunk:
    chunk_id: int
    text: str
    content_type: str
    distance: float
    subject_id: int | None
    subject_name: str
    year: str | None
    semester: str | None
    relative_path: str
    absolute_path: str
    page_start: int | None
    page_end: int | None
    line_start: int | None
    line_end: int | None


def _knn_course(conn, vector, fetch_k: int) -> list[RetrievedChunk]:
    knn_rows = conn.execute(
        """
        SELECT chunk_id, distance
        FROM chunk_embeddings
        WHERE embedding MATCH ? AND k = ?
        ORDER BY distance
        """,
        (sqlite_vec.serialize_float32(vector.tolist()), fetch_k),
    ).fetchall()
    if not knn_rows:
        return []

    distance_by_chunk_id = {row["chunk_id"]: row["distance"] for row in knn_rows}
    placeholders = ",".join("?" * len(knn_rows))
    chunk_rows = conn.execute(
        f"""
        SELECT c.id AS chunk_id, c.text, c.content_type, c.page_start, c.page_end, c.line_start, c.line_end,
               sf.relative_path, sf.absolute_path, sf.subject_id,
               s.name AS subject_name, s.year, s.semester
        FROM chunks c
        JOIN source_files sf ON sf.id = c.source_file_id
        JOIN subjects s ON s.id = sf.subject_id
        WHERE c.id IN ({placeholders})
        """,
        [row["chunk_id"] for row in knn_rows],
    ).fetchall()

    results: list[RetrievedChunk] = []
    for row in chunk_rows:
        results.append(
            RetrievedChunk(
                chunk_id=row["chunk_id"],
                text=row["text"],
                content_type=row["content_type"],
                distance=distance_by_chunk_id[row["chunk_id"]],
                subject_id=row["subject_id"],
                subject_name=row["subject_name"],
                year=row["year"],
                semester=row["semester"],
                relative_path=row["relative_path"],
                absolute_path=row["absolute_path"],
                page_start=row["page_start"],
                page_end=row["page_end"],
                line_start=row["line_start"],
                line_end=row["line_end"],
            )
        )
    return results


def _knn_cyber(conn, vector, fetch_k: int) -> list[RetrievedChunk]:
    knn_rows = conn.execute(
        """
        SELECT chunk_id, distance
        FROM cyber_chunk_embeddings
        WHERE embedding MATCH ? AND k = ?
        ORDER BY distance
        """,
        (sqlite_vec.serialize_float32(vector.tolist()), fetch_k),
    ).fetchall()
    if not knn_rows:
        return []

    distance_by_chunk_id = {row["chunk_id"]: row["distance"] for row in knn_rows}
    placeholders = ",".join("?" * len(knn_rows))
    chunk_rows = conn.execute(
        f"""
        SELECT cc.id AS chunk_id, cc.text, cc.content_type,
               ci.title AS cyber_title, ci.url AS cyber_url, ci.authority_source
        FROM cyber_chunks cc
        JOIN cyber_items ci ON ci.id = cc.cyber_item_id
        WHERE cc.id IN ({placeholders})
        """,
        [row["chunk_id"] for row in knn_rows],
    ).fetchall()

    results: list[RetrievedChunk] = []
    for row in chunk_rows:
        results.append(
            RetrievedChunk(
                chunk_id=row["chunk_id"],
                text=row["text"],
                content_type=row["content_type"],
                distance=distance_by_chunk_id[row["chunk_id"]],
                # No subject_id: this is what naturally excludes cyber rows
                # from any subject-scoped retrieve() call, with no separate
                # "cyber only / course only" toggle needed.
                subject_id=None,
                subject_name=row["authority_source"],
                year=None,
                semester=None,
                relative_path=row["cyber_title"],
                absolute_path=row["cyber_url"],
                page_start=None,
                page_end=None,
                line_start=None,
                line_end=None,
            )
        )
    return results


def retrieve(query: str, top_k: int = 10, subject_id: int | None = None) -> list[RetrievedChunk]:
    """KNN search over both sqlite-vec tables (course chunks + cyber-veille
    chunks), merged by distance, then joined back to relational metadata for
    citations. Overfetches and filters in Python when scoping to a subject
    rather than pushing the filter into vec0 -- simplest option at this
    corpus scale (thousands, not millions, of chunks)."""
    vector = embed_query(query)
    fetch_k = top_k * 5 if subject_id is not None else top_k

    with get_connection() as conn:
        course_rows = _knn_course(conn, vector, fetch_k)
        cyber_rows = [] if subject_id is not None else _knn_cyber(conn, vector, fetch_k)
        merged = sorted(course_rows + cyber_rows, key=lambda r: r.distance)

        results: list[RetrievedChunk] = []
        for chunk in merged:
            if subject_id is not None and chunk.subject_id != subject_id:
                continue
            results.append(chunk)
            if len(results) >= top_k:
                break
    return results
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/cyber/test_retriever_merge.py -v`
Expected: `2 passed`

- [ ] **Step 5: Run the full backend test suite to confirm nothing else broke**

Run: `cd backend && uv run pytest -v`
Expected: all tests pass (this is the first task that touches a file — `retriever.py` — consumed by existing, non-cyber code (`rag/qa.py`, `api/chat.py`, `api/subjects.py`), so this step is the regression check for those).

- [ ] **Step 6: Commit**

```bash
git add backend/app/rag/retriever.py backend/tests/cyber/test_retriever_merge.py
git commit -m "feat(cyber): merge cyber-veille chunks into the RAG retriever"
```

---

### Task 9: Obsidian export for cyber items

**Files:**
- Create: `backend/app/obsidian/cyber_export.py`
- Test: `backend/tests/cyber/test_cyber_export.py`

**Interfaces:**
- Consumes: `cyber_items` (Task 2), `app.config.get_settings().obsidian_vault_path`, `app.obsidian.export.slugify`.
- Produces: `export_cyber_to_obsidian() -> dict | None`. Consumed by Task 7 (`pipeline._sync_obsidian_export`).

- [ ] **Step 1: Write the failing test**

Create `backend/tests/cyber/test_cyber_export.py`:

```python
from pathlib import Path

import pytest

from app.config import get_settings
from app.db.connection import init_db, get_connection
from app.obsidian.cyber_export import export_cyber_to_obsidian


@pytest.fixture
def vault(tmp_path, monkeypatch):
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(vault_root))
    get_settings.cache_clear()
    init_db()
    yield vault_root
    get_settings.cache_clear()


def _seed_item(conn, title="Guide de test", referentiel=None, tags=None):
    import json

    conn.execute(
        """
        INSERT INTO cyber_items
            (connector, url, title, published_at, fetched_at, content_hash, raw_text, summary,
             content_type, technical_domain, level, authority_source, referentiel, tags_json,
             generation_model, last_synced_at)
        VALUES ('anssi', ?, ?, '2026-01-01T00:00:00Z', '2026-01-02T00:00:00Z', 'h', 'texte complet',
                'Résumé reformulé de test.', 'guide_bonnes_pratiques', 'reseau', 'fondamental',
                'ANSSI', ?, ?, 'llama3.1:8b', '2026-01-02T00:00:00Z')
        """,
        (f"https://example.org/{title}", title, referentiel, json.dumps(tags or [])),
    )
    conn.commit()


def test_export_writes_one_note_per_item(vault):
    with get_connection() as conn:
        _seed_item(conn, title="Guide de test")

    result = export_cyber_to_obsidian()

    assert result == {"items_exported": 1}
    export_root = vault / "Cours CPE" / "Culture Cyber"
    note_path = export_root / "Guide de test.md"
    assert note_path.exists()
    content = note_path.read_text(encoding="utf-8")
    assert "source: ANSSI" in content
    assert "https://example.org/Guide de test" in content
    assert "Résumé reformulé de test." in content


def test_export_writes_index(vault):
    with get_connection() as conn:
        _seed_item(conn, title="Guide A")
        _seed_item(conn, title="Guide B")

    export_cyber_to_obsidian()

    index_path = vault / "Cours CPE" / "Culture Cyber" / "_Index.md"
    assert index_path.exists()
    content = index_path.read_text(encoding="utf-8")
    assert "Guide A" in content
    assert "Guide B" in content


def test_export_returns_none_when_vault_not_configured(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.delenv("OBSIDIAN_VAULT_PATH", raising=False)
    get_settings.cache_clear()
    init_db()

    assert export_cyber_to_obsidian() is None
    get_settings.cache_clear()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/cyber/test_cyber_export.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.obsidian.cyber_export'`

- [ ] **Step 3: Implement the exporter**

Create `backend/app/obsidian/cyber_export.py`:

```python
"""Mirrors cyber-veille items (ANSSI/CERT-FR/...) into the user's Obsidian
vault as markdown notes, under "Cours CPE/Culture Cyber/" -- same vault
Study Copilot already writes course notes to (see obsidian/export.py).

Each item becomes its own note with YAML frontmatter (source, url, dates,
taxonomy tags) plus the LLM-reformulated summary and a short capped verbatim
excerpt -- never the full scraped text, to avoid reproducing protected
content wholesale. Regenerated (idempotent overwrite) after every
POST /cyber/sync; hand edits here will be lost on the next sync."""

import json
from pathlib import Path

from app.config import get_settings
from app.db.connection import get_connection
from app.obsidian.export import slugify

EXPORT_FOLDER_NAME = Path("Cours CPE") / "Culture Cyber"
EXCERPT_CHAR_CAP = 400


def _export_root() -> Path | None:
    settings = get_settings()
    if not settings.obsidian_vault_path:
        return None
    return settings.obsidian_vault_path / EXPORT_FOLDER_NAME


def _write_item_note(export_root: Path, item: dict) -> Path:
    export_root.mkdir(parents=True, exist_ok=True)
    path = export_root / f"{slugify(item['title'])}.md"

    tags = json.loads(item["tags_json"])
    frontmatter = [
        "---",
        f"source: {item['authority_source']}",
        f"connector: {item['connector']}",
        f"url: {item['url']}",
        f"published_at: {item['published_at'] or ''}",
        f"fetched_at: {item['fetched_at']}",
        f"content_type: {item['content_type']}",
        f"technical_domain: {item['technical_domain']}",
        f"level: {item['level']}",
        f"referentiel: {item['referentiel'] or ''}",
        f"tags: [{', '.join(tags)}]",
        "---",
        "",
    ]

    excerpt = item["raw_text"][:EXCERPT_CHAR_CAP].strip()
    body = [
        f"# {item['title']}",
        "",
        item["summary"],
        "",
        "## Extrait",
        "",
        f"> {excerpt}{'…' if len(item['raw_text']) > EXCERPT_CHAR_CAP else ''}",
        "",
        f"[Source originale]({item['url']}) -- récupéré le {item['fetched_at']}",
        "",
    ]

    path.write_text("\n".join(frontmatter + body), encoding="utf-8")
    return path


def _write_index(export_root: Path, items: list[dict]) -> None:
    lines = [
        "# Culture Cyber — Index", "",
        "Généré automatiquement par Study Copilot après chaque `POST /cyber/sync`. "
        "Ne pas éditer à la main.",
        "",
    ]
    by_domain: dict[str, list[dict]] = {}
    for item in items:
        by_domain.setdefault(item["technical_domain"], []).append(item)

    for domain in sorted(by_domain):
        lines.append(f"## {domain}")
        for item in sorted(by_domain[domain], key=lambda i: i["title"]):
            lines.append(f"- [[{slugify(item['title'])}|{item['title']}]] ({item['authority_source']})")
        lines.append("")

    (export_root / "_Index.md").write_text("\n".join(lines), encoding="utf-8")


def export_cyber_to_obsidian() -> dict | None:
    """No-op (returns None) if OBSIDIAN_VAULT_PATH isn't configured."""
    export_root = _export_root()
    if export_root is None:
        return None

    with get_connection() as conn:
        items = [dict(row) for row in conn.execute("SELECT * FROM cyber_items").fetchall()]

    for item in items:
        _write_item_note(export_root, item)
    _write_index(export_root, items)

    return {"items_exported": len(items)}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/cyber/test_cyber_export.py -v`
Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/app/obsidian/cyber_export.py backend/tests/cyber/test_cyber_export.py
git commit -m "feat(cyber): export cyber-veille items to Obsidian under Cours CPE/Culture Cyber/"
```

---

### Task 10: API endpoints and wiring

**Files:**
- Create: `backend/app/api/cyber.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/cyber/test_cyber_api.py`

**Interfaces:**
- Consumes: `pipeline.sync_all` (Task 7).
- Produces: `POST /cyber/sync`, `GET /cyber/status`. Consumed by Task 11 (frontend).

- [ ] **Step 1: Write the failing test**

Create `backend/tests/cyber/test_cyber_api.py`:

```python
import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.db.connection import init_db


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    get_settings.cache_clear()
    init_db()

    # Import main only after DB_PATH is patched, and only inside the test, so
    # module-level state (the in-memory _state dict in api/cyber.py) starts
    # fresh per test.
    import importlib

    import app.api.cyber as cyber_api

    importlib.reload(cyber_api)

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client, cyber_api
    get_settings.cache_clear()


def test_status_starts_idle(client):
    test_client, _ = client
    response = test_client.get("/cyber/status")
    assert response.status_code == 200
    assert response.json()["status"] == "idle"


def test_sync_endpoint_starts_and_status_reflects_it(client, monkeypatch):
    test_client, cyber_api = client

    async def fake_sync_all(progress_cb=None):
        from app.cyber.pipeline import SyncStats

        return SyncStats(items_found=0, items_added=0, items_updated=0, items_skipped=0, errors=0)

    monkeypatch.setattr(cyber_api, "sync_all", fake_sync_all)

    response = test_client.post("/cyber/sync")
    assert response.status_code == 200
    assert response.json()["status"] == "started"

    status = test_client.get("/cyber/status").json()
    assert status["status"] in ("running", "completed")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/cyber/test_cyber_api.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.api.cyber'`

- [ ] **Step 3: Implement the API router**

Create `backend/app/api/cyber.py`:

```python
import asyncio
import threading

from fastapi import APIRouter, BackgroundTasks

from app.cyber.pipeline import sync_all

router = APIRouter(prefix="/cyber", tags=["cyber"])

_lock = threading.Lock()
_state = {
    "status": "idle",  # idle | running | completed | failed
    "current": 0,
    "total": 0,
    "current_item": None,
    "stats": None,
    "error": None,
}


def _try_claim() -> bool:
    """Same atomic check-and-set pattern as api/ingest.py::_try_claim, so a
    double-click on 'Sync' can't start two overlapping syncs."""
    with _lock:
        if _state["status"] == "running":
            return False
        _state.update(status="running", current=0, total=0, current_item=None, stats=None, error=None)
        return True


def _run() -> None:
    def progress_cb(current: int, total: int, title: str) -> None:
        with _lock:
            _state.update(current=current, total=total, current_item=title)

    try:
        stats = asyncio.run(sync_all(progress_cb=progress_cb))
        with _lock:
            _state.update(status="completed", stats=stats.__dict__)
    except Exception as exc:  # noqa: BLE001 - surfaced to the UI via /status
        with _lock:
            _state.update(status="failed", error=str(exc))


@router.post("/sync")
def start_sync(background_tasks: BackgroundTasks):
    if not _try_claim():
        return {"status": "already_running"}
    background_tasks.add_task(_run)
    return {"status": "started"}


@router.get("/status")
def get_status():
    with _lock:
        return dict(_state)


@router.get("/items")
def list_items():
    from app.db.connection import get_connection

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, connector, url, title, published_at, fetched_at, summary,
                   content_type, technical_domain, level, authority_source, referentiel, tags_json
            FROM cyber_items
            ORDER BY fetched_at DESC
            """
        ).fetchall()
        return [dict(row) for row in rows]
```

- [ ] **Step 4: Wire the router into `main.py`**

In `backend/app/main.py`, add the import and registration:

```python
from app.api import chat, cyber, game, graph, ingest, subjects
```

(replacing the existing `from app.api import chat, game, graph, ingest, subjects` line)

```python
app.include_router(cyber.router)
```

(added after the existing `app.include_router(game.router)` line)

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/cyber/test_cyber_api.py -v`
Expected: `2 passed`

- [ ] **Step 6: Run the full backend test suite**

Run: `cd backend && uv run pytest -v`
Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/cyber.py backend/app/main.py backend/tests/cyber/test_cyber_api.py
git commit -m "feat(cyber): add POST /cyber/sync, GET /cyber/status, GET /cyber/items endpoints"
```

---

### Task 11: Frontend "Veille Cyber" tab

**Files:**
- Modify: `frontend/src/api/client.ts`
- Create: `frontend/src/pages/CyberWatch.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `GET /cyber/status`, `POST /cyber/sync`, `GET /cyber/items` (Task 10).
- Produces: a new `'cyber'` tab in `App.tsx`'s nav.

- [ ] **Step 1: Add API client functions and types**

In `frontend/src/api/client.ts`, add these types near `IngestStatus`:

```typescript
export interface CyberSyncStatus {
  status: 'idle' | 'running' | 'completed' | 'failed'
  current: number
  total: number
  current_item: string | null
  stats: Record<string, number> | null
  error: string | null
}

export interface CyberItem {
  id: number
  connector: string
  url: string
  title: string
  published_at: string | null
  fetched_at: string
  summary: string
  content_type: string
  technical_domain: string
  level: string
  authority_source: string
  referentiel: string | null
  tags_json: string
}
```

And these functions near `startIngestion`/`fetchIngestStatus`:

```typescript
export async function startCyberSync(): Promise<void> {
  await fetch(`${BASE}/cyber/sync`, { method: 'POST' })
}

export async function fetchCyberStatus(): Promise<CyberSyncStatus> {
  const res = await fetch(`${BASE}/cyber/status`)
  if (!res.ok) throw new Error('Failed to fetch cyber sync status')
  return res.json()
}

export async function fetchCyberItems(): Promise<CyberItem[]> {
  const res = await fetch(`${BASE}/cyber/items`)
  if (!res.ok) throw new Error('Failed to fetch cyber items')
  return res.json()
}
```

- [ ] **Step 2: Create the page, modeled on `Subjects.tsx`**

Create `frontend/src/pages/CyberWatch.tsx`:

```tsx
import { useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { fetchCyberItems, fetchCyberStatus, startCyberSync, type CyberItem } from '../api/client'

export default function CyberWatch() {
  const queryClient = useQueryClient()
  const { data: items } = useQuery({ queryKey: ['cyber-items'], queryFn: fetchCyberItems })
  const [polling, setPolling] = useState(false)
  const { data: status } = useQuery({
    queryKey: ['cyber-status'],
    queryFn: fetchCyberStatus,
    refetchInterval: polling ? 1000 : false,
  })

  useEffect(() => {
    if (status?.status === 'running') setPolling(true)
    else if (polling) {
      setPolling(false)
      queryClient.invalidateQueries({ queryKey: ['cyber-items'] })
    }
  }, [status, polling, queryClient])

  async function handleSync() {
    await startCyberSync()
    setPolling(true)
  }

  const running = status?.status === 'running'
  const progressPct = status && status.total > 0 ? Math.round((status.current / status.total) * 100) : 0

  return (
    <div className="h-full overflow-y-auto grid-paper">
      <header className="bg-panel px-8 py-4 flex items-center justify-between border-b border-ink/8">
        <div>
          <p className="font-data text-[10px] tracking-wider text-ink-soft uppercase">Base de connaissances</p>
          <h1 className="font-display text-xl font-semibold text-ink">Veille Cyber</h1>
          <p className="font-data text-xs text-ink-soft mt-0.5">{items?.length ?? 0} fiches capitalisées</p>
        </div>
        <button
          className="bg-amber hover:bg-amber/90 text-paper px-4 py-2.5 rounded text-sm font-medium disabled:opacity-50 transition-colors flex items-center gap-2 whitespace-nowrap shrink-0 font-display"
          onClick={handleSync}
          disabled={running}
        >
          {running && (
            <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 0 1 8-8V0C5.373 0 0 5.373 0 12h4Z" />
            </svg>
          )}
          {running ? 'Synchronisation...' : 'Sync now'}
        </button>
      </header>

      <div className="max-w-4xl mx-auto px-8 py-6 flex flex-col gap-3">
        {running && (
          <div className="bg-panel border border-ink/10 rounded px-4 py-3">
            <div className="flex justify-between font-data text-xs text-ink-soft mb-1.5">
              <span className="truncate max-w-md">{status?.current_item}</span>
              <span>{status?.current} / {status?.total}</span>
            </div>
            <div className="h-1 bg-ink/8 rounded-full overflow-hidden">
              <div className="h-full bg-amber rounded-full transition-all duration-300" style={{ width: `${progressPct}%` }} />
            </div>
          </div>
        )}

        {status?.status === 'failed' && (
          <div className="bg-alert-soft border border-alert/25 text-alert text-sm rounded px-4 py-3">
            Erreur de synchronisation : {status.error}
          </div>
        )}

        {items?.length === 0 && !running && (
          <div className="flex flex-col items-center justify-center text-center py-20 gap-3">
            <p className="text-ink-soft text-sm">Aucune fiche pour l'instant.</p>
            <button className="text-amber text-sm font-medium hover:underline" onClick={handleSync}>
              Lancer la première synchronisation
            </button>
          </div>
        )}

        {items?.map((item) => <ItemCard key={item.id} item={item} />)}
      </div>
    </div>
  )
}

function ItemCard({ item }: { item: CyberItem }) {
  const tags: string[] = JSON.parse(item.tags_json || '[]')
  return (
    <a
      href={item.url}
      target="_blank"
      rel="noreferrer"
      className="corner-marks bg-panel border border-ink/10 rounded px-4 py-3 flex flex-col gap-1.5 hover:border-amber/50 hover:shadow-sm transition-all"
    >
      <div className="flex items-center gap-2">
        <span className="font-data text-[11px] text-ink-soft bg-paper border border-ink/10 rounded px-2 py-0.5">
          {item.authority_source}
        </span>
        <p className="font-display font-medium text-ink text-sm">{item.title}</p>
      </div>
      <p className="text-xs text-ink-soft">{item.summary}</p>
      <div className="flex gap-1.5 flex-wrap">
        <Badge>{item.content_type}</Badge>
        <Badge>{item.technical_domain}</Badge>
        <Badge>{item.level}</Badge>
        {tags.map((tag) => <Badge key={tag}>{tag}</Badge>)}
      </div>
    </a>
  )
}

function Badge({ children }: { children: React.ReactNode }) {
  return (
    <span className="font-data text-[10px] text-ink-soft bg-paper border border-ink/10 rounded px-1.5 py-0.5">
      {children}
    </span>
  )
}
```

- [ ] **Step 3: Add the tab to `App.tsx`**

In `frontend/src/App.tsx`:

Add the import:

```typescript
import CyberWatch from './pages/CyberWatch'
```

Change the `Tab` type:

```typescript
type Tab = 'chat' | 'subjects' | 'cyber' | 'graph' | 'game'
```

Add a nav entry to `NAV_ITEMS` (after the `'subjects'` entry):

```typescript
  {
    id: 'cyber',
    label: 'Veille Cyber',
    icon: (
      <svg viewBox="0 0 24 24" fill="none" strokeWidth="1.6" stroke="currentColor" className="w-4 h-4">
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 2 4 6v6c0 5 3.4 8.7 8 10 4.6-1.3 8-5 8-10V6l-8-4Z" />
      </svg>
    ),
  },
```

Add the route in `<main>`:

```tsx
        {tab === 'cyber' && <CyberWatch />}
```

(added after `{tab === 'subjects' && <Subjects />}`)

- [ ] **Step 4: Verify the frontend builds and typechecks**

Run: `cd frontend && npm run build`
Expected: exits 0, no TypeScript errors.

- [ ] **Step 5: Manual smoke test**

Run: `cd backend && uv run uvicorn app.main:app --reload --port 8000` (in one terminal) and `cd frontend && npm run dev` (in another). Open `http://localhost:5173`, click the new "Veille Cyber" tab, click "Sync now", and confirm the progress bar advances and items appear once the sync completes (requires `OBSIDIAN_VAULT_PATH`/`ANSSI`/`CERT-FR` network access to be meaningful end-to-end; with no network it should still show a clean "failed" state with the underlying error rather than crashing the UI).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/client.ts frontend/src/pages/CyberWatch.tsx frontend/src/App.tsx
git commit -m "feat(cyber): add Veille Cyber tab to the frontend"
```

---

## Post-plan: manual verification checklist

Once all tasks are merged, do one real end-to-end run (not covered by automated tests, since those never hit the network):

1. Set `OBSIDIAN_VAULT_PATH` in `backend/.env` if not already set.
2. Start the backend and frontend (see Task 11, Step 5).
3. Click "Sync now" on the Veille Cyber tab.
4. Confirm `GET /cyber/status` reaches `completed` with `items_added > 0`.
5. Confirm new `.md` files appear under `<vault>/Cours CPE/Culture Cyber/`.
6. Ask a cybersecurity-related question in the Chat tab and confirm a citation with `subject_name` set to `ANSSI` or `CERT-FR` shows up.
7. Re-click "Sync now" and confirm `items_skipped` matches `items_added` from the previous run (hash-based dedup working).
