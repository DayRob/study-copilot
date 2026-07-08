from pathlib import Path

LANGUAGE_BY_EXTENSION = {
    ".py": "python", ".java": "java", ".ts": "typescript", ".tsx": "tsx",
    ".js": "javascript", ".jsx": "jsx", ".mjs": "javascript", ".cjs": "javascript",
    ".tf": "terraform", ".tfvars": "terraform", ".yml": "yaml", ".yaml": "yaml",
    ".sql": "sql", ".sh": "bash", ".ps1": "powershell",
    ".c": "c", ".h": "c", ".hpp": "cpp", ".cpp": "cpp", ".cs": "csharp",
    ".go": "go", ".rb": "ruby", ".php": "php",
}


def extract_code(path: Path) -> tuple[str, str]:
    """Read a source file as text, tolerating non-UTF-8 encodings from
    older TPs. Returns (text, language)."""
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        from charset_normalizer import from_bytes

        best = from_bytes(raw).best()
        text = str(best) if best else raw.decode("utf-8", errors="replace")

    language = LANGUAGE_BY_EXTENSION.get(path.suffix.lower(), "text")
    return text, language
