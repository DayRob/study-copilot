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

import yaml

from app.config import get_settings
from app.db.connection import get_connection
from app.obsidian.export import slugify

EXPORT_FOLDER_NAME = Path("Cours CPE") / "Culture Cyber"
EXCERPT_CHAR_CAP = 400


def _frontmatter_block(item: dict, tags: list[str]) -> str:
    """Build YAML frontmatter block with proper escaping for special characters.

    Uses yaml.safe_dump to ensure values containing colons, quotes, or other
    special characters are properly escaped.
    """
    data = {
        "source": item["authority_source"],
        "connector": item["connector"],
        "url": item["url"],
        "published_at": item["published_at"] or "",
        "fetched_at": item["fetched_at"],
        "content_type": item["content_type"],
        "technical_domain": item["technical_domain"],
        "level": item["level"],
        "referentiel": item["referentiel"] or "",
        "tags": tags,
    }
    return "---\n" + yaml.safe_dump(data, allow_unicode=True, sort_keys=False) + "---\n"


def _export_root() -> Path | None:
    settings = get_settings()
    if settings.obsidian_vault_path is None:
        return None
    return settings.obsidian_vault_path / EXPORT_FOLDER_NAME


def _write_item_note(export_root: Path, item: dict) -> Path:
    export_root.mkdir(parents=True, exist_ok=True)
    path = export_root / f"{slugify(item['title'])}.md"

    tags = json.loads(item["tags_json"])
    frontmatter = _frontmatter_block(item, tags)

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

    path.write_text(frontmatter + "\n".join(body), encoding="utf-8")
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
