"""
Query pipeline.

For a question:
1. Embed the question.
2. Retrieve top-K most similar chunks for the user's organization.
3. For image-type chunks, fetch image bytes from Supabase storage (up to 3).
4. Pass chunks to Claude (multimodal if images present).
5. Build a structured citation list and return.

Retrieval method: pgvector cosine similarity via the match_chunks RPC.
Fallback: in-memory cosine similarity (slower, used if RPC is unavailable).
"""
import logging
from typing import List, Dict, Any

from app.core.config import settings
from app.db.supabase_client import get_supabase_admin
from app.services.embedding_service import embed_query, cosine_similarity
from app.services.claude_service import generate_answer

logger = logging.getLogger(__name__)

# Max images to fetch per query — caps latency and prompt size.
IMAGE_FETCH_LIMIT = 3


def answer_question(question: str, organization_id: str) -> Dict[str, Any]:
    supabase = get_supabase_admin()
    query_vec = embed_query(question)
    top_k = settings.MAX_CHUNKS_PER_QUERY

    # Retrieve
    try:
        raw = _retrieve_via_rpc(supabase, query_vec, organization_id, top_k)
    except Exception as exc:
        logger.warning("match_chunks RPC failed (%s), falling back to in-memory", exc)
        raw = _retrieve_in_memory(supabase, query_vec, organization_id, top_k)

    chunks = _hydrate_chunks(supabase, raw)

    # Attach image bytes for image-type chunks (enables multimodal prompt)
    chunks = _attach_image_bytes(supabase, chunks)

    # Generate
    answer = generate_answer(question, chunks)

    # Build citation payload
    citations = []
    for c in chunks:
        citations.append({
            "chunk_id":      c.get("chunk_id"),
            "document_name": c.get("document_name") or "Unknown document",
            "revision":      c.get("revision"),
            "section":       c.get("section_title"),
            "page_start":    c.get("page_start"),
            "chunk_type":    c.get("chunk_type", "text"),
            "excerpt":       (c.get("content") or "")[:280],
        })

    return {"answer": answer, "citations": citations}


# ── Retrieval ─────────────────────────────────────────────────────────────────

def _retrieve_via_rpc(supabase, query_vec: List[float], org_id: str, top_k: int):
    res = supabase.rpc(
        "match_chunks",
        {
            "query_embedding":    query_vec,
            "match_organization_id": org_id,
            "match_count":        top_k,
        },
    ).execute()
    return res.data or []


def _retrieve_in_memory(supabase, query_vec: List[float], org_id: str, top_k: int):
    """Fallback: pull all chunks for org and rank in Python."""
    res = supabase.table("document_chunks").select(
        "id, document_id, content, page_start, page_end, "
        "chunk_index, chunk_type, image_path, embedding"
    ).eq("organization_id", org_id).execute()
    rows = res.data or []
    scored = []
    for r in rows:
        emb = r.get("embedding")
        if not emb:
            continue
        score = cosine_similarity(query_vec, emb)
        scored.append((score, r))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [r for _, r in scored[:top_k]]


def _hydrate_chunks(supabase, raw_chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Attach document metadata to each chunk."""
    if not raw_chunks:
        return []
    doc_ids = list({c["document_id"] for c in raw_chunks if c.get("document_id")})
    docs = supabase.table("documents").select(
        "id, name, revision, document_type"
    ).in_("id", doc_ids).execute()
    doc_lookup = {d["id"]: d for d in (docs.data or [])}

    out = []
    for c in raw_chunks:
        d = doc_lookup.get(c.get("document_id"), {})
        out.append({
            "chunk_id":      c.get("id") or c.get("chunk_id"),
            "document_id":   c.get("document_id"),
            "document_name": d.get("name"),
            "revision":      d.get("revision"),
            "document_type": d.get("document_type"),
            "section_title": c.get("section_title"),
            "page_start":    c.get("page_start"),
            "page_end":      c.get("page_end"),
            "content":       c.get("content", ""),
            "chunk_type":    c.get("chunk_type", "text"),
            "image_path":    c.get("image_path"),
            "image_bytes":   None,   # filled by _attach_image_bytes
            "image_ext":     None,
        })
    return out


def _attach_image_bytes(supabase, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    For up to IMAGE_FETCH_LIMIT image-type chunks, download bytes from
    storage so generate_answer() can build a multimodal prompt.
    """
    fetched = 0
    for chunk in chunks:
        if (
            chunk.get("chunk_type") == "image"
            and chunk.get("image_path")
            and fetched < IMAGE_FETCH_LIMIT
        ):
            try:
                img_bytes = supabase.storage.from_(
                    settings.STORAGE_BUCKET
                ).download(chunk["image_path"])
                if img_bytes:
                    chunk["image_bytes"] = img_bytes
                    ext = chunk["image_path"].rsplit(".", 1)[-1]
                    chunk["image_ext"] = ext if len(ext) <= 4 else "png"
                    fetched += 1
            except Exception as exc:
                logger.warning("Could not fetch image %s: %s", chunk["image_path"], exc)
    return chunks
