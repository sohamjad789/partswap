"""Local PDF text and image helpers for the extraction pipeline."""

from pathlib import Path

import fitz


def page_texts(pdf_path: Path, max_pages: int = 4) -> list[dict[str, object]]:
    """Return one-based page text, falling back to pdfplumber for sparse pages."""
    try:
        document = fitz.open(pdf_path)
    except (fitz.FileDataError, OSError, RuntimeError):
        return []
    try:
        pages = [{"page": index + 1, "text": document[index].get_text("text").strip()}
                 for index in range(min(len(document), max_pages))]
    finally:
        document.close()
    sparse = [entry for entry in pages if len(str(entry["text"])) < 40]
    if not sparse:
        return pages
    try:
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            for entry in sparse:
                text = (pdf.pages[int(entry["page"]) - 1].extract_text() or "").strip()
                if text:
                    entry["text"] = text
    except Exception:
        pass
    return pages


def page_png(pdf_path: Path, page: int, dpi: int = 150) -> bytes:
    """Render one one-based PDF page to PNG bytes."""
    try:
        document = fitz.open(pdf_path)
        try:
            if page < 1 or page > len(document):
                return b""
            pixmap = document[page - 1].get_pixmap(dpi=dpi, alpha=False)
            return pixmap.tobytes("png")
        finally:
            document.close()
    except (fitz.FileDataError, OSError, RuntimeError):
        return b""
