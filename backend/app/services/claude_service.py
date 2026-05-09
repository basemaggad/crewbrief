"""
Claude API integration.
Sends the user's question along with the retrieved chunks and asks Claude
to answer strictly from the provided sources, with inline citations.
"""
from typing import List, Dict, Any
from anthropic import Anthropic

from app.core.config import settings


_client: Anthropic | None = None


def get_client() -> Anthropic:
    global _client
    if _client is None:
        _client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    return _client


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


def build_user_message(question: str, chunks: List[Dict[str, Any]]) -> str:
    """Format the question and source chunks into a single user message."""
    if not chunks:
        return f"QUESTION: {question}\n\nSOURCES: (no relevant excerpts found in the document library)"

    lines = ["SOURCES:"]
    for i, c in enumerate(chunks, start=1):
        doc = c.get("document_name", "Unknown document")
        rev = c.get("revision") or "—"
        page = c.get("page_start") or "?"
        section = c.get("section") or ""
        sect_part = f", §{section}" if section else ""
        lines.append(f"\n[{i}] {doc} (Rev {rev}, p.{page}{sect_part})")
        lines.append(c.get("content", ""))

    lines.append("\n\nQUESTION: " + question)
    return "\n".join(lines)


def generate_answer(question: str, chunks: List[Dict[str, Any]]) -> str:
    """Calls Claude and returns the answer text."""
    user_msg = build_user_message(question, chunks)

    client = get_client()
    response = client.messages.create(
        model=settings.CLAUDE_MODEL,
        max_tokens=1500,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )

    # Concatenate any text blocks from the response
    parts = []
    for block in response.content:
        if getattr(block, "type", None) == "text":
            parts.append(block.text)
    return "\n".join(parts).strip()
