from dataclasses import dataclass
from pathlib import Path


@dataclass
class PageBlock:
    page_number: int  # 1-indexed
    text: str


def extract_pdf(path: Path) -> list[PageBlock]:
    """Extract text per page, preserving page numbers for citation.
    pymupdf4llm gives markdown-ish output that keeps headings/structure;
    falls back to pdfplumber (plain text) if it fails on an unusual layout."""
    try:
        return _extract_with_pymupdf4llm(path)
    except Exception:
        return _extract_with_pdfplumber(path)


def _extract_with_pymupdf4llm(path: Path) -> list[PageBlock]:
    import pymupdf4llm

    pages = pymupdf4llm.to_markdown(str(path), page_chunks=True)
    blocks = []
    for page in pages:
        text = (page.get("text") or "").strip()
        if not text:
            continue
        page_number = page.get("metadata", {}).get("page", len(blocks) + 1)
        blocks.append(PageBlock(page_number=page_number, text=text))
    if not blocks:
        raise ValueError("pymupdf4llm produced no text")
    return blocks


def _extract_with_pdfplumber(path: Path) -> list[PageBlock]:
    import pdfplumber

    blocks = []
    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            text = (page.extract_text() or "").strip()
            if text:
                blocks.append(PageBlock(page_number=i, text=text))
    return blocks
