from dataclasses import dataclass, replace

from app.ingestion.extractors.docx import DocxSection
from app.ingestion.extractors.pdf import PageBlock

TARGET_WORDS = 450
OVERLAP_WORDS = 60
CODE_WINDOW_LINES = 80
CODE_WINDOW_OVERLAP = 10
HARD_CHAR_CAP = 4000

# Node types across common tree-sitter grammars that represent a
# self-contained, chunk-worthy unit of code.
CHUNKABLE_NODE_TYPES = {
    "function_definition", "function_declaration", "method_declaration",
    "class_definition", "class_declaration", "interface_declaration",
    "impl_item", "struct_item", "enum_item",
}


@dataclass
class Chunk:
    text: str
    content_type: str  # 'prose' | 'code'
    page_start: int | None = None
    page_end: int | None = None
    line_start: int | None = None
    line_end: int | None = None
    language: str | None = None


def _split_words(text: str, target: int, overlap: int) -> list[str]:
    raw_paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not raw_paragraphs:
        return []

    # Hard-split any oversized "paragraph" (e.g. a file with no blank lines,
    # like a raw log dump) so it can't slip through as one giant chunk.
    paragraphs: list[str] = []
    for p in raw_paragraphs:
        words = p.split()
        if len(words) <= target * 2:
            paragraphs.append(p)
        else:
            for i in range(0, len(words), target):
                paragraphs.append(" ".join(words[i : i + target]))

    chunks: list[str] = []
    current: list[str] = []
    current_words = 0

    for paragraph in paragraphs:
        word_count = len(paragraph.split())
        if current and current_words + word_count > target:
            chunks.append("\n\n".join(current))
            # carry the tail of the previous chunk forward for overlap
            overlap_paragraphs: list[str] = []
            overlap_words = 0
            for p in reversed(current):
                pw = len(p.split())
                if overlap_words >= overlap:
                    break
                overlap_paragraphs.insert(0, p)
                overlap_words += pw
            current = overlap_paragraphs
            current_words = overlap_words
        current.append(paragraph)
        current_words += word_count

    if current:
        chunks.append("\n\n".join(current))
    return chunks


def chunk_pdf_pages(blocks: list[PageBlock]) -> list[Chunk]:
    """Each PDF page is a natural chunk boundary for slide decks; pages
    with a lot of text get further split, each sub-chunk keeping the same
    page number for citation purposes."""
    chunks: list[Chunk] = []
    for block in blocks:
        for piece in _split_words(block.text, TARGET_WORDS, OVERLAP_WORDS) or [block.text]:
            chunks.append(
                Chunk(
                    text=piece,
                    content_type="prose",
                    page_start=block.page_number,
                    page_end=block.page_number,
                )
            )
    return chunks


def chunk_docx_sections(sections: list[DocxSection]) -> list[Chunk]:
    chunks: list[Chunk] = []
    for section in sections:
        prefixed = f"{section.heading}\n{section.text}" if section.heading else section.text
        for piece in _split_words(prefixed, TARGET_WORDS, OVERLAP_WORDS) or [prefixed]:
            chunks.append(Chunk(text=piece, content_type="prose"))
    return chunks


def _looks_minified(text: str) -> bool:
    """Bundled/minified JS (very long lines, few newlines relative to size)
    can make tree-sitter parsing pathologically slow or hang outright --
    skip straight to the cheap fixed-window fallback for these instead of
    ever attempting to parse them."""
    lines = text.splitlines() or [text]
    avg_line_length = len(text) / len(lines)
    return avg_line_length > 300 or len(text) > 20_000 and len(lines) < 20


def chunk_code(text: str, language: str) -> list[Chunk]:
    if not _looks_minified(text):
        tree_sitter_chunks = _try_tree_sitter_chunks(text, language)
        if tree_sitter_chunks is not None:
            return tree_sitter_chunks
    return _fixed_window_chunks(text, language)


def _fixed_window_chunks(text: str, language: str) -> list[Chunk]:
    lines = text.splitlines()
    if not lines:
        return []
    chunks: list[Chunk] = []
    start = 0
    while start < len(lines):
        end = min(start + CODE_WINDOW_LINES, len(lines))
        piece = "\n".join(lines[start:end])
        if piece.strip():
            chunks.append(
                Chunk(
                    text=piece,
                    content_type="code",
                    line_start=start + 1,
                    line_end=end,
                    language=language,
                )
            )
        if end == len(lines):
            break
        start = end - CODE_WINDOW_OVERLAP
    return chunks


def _try_tree_sitter_chunks(text: str, language: str) -> list[Chunk] | None:
    try:
        from tree_sitter_language_pack import get_parser
    except ImportError:
        return None

    try:
        parser = get_parser(language)
    except Exception:
        return None

    try:
        tree = parser.parse(text.encode("utf-8"))
    except Exception:
        return None

    root = tree.root_node
    chunks: list[Chunk] = []
    buffer_start_line: int | None = None
    buffer_end_line: int | None = None
    buffer_text: list[str] = []

    def flush():
        if buffer_text:
            chunks.append(
                Chunk(
                    text="\n".join(buffer_text),
                    content_type="code",
                    line_start=buffer_start_line + 1,
                    line_end=buffer_end_line + 1,
                    language=language,
                )
            )

    for child in root.children:
        snippet = text.encode("utf-8")[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
        if child.type in CHUNKABLE_NODE_TYPES or len(snippet.splitlines()) > 5:
            flush()
            chunks.append(
                Chunk(
                    text=snippet,
                    content_type="code",
                    line_start=child.start_point[0] + 1,
                    line_end=child.end_point[0] + 1,
                    language=language,
                )
            )
            buffer_text = []
            buffer_start_line = None
        else:
            if buffer_start_line is None:
                buffer_start_line = child.start_point[0]
            buffer_end_line = child.end_point[0]
            buffer_text.append(snippet)
    flush()

    if not chunks:
        return None
    return chunks


def enforce_char_cap(chunks: list[Chunk], max_chars: int = HARD_CHAR_CAP) -> list[Chunk]:
    """Final safety net, independent of word/line counting: some files (CSV
    data dumps with no spaces so 'words' are whole rows, minified code with
    very long lines) slip past the word- or line-based limits above and
    produce a single huge chunk. Guarantee no chunk ever exceeds max_chars."""
    result: list[Chunk] = []
    for chunk in chunks:
        if len(chunk.text) <= max_chars:
            result.append(chunk)
            continue
        for i in range(0, len(chunk.text), max_chars):
            result.append(replace(chunk, text=chunk.text[i : i + max_chars]))
    return result
