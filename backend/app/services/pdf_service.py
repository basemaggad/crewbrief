"""
PDF content extraction — routes each page's content by type:

  text   → prose/paragraphs, stripped of repeating header/footer boilerplate
  table  → Markdown-formatted table (preserves column headers + row structure)
  image  → raw bytes for vision-LLM summarization (filled later by document_service)

Two-pass approach:
  Pass 1 — pdfplumber: table detection + Markdown extraction + text extraction
            with table regions masked out (so table text isn't double-counted).
  Pass 2 — PyMuPDF:    embedded raster image extraction; page rasterization for
            vector-heavy diagram pages (schematics drawn as PDF vector commands,
            which do NOT appear in get_images()).

Aviation-manual note:
  Most hydraulic/electrical/fuel schematics in FCOMs/AMMs are vector graphics,
  not raster images. The only way to capture them is to rasterize the page.
  Pass 2b detects these pages by low text density + high drawing count.
"""

from io import BytesIO
from typing import List, Dict, Any, Optional, Set
import re
from collections import Counter

import pdfplumber
import pymupdf   # PyMuPDF — use `import pymupdf`, not `import fitz` (legacy alias)


# ── Tuning knobs ─────────────────────────────────────────────────────────────
HEADER_ZONE_LINES = 3       # lines at top/bottom of page inspected for boilerplate
FOOTER_ZONE_LINES = 3
REPEAT_FRACTION   = 0.5     # fraction of pages a line must appear on to be boilerplate
MIN_PAGES_FOR_DETECTION = 4 # below this, repetition is unreliable

MIN_IMAGE_BYTES = 5_000     # skip images smaller than this (icons, bullets, watermarks)

# Pages with fewer text chars AND more drawings than these thresholds are treated
# as vector-diagram pages and rasterized for vision processing.
DIAGRAM_TEXT_THRESHOLD = 300
DIAGRAM_DRAWING_THRESHOLD = 15

# Max data rows per table chunk. Keeps each chunk under gemini-embedding-001's
# 2048-token input limit. Headers are repeated in each chunk so column context
# is never lost. (Typical MEL/DDG row: ~20–50 tokens → 25 rows ≈ 500–1250 tokens)
TABLE_MAX_ROWS_PER_CHUNK = 25
# ─────────────────────────────────────────────────────────────────────────────

_DIGITS = re.compile(r"\d+")


# ── Header / footer detection (ported from original pdf_service.py) ───────────

def _normalize(line: str) -> str:
    masked = _DIGITS.sub("#", line)
    return " ".join(masked.split()).strip().lower()


def _find_repeating_lines(page_line_lists: List[List[str]]) -> Set[str]:
    header_counter: Counter = Counter()
    footer_counter: Counter = Counter()
    for lines in page_line_lists:
        non_empty = [ln for ln in lines if ln.strip()]
        if not non_empty:
            continue
        for ln in {_normalize(l) for l in non_empty[:HEADER_ZONE_LINES]}:
            header_counter[ln] += 1
        for ln in {_normalize(l) for l in non_empty[-FOOTER_ZONE_LINES:]}:
            footer_counter[ln] += 1
    n = len(page_line_lists)
    threshold = max(2, int(n * REPEAT_FRACTION))
    repeating: Set[str] = set()
    for counter in (header_counter, footer_counter):
        for ln, count in counter.items():
            if ln and count >= threshold:
                repeating.add(ln)
    return repeating


def _strip_lines(text: str, repeating: Set[str]) -> str:
    kept = [ln for ln in text.split("\n") if _normalize(ln) not in repeating]
    return "\n".join(kept).strip()


# ── Table helpers ─────────────────────────────────────────────────────────────

def _rows_to_markdown(rows: List[List[Optional[str]]]) -> str:
    """Convert a pdfplumber table (list-of-rows, each a list-of-cells) to Markdown."""
    if not rows or len(rows) < 2:
        return ""
    max_cols = max(len(r) for r in rows)

    def clean(cell) -> str:
        return str(cell or "").replace("\n", " ").strip()

    def pad(row: list) -> List[str]:
        return [clean(c) for c in row] + [""] * (max_cols - len(row))

    lines = [
        "| " + " | ".join(pad(rows[0])) + " |",
        "| " + " | ".join(["---"] * max_cols) + " |",
    ]
    for row in rows[1:]:
        lines.append("| " + " | ".join(pad(row)) + " |")
    return "\n".join(lines)


def _split_table(rows: List[List[Optional[str]]]) -> List[str]:
    """
    Return one or more Markdown strings for a table. Large tables are split into
    row-group chunks, repeating the header row in each so column meaning is never
    lost at the embedding boundary.
    """
    if not rows:
        return []
    header = rows[0]
    data   = rows[1:]
    if len(data) <= TABLE_MAX_ROWS_PER_CHUNK:
        md = _rows_to_markdown(rows)
        return [md] if md else []
    chunks = []
    for i in range(0, len(data), TABLE_MAX_ROWS_PER_CHUNK):
        md = _rows_to_markdown([header] + data[i:i + TABLE_MAX_ROWS_PER_CHUNK])
        if md:
            chunks.append(md)
    return chunks


# ── Main extraction function ──────────────────────────────────────────────────

def extract_content(pdf_bytes: bytes) -> List[Dict[str, Any]]:
    """
    Extract all content from a PDF and return a typed content list.

    Each item is a dict:
      {
        "type":        "text" | "table" | "image",
        "content":     str,    # prose/Markdown for text/table; empty for images
                               # (filled later by vision LLM in document_service)
        "page":        int,    # 1-indexed page number
        "image_bytes": bytes | None,  # raw image bytes (image type only)
        "image_ext":   str   | None,  # e.g. "png", "jpeg" (image type only)
        "image_idx":   int   | None,  # index within page (image type only)
      }
    """
    items: List[Dict[str, Any]] = []

    # ── Pass 1: text + tables via pdfplumber ──────────────────────────────
    with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:

        # Collect raw text lines for header/footer detection (one pass over all pages)
        all_line_lists: List[List[str]] = []
        for pg in pdf.pages:
            raw = pg.extract_text() or ""
            all_line_lists.append(raw.split("\n"))

        repeating: Set[str] = set()
        if len(pdf.pages) >= MIN_PAGES_FOR_DETECTION:
            repeating = _find_repeating_lines(all_line_lists)

        for page_num, page in enumerate(pdf.pages, start=1):

            # --- Tables ---
            table_finder = page.find_tables()
            table_bboxes = [t.bbox for t in table_finder]

            for tbl in table_finder:
                rows = tbl.extract()
                if not rows:
                    continue
                for md in _split_table(rows):
                    items.append({
                        "type":        "table",
                        "content":     md,
                        "page":        page_num,
                        "image_bytes": None,
                        "image_ext":   None,
                        "image_idx":   None,
                    })

            # --- Text (table regions masked out) ---
            # Chain outside_bbox() calls to progressively exclude each table region.
            text_page = page
            for bbox in table_bboxes:
                text_page = text_page.outside_bbox(bbox)
            text = text_page.extract_text() or ""
            text = _strip_lines(text, repeating)
            if text.strip():
                items.append({
                    "type":        "text",
                    "content":     text,
                    "page":        page_num,
                    "image_bytes": None,
                    "image_ext":   None,
                    "image_idx":   None,
                })

    # ── Pass 2: images via PyMuPDF ────────────────────────────────────────
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    try:
        seen_xrefs: Set[int] = set()

        for page_num, page in enumerate(doc, start=1):
            page_img_idx = 0

            # 2a. Embedded raster images (photos, scanned diagrams stored as bitmaps)
            for img_ref in page.get_images(full=True):
                xref = img_ref[0]
                if xref in seen_xrefs:
                    continue            # same image referenced on multiple pages
                seen_xrefs.add(xref)
                try:
                    img_data  = doc.extract_image(xref)
                    img_bytes = img_data.get("image", b"")
                    if len(img_bytes) < MIN_IMAGE_BYTES:
                        continue        # skip tiny decorative elements
                    items.append({
                        "type":        "image",
                        "content":     "",
                        "page":        page_num,
                        "image_bytes": img_bytes,
                        "image_ext":   img_data.get("ext", "png"),
                        "image_idx":   page_img_idx,
                    })
                    page_img_idx += 1
                except Exception:
                    continue

            # 2b. Vector-graphic diagram pages (schematics drawn as PDF vector commands).
            # get_images() returns nothing for these — the only way to capture them is
            # to rasterize the whole page. Detect by low text density + high drawing count.
            page_text = page.get_text()
            drawings  = page.get_drawings()
            if (len(page_text) < DIAGRAM_TEXT_THRESHOLD
                    and len(drawings) > DIAGRAM_DRAWING_THRESHOLD):
                try:
                    pixmap    = page.get_pixmap(dpi=150)
                    png_bytes = pixmap.tobytes("png")
                    if len(png_bytes) >= MIN_IMAGE_BYTES:
                        items.append({
                            "type":        "image",
                            "content":     "",
                            "page":        page_num,
                            "image_bytes": png_bytes,
                            "image_ext":   "png",
                            "image_idx":   page_img_idx,
                        })
                except Exception:
                    pass

    finally:
        doc.close()

    # Sort by page so all content comes out in document order
    items.sort(key=lambda x: x["page"])
    return items


# ── Legacy shim (kept for any callers that haven't been updated yet) ──────────

def extract_pages(pdf_bytes: bytes):
    """
    Deprecated — returns plain-text pages in the old (page_num, text) format.
    Use extract_content() for new code.
    """
    from io import BytesIO as _BytesIO
    items = [i for i in extract_content(pdf_bytes) if i["type"] == "text"]
    # Deduplicate per page (extract_content may yield multiple text items per page)
    pages_text: Dict[int, List[str]] = {}
    for item in items:
        pages_text.setdefault(item["page"], []).append(item["content"])
    return [(p, "\n\n".join(texts)) for p, texts in sorted(pages_text.items())]
