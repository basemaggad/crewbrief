"""
PDF text extraction with repeating header/footer removal.

pypdf returns the full text of each page, including the banner that
repeats at the top/bottom of every page: operator name, document code,
revision, "Page X of Y", supplier markings, "CONFIDENTIAL", etc. That
boilerplate is a problem for two reasons:

  1. Identifying info — it stamps "Royal Jordanian / <supplier>" onto
     every chunk that later leaves the system for embedding/answering.
  2. Embedding quality — if every chunk shares the same banner text,
     embeddings drift toward that shared boilerplate and semantic search
     gets worse.

We remove it with "repeating-line detection": a line that appears in the
top or bottom zone of a large fraction of pages is boilerplate, not
content, so we drop it. Digits are masked before comparison so that
"Page 3 of 210" and "Page 4 of 210" are recognised as the same banner.

This is a drop-in replacement for the previous extract_pages(): same
signature, same List[Tuple[int, str]] return shape. Nothing downstream
(chunking, embedding, storage) needs to change.
"""
from io import BytesIO
from typing import List, Tuple, Set
import re
from collections import Counter
from pypdf import PdfReader


# ── Tuning knobs ────────────────────────────────────────────────────────────
# How many lines at the top / bottom of each page count as the header /
# footer "zone" we inspect for boilerplate. Aviation manuals usually have
# a 1–3 line banner; widen if a banner is taller.
HEADER_ZONE_LINES = 3
FOOTER_ZONE_LINES = 3

# A line must appear (in a zone) on at least this fraction of pages to be
# treated as repeating boilerplate.
REPEAT_FRACTION = 0.5

# Below this page count, repetition isn't a reliable signal, so we skip
# stripping entirely rather than risk deleting real content.
MIN_PAGES_FOR_DETECTION = 4
# ─────────────────────────────────────────────────────────────────────────────


_DIGITS = re.compile(r"\d+")


def _normalize(line: str) -> str:
    """
    Collapse whitespace and mask digit runs so banners that change per page
    (page numbers, dates, revision counters) still compare as identical.
    Used only for *matching* — the original line text is what gets removed.
    """
    masked = _DIGITS.sub("#", line)
    return " ".join(masked.split()).strip().lower()


def _find_repeating_lines(page_line_lists: List[List[str]]) -> Set[str]:
    """
    Count normalized lines that recur in the header or footer zone across
    pages. Returns the set of normalized strings considered boilerplate.
    """
    header_counter: Counter = Counter()
    footer_counter: Counter = Counter()

    for lines in page_line_lists:
        non_empty = [l for l in lines if l.strip()]
        if not non_empty:
            continue
        header = non_empty[:HEADER_ZONE_LINES]
        footer = non_empty[-FOOTER_ZONE_LINES:]
        # set() per page so a line repeated within one page counts once.
        for ln in {_normalize(l) for l in header}:
            header_counter[ln] += 1
        for ln in {_normalize(l) for l in footer}:
            footer_counter[ln] += 1

    n_pages = len(page_line_lists)
    threshold = max(2, int(n_pages * REPEAT_FRACTION))

    repeating: Set[str] = set()
    for counter in (header_counter, footer_counter):
        for ln, count in counter.items():
            if ln and count >= threshold:
                repeating.add(ln)
    return repeating


def _strip_lines(text: str, repeating: Set[str]) -> str:
    """Drop any line whose normalized form is in the boilerplate set."""
    kept = [line for line in text.split("\n") if _normalize(line) not in repeating]
    return "\n".join(kept).strip()


def extract_pages(pdf_bytes: bytes) -> List[Tuple[int, str]]:
    """
    Returns list of (page_number, page_text) tuples. Page numbers are
    1-indexed. Repeating header/footer boilerplate is removed when the
    document has enough pages for repetition to be a reliable signal.
    """
    reader = PdfReader(BytesIO(pdf_bytes))

    # Pass 1: pull raw text per page and split into lines.
    raw_pages: List[Tuple[int, str]] = []
    page_line_lists: List[List[str]] = []
    for i, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        raw_pages.append((i, text))
        page_line_lists.append(text.split("\n"))

    # Decide what to strip — only if there are enough pages to judge.
    repeating: Set[str] = set()
    if len(raw_pages) >= MIN_PAGES_FOR_DETECTION:
        repeating = _find_repeating_lines(page_line_lists)

    # Pass 2: rebuild each page with boilerplate removed.
    pages: List[Tuple[int, str]] = []
    for page_num, text in raw_pages:
        cleaned = _strip_lines(text, repeating) if repeating else text
        pages.append((page_num, cleaned))
    return pages


# Optional: expose what was stripped, for debugging/inspection.
def detect_boilerplate(pdf_bytes: bytes) -> Set[str]:
    """
    Return the set of normalized lines that extract_pages() would strip.
    Handy for verifying the detector caught the real banner (and nothing
    else) before trusting it on a full document.
    """
    reader = PdfReader(BytesIO(pdf_bytes))
    page_line_lists: List[List[str]] = []
    for page in reader.pages:
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        page_line_lists.append(text.split("\n"))
    if len(page_line_lists) < MIN_PAGES_FOR_DETECTION:
        return set()
    return _find_repeating_lines(page_line_lists)
