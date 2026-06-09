"""
Claude API integration.

Two responsibilities:
  summarize_image()   Takes raw image bytes, returns an exhaustive text
                      description for embedding and retrieval.
  generate_answer()   Takes a question + retrieved chunks, calls Claude,
                      returns the answer string. Automatically switches to
                      a multimodal prompt when any chunk carries image_bytes.
"""
import base64
import logging
from typing import List, Dict, Any

from anthropic import Anthropic

from app.core.config import settings

logger = logging.getLogger(__name__)

_client: Anthropic | None = None


def get_client() -> Anthropic:
    global _client
    if _client is None:
        _client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    return _client


# ── System prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are CrewBrief, an aviation document Q&A assistant for Royal Jordanian flight crews.

Your behavior rules:
1. Answer ONLY using the document excerpts provided in the user message under "SOURCES". Do not use any outside knowledge.
2. If the sources don't contain the answer, say so plainly: "I don't have this information in your current document library."
3. Be concise and operationally direct — pilots want clear, accurate answers fast.
4. Cite sources inline using [1], [2], etc. matching the source numbers given.
5. If procedures or limitations are involved, quote exact figures (speeds, altitudes, times) from the source.
6. Never invent procedures, limitations, or values not present in the sources.
7. If multiple sources conflict, point this out and cite both.
"""

_MEDIA_TYPE_MAP = {
    "png":  "image/png",
    "jpeg": "image/jpeg",
    "jpg":  "image/jpeg",
    "gif":  "image/gif",
    "webp": "image/webp",
}


# ── Image summarization ───────────────────────────────────────────────────────

def summarize_image(image_bytes: bytes, image_ext: str = "png") -> str:
    """
    Pass an image to Claude vision and return an exhaustive text description.
    The description is embedded and searched — it must be fully self-contained.
    Returns empty string on failure (caller should log and skip the chunk).
    """
    media_type = _MEDIA_TYPE_MAP.get(image_ext.lower(), "image/png")
    b64_data   = base64.standard_b64encode(image_bytes).decode("utf-8")
    try:
        response = get_client().messages.create(
            model=settings.CLAUDE_MODEL,
            max_tokens=800,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type":       "base64",
                            "media_type": media_type,
                            "data":       b64_data,
                        },
                    },
                    {
                        "type": "text",
                        "text": (
                            "This is a diagram or figure from an aviation manual. "
                            "Describe it exhaustively and precisely. Include: "
                            "all labeled components, system names, flow directions "
                            "(arrows, lines), numeric values, switch/valve states, "
                            "color-coding conventions, and any text visible in the image. "
                            "Write in dense prose — do not omit any detail that would "
                            "help a pilot or engineer understand the system. "
                            "If it is a table or checklist rather than a schematic, "
                            "transcribe every row and value."
                        ),
                    },
                ],
            }],
        )
        return response.content[0].text if response.content else ""
    except Exception as exc:
        logger.error("summarize_image failed: %s", exc)
        return ""


# ── Answer generation ─────────────────────────────────────────────────────────

def generate_answer(question: str, chunks: List[Dict[str, Any]]) -> str:
    """
    Build the prompt from question + retrieved chunks and call Claude.
    Switches to a multimodal content list when any chunk has image_bytes.
    """
    has_images = any(c.get("image_bytes") for c in chunks)

    if has_images:
        user_content = _build_multimodal_content(question, chunks)
    else:
        user_content = build_user_message(question, chunks)

    client = get_client()
    response = client.messages.create(
        model=settings.CLAUDE_MODEL,
        max_tokens=1500,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )
    parts = []
    for block in response.content:
        if getattr(block, "type", None) == "text":
            parts.append(block.text)
    return "\n".join(parts).strip()


def build_user_message(question: str, chunks: List[Dict[str, Any]]) -> str:
    """Format question + text/table chunks into a single string (no images)."""
    if not chunks:
        return (
            f"QUESTION: {question}\n\n"
            "SOURCES: (no relevant excerpts found in the document library)"
        )
    lines = ["SOURCES:"]
    for i, c in enumerate(chunks, start=1):
        doc      = c.get("document_name", "Unknown document")
        rev      = c.get("revision") or "—"
        page     = c.get("page_start") or "?"
        section  = c.get("section_title") or ""
        sect_part = f", §{section}" if section else ""
        lines.append(f"\n[{i}] {doc} (Rev {rev}, p.{page}{sect_part})")
        lines.append(c.get("content", ""))
    lines.append("\n\nQUESTION: " + question)
    return "\n".join(lines)


def _build_multimodal_content(
    question: str, chunks: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Build a multimodal content list for the Anthropic messages API.
    Text/table chunks become text blocks; image chunks with bytes become
    image blocks (capped at 3 to control cost/latency).
    """
    content: List[Dict[str, Any]] = [{"type": "text", "text": "SOURCES:\n"}]
    images_included = 0

    for i, c in enumerate(chunks, start=1):
        doc       = c.get("document_name", "Unknown document")
        rev       = c.get("revision") or "—"
        page      = c.get("page_start") or "?"
        section   = c.get("section_title") or ""
        sect_part = f", §{section}" if section else ""
        header    = f"[{i}] {doc} (Rev {rev}, p.{page}{sect_part})"

        img_bytes = c.get("image_bytes")
        if img_bytes and images_included < 3:
            ext        = c.get("image_ext", "png")
            media_type = _MEDIA_TYPE_MAP.get(ext.lower(), "image/png")
            b64_data   = base64.standard_b64encode(img_bytes).decode("utf-8")
            content.append({"type": "text", "text": f"\n{header} (diagram/figure):"})
            content.append({
                "type":   "image",
                "source": {
                    "type":       "base64",
                    "media_type": media_type,
                    "data":       b64_data,
                },
            })
            images_included += 1
            # Include the text summary too (helps Claude reference it in citations)
            if c.get("content"):
                content.append({
                    "type": "text",
                    "text": f"[Image description: {c['content']}]",
                })
        else:
            content.append({
                "type": "text",
                "text": f"\n{header}\n{c.get('content', '')}",
            })

    content.append({"type": "text", "text": f"\n\nQUESTION: {question}"})
    return content
