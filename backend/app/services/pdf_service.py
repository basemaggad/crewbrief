"""
PDF text extraction.
Uses pypdf to pull text page by page. Each chunk we create later carries
the page number so citations can point users to the right page.
"""
from io import BytesIO
from typing import List, Tuple
from pypdf import PdfReader


def extract_pages(pdf_bytes: bytes) -> List[Tuple[int, str]]:
    """Returns list of (page_number, page_text) tuples. Page numbers are 1-indexed."""
    reader = PdfReader(BytesIO(pdf_bytes))
    pages: List[Tuple[int, str]] = []
    for i, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        pages.append((i, text))
    return pages
