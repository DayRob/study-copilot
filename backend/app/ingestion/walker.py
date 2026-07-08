import re
from dataclasses import dataclass
from pathlib import Path

import pathspec

# Directories that are never course content, regardless of what's inside them.
NAME_DENYLIST = {
    "node_modules", ".git", ".hg", ".svn", ".next", ".nuxt", "dist", "build",
    "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache", "target",
    ".gradle", ".idea", ".vscode", ".terraform", "coverage", ".tox",
    "site-packages", "egg-info",
}

# Extensions that are never worth extracting text from.
BINARY_DENYLIST = {
    ".pyc", ".pyd", ".class", ".exe", ".dll", ".so", ".o", ".a", ".lib",
    ".zip", ".tar", ".gz", ".7z", ".rar", ".jar", ".war",
    ".mp4", ".mp3", ".wav", ".mov", ".avi",
    ".vmdk", ".vmwarevm", ".iso", ".ova",
}

# Known extensions we know how to extract, mapped to a coarse file_type.
KNOWN_EXTENSIONS: dict[str, str] = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".doc": "docx",
    **{ext: "code" for ext in (
        ".py", ".java", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
        ".tf", ".tfvars", ".yml", ".yaml", ".sql", ".sh", ".ps1",
        ".c", ".h", ".hpp", ".cpp", ".cs", ".go", ".rb", ".php",
    )},
    **{ext: "text" for ext in (".md", ".txt", ".csv", ".json", ".xml")},
}

SEMESTER_PATTERN = re.compile(r"^\d\s*(er|ère|eme|ème)?\s*semestre", re.IGNORECASE)

# Minified/bundled JS (or other huge single-blob code files) can live in
# folders with no obviously excludable name (e.g. 'webui/assets') -- a size
# cutoff catches these regardless of where they sit. This is now a secondary
# safety net (chunking.py's char-cap + minified-code heuristic already bound
# per-chunk size and skip pathological tree-sitter parses), so it just needs
# to stop truly enormous files from wasting embedding time, not prevent hangs.
# "code" keeps a tight ceiling since that's where bundled/minified JS hides;
# "text" (.md/.txt/.csv/.json/.xml) gets a much higher one since these are
# human-authored prose/data -- e.g. a large personal Markdown notes file --
# and were never the source of the original hang.
MAX_CODE_BYTES = 400_000
MAX_TEXT_BYTES = 5_000_000
MAX_DOCUMENT_BYTES = 50_000_000


def _is_venv_dir(path: Path) -> bool:
    """Structural venv detection: name alone is unreliable (e.g. a folder
    named 'art' turned out to be a Python venv in the real corpus)."""
    if (path / "pyvenv.cfg").exists():
        return True
    if (path / "Lib" / "site-packages").exists():
        return True
    if list(path.glob("lib/python*/site-packages")):
        return True
    if (path / "Scripts" / "activate").exists() or (path / "bin" / "activate").exists():
        return True
    return False


def _load_ingestignore(root: Path) -> pathspec.PathSpec | None:
    ignore_file = root / ".ingestignore"
    if not ignore_file.exists():
        return None
    lines = ignore_file.read_text(encoding="utf-8").splitlines()
    return pathspec.PathSpec.from_lines("gitwildmatch", lines)


@dataclass
class DiscoveredFile:
    absolute_path: Path
    relative_path: Path  # relative to the course root (e.g. 4A or 5A dir's parent)
    subject_root: Path   # absolute path of the subject's own folder
    year: str
    semester: str | None
    subject: str
    file_type: str


def _infer_metadata(root_name: str, rel_parts: tuple[str, ...]) -> tuple[str, str | None, str] | None:
    """rel_parts is the path relative to the root, split into segments,
    NOT including the filename. Returns (year, semester, subject) or None
    if there's no subject-level folder yet (file sits directly under the year root)."""
    if not rel_parts:
        return None
    year = root_name
    idx = 0
    semester = None
    if SEMESTER_PATTERN.match(rel_parts[idx]):
        semester = rel_parts[idx]
        idx += 1
    if idx >= len(rel_parts):
        return None
    subject = rel_parts[idx]
    return year, semester, subject


def discover_files(course_roots: list[Path]) -> list[DiscoveredFile]:
    """Walk each course root, pruning excluded directories, and return the
    list of files worth ingesting with year/semester/subject metadata."""
    discovered: list[DiscoveredFile] = []

    for root in course_roots:
        root = root.resolve()
        if not root.exists():
            continue
        ignore_spec = _load_ingestignore(root)
        root_name = root.name

        stack = [root]
        while stack:
            current = stack.pop()
            try:
                entries = list(current.iterdir())
            except (PermissionError, OSError):
                continue

            for entry in entries:
                rel = entry.relative_to(root)
                if ignore_spec and ignore_spec.match_file(str(rel)):
                    continue

                if entry.is_dir():
                    if entry.name in NAME_DENYLIST:
                        continue
                    if entry.name.endswith((".egg-info", ".dist-info")):
                        continue
                    if _is_venv_dir(entry):
                        continue
                    stack.append(entry)
                    continue

                if entry.suffix.lower() in BINARY_DENYLIST:
                    continue
                file_type = KNOWN_EXTENSIONS.get(entry.suffix.lower())
                if file_type is None:
                    continue

                try:
                    size = entry.stat().st_size
                except OSError:
                    continue
                if file_type in ("pdf", "docx"):
                    max_size = MAX_DOCUMENT_BYTES
                elif file_type == "text":
                    max_size = MAX_TEXT_BYTES
                else:
                    max_size = MAX_CODE_BYTES
                if size > max_size:
                    continue

                rel_dir_parts = rel.parent.parts
                meta = _infer_metadata(root_name, rel_dir_parts)
                if meta is None:
                    continue
                year, semester, subject = meta
                subject_root = root.joinpath(*rel_dir_parts[: (2 if semester else 1)])

                discovered.append(
                    DiscoveredFile(
                        absolute_path=entry,
                        relative_path=rel,
                        subject_root=subject_root,
                        year=year,
                        semester=semester,
                        subject=subject,
                        file_type=file_type,
                    )
                )

    return discovered
