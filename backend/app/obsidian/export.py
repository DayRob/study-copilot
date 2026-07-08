"""Mirrors Study Copilot's synthesized knowledge (subject overviews) into the
user's Obsidian vault as markdown notes, so it's browsable there without
opening the app. Runs automatically after ingestion and after each overview
generation (see pipeline.py / api/subjects.py) -- no manual re-export step.

Each key concept becomes its own note under _Concepts/, and subject notes
link to it with [[wikilinks]]: this is what gives Obsidian's native graph
view an actual knowledge graph (shared concepts across subjects become
visible connections), matching the in-app knowledge graph (api/graph.py).

This folder is a generated mirror -- hand edits here will be overwritten on
the next export. Personal notes belong in the separate "Mes Notes" folder,
which is an ingestion *source* instead (see ingestion/watcher.py)."""

import json
import re
from collections import defaultdict
from pathlib import Path

from app.config import get_settings
from app.db.connection import get_connection

EXPORT_FOLDER_NAME = "Cours CPE"
CONCEPTS_FOLDER_NAME = "_Concepts"


def slugify(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', "-", name).strip()


def _export_root() -> Path | None:
    settings = get_settings()
    if not settings.obsidian_vault_path:
        return None
    return settings.obsidian_vault_path / EXPORT_FOLDER_NAME


def _subject_folder(export_root: Path, year: str, semester: str | None) -> Path:
    parts = [export_root, year]
    if semester:
        parts.append(slugify(semester))
    return Path(*parts)


def _concept_link(export_root: Path, vault_root: Path, concept: str) -> str:
    rel = (export_root / CONCEPTS_FOLDER_NAME / slugify(concept)).relative_to(vault_root).as_posix()
    return f"[[{rel}|{concept}]]"


def _write_subject_note(
    export_root: Path, vault_root: Path, subject: dict, overview: dict | None, file_count: int, chunk_count: int
) -> Path:
    folder = _subject_folder(export_root, subject["year"], subject["semester"])
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{slugify(subject['name'])}.md"

    lines = [f"# {subject['name']}", ""]
    lines.append(
        f"*{subject['year']}{' · ' + subject['semester'] if subject['semester'] else ''} "
        f"· {file_count} fichiers · {chunk_count} passages indexés*"
    )
    lines.append("")

    if overview:
        lines.append("## Résumé")
        lines.append(overview["summary"])
        lines.append("")

        key_topics = overview.get("key_topics", [])
        if key_topics:
            lines.append("## Notions clés")
            for topic in key_topics:
                lines.append(f"### {_concept_link(export_root, vault_root, topic['concept'])}")
                lines.append(topic["explanation"])
                lines.append("")

        examples = overview.get("examples", [])
        if examples:
            lines.append("## Extraits du cours")
            for ex in examples:
                loc = ""
                if ex.get("page_start"):
                    loc = f"page {ex['page_start']}"
                elif ex.get("line_start"):
                    loc = f"lignes {ex['line_start']}-{ex['line_end']}"
                source = ex["relative_path"].replace("\\", "/")
                lines.append(f"> {ex['text'][:500].strip()}")
                lines.append(f">\n> — *{source}{', ' + loc if loc else ''}*")
                lines.append("")

        resources = overview.get("resources", [])
        if resources:
            lines.append("## Ressources")
            for r in resources:
                lines.append(f"- [{r['label']}]({r['url']})")
            lines.append("")
    else:
        lines.append("*Fiche pas encore générée par l'IA — liste brute des fichiers ingérés.*")
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _write_concept_notes(export_root: Path, vault_root: Path, concept_index: dict[str, list[dict]]) -> None:
    concepts_root = export_root / CONCEPTS_FOLDER_NAME
    concepts_root.mkdir(parents=True, exist_ok=True)
    for concept, mentions in concept_index.items():
        path = concepts_root / f"{slugify(concept)}.md"
        lines = [f"# {concept}", "", f"*Abordé dans {len(mentions)} sujet(s).*", ""]
        for m in mentions:
            rel = m["note_path"].relative_to(vault_root).as_posix()
            lines.append(f"## [[{rel[:-3]}|{m['subject_name']}]]")
            lines.append(m["explanation"])
            lines.append("")
        path.write_text("\n".join(lines), encoding="utf-8")


def _write_index(export_root: Path, vault_root: Path, entries: list[dict]) -> None:
    lines = [
        "# Cours CPE — Index", "",
        "Généré automatiquement par Study Copilot après chaque synchronisation. Ne pas éditer à la main "
        "(voir le dossier \"Mes Notes\" pour tes propres notes).",
        "",
    ]
    by_year: dict[str, dict[str, list[dict]]] = {}
    for e in entries:
        by_year.setdefault(e["year"], {}).setdefault(e["semester"] or "-", []).append(e)

    for year in sorted(by_year):
        lines.append(f"## {year}")
        for semester in sorted(by_year[year]):
            if semester != "-":
                lines.append(f"### {semester}")
            for e in sorted(by_year[year][semester], key=lambda x: x["name"]):
                rel = e["note_path"].relative_to(vault_root).as_posix()
                lines.append(f"- [[{rel[:-3]}|{e['name']}]]")
        lines.append("")

    (export_root / "_Index.md").write_text("\n".join(lines), encoding="utf-8")


def export_to_obsidian() -> dict | None:
    """No-op (returns None) if OBSIDIAN_VAULT_PATH isn't configured."""
    export_root = _export_root()
    if export_root is None:
        return None
    vault_root = get_settings().obsidian_vault_path

    with get_connection() as conn:
        subjects = conn.execute(
            """
            SELECT s.id, s.year, s.semester, s.name,
                   COUNT(DISTINCT sf.id) AS file_count,
                   COUNT(DISTINCT c.id) AS chunk_count
            FROM subjects s
            LEFT JOIN source_files sf ON sf.subject_id = s.id
            LEFT JOIN chunks c ON c.source_file_id = sf.id
            GROUP BY s.id
            """
        ).fetchall()
        overviews = {
            row["subject_id"]: {
                "summary": row["summary"],
                "key_topics": json.loads(row["key_topics"]),
                "examples": json.loads(row["examples"]),
                "resources": json.loads(row["resources"]),
            }
            for row in conn.execute("SELECT * FROM subject_overviews").fetchall()
        }

    entries = []
    concept_index: dict[str, list[dict]] = defaultdict(list)

    for s in subjects:
        overview = overviews.get(s["id"])
        note_path = _write_subject_note(export_root, vault_root, dict(s), overview, s["file_count"], s["chunk_count"])
        entries.append({"year": s["year"], "semester": s["semester"], "name": s["name"], "note_path": note_path})
        if overview:
            for topic in overview.get("key_topics", []):
                concept_index[topic["concept"]].append(
                    {"subject_name": s["name"], "note_path": note_path, "explanation": topic["explanation"]}
                )

    _write_concept_notes(export_root, vault_root, concept_index)
    _write_index(export_root, vault_root, entries)

    return {"subjects_exported": len(subjects), "concepts_exported": len(concept_index)}
