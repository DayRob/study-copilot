from dataclasses import dataclass
from pathlib import Path


@dataclass
class DocxSection:
    heading: str | None
    text: str


def extract_docx(path: Path) -> list[DocxSection]:
    """Split a docx into sections by heading paragraphs, preserving structure
    for chunking. Tables are appended as pipe-separated rows within the
    current section."""
    import docx

    document = docx.Document(str(path))
    sections: list[DocxSection] = []
    current_heading: str | None = None
    current_lines: list[str] = []

    def flush():
        text = "\n".join(current_lines).strip()
        if text:
            sections.append(DocxSection(heading=current_heading, text=text))

    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        if not text:
            continue
        is_heading = paragraph.style.name.lower().startswith("heading") or paragraph.style.name.lower() == "title"
        if is_heading:
            flush()
            current_heading = text
            current_lines = []
        else:
            current_lines.append(text)
    flush()

    for table in document.tables:
        rows = []
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells]
            if any(cells):
                rows.append(" | ".join(cells))
        if rows:
            sections.append(DocxSection(heading=current_heading, text="\n".join(rows)))

    return sections
