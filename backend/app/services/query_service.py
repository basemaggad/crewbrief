"""
Query pipeline.

For a question:
1. Embed the question.
2. Retrieve top-K most similar chunks for the user's organization.
3. Pass them to Claude with the system prompt.
4. Build a structured citation list and return.

Retrieval method: pgvector cosine similarity, performed via a Postgres
RPC named `match_chunks` (defined in the Supabase migration). If that RPC
is unavailable, we fall back to in-memory cosine similarity over all
chunks for the org (slower but works without the RPC).
"""
from typing import List, Dict, Any
from app.core.config import settings
from app.db.supabase_client import get_supabase_admin
from app.services.embedding_service import embed_query, cosine_similarity
from app.services.claude_service import generate_answer


def _retrieve_via_rpc(supabase, query_vec: List[float], org_id: str, top_k: int):
    """Try pgvector RPC. Returns list of chunk dicts or raises."""
    res = supabase.rpc(
        "match_chunks",
        {
            "query_embedding": query_vec,
            "match_organization_id": org_id,
            "match_count": top_k,
        },
    ).execute()
    return res.data or []


def _retrieve_in_memory(supabase, query_vec: List[float], org_id: str, top_k: int):
    """Fallback: pull all chunks for org and rank in Python."""
    res = supabase.table("document_chunks").select(
        "id, document_id, content, page_start, page_end, embedding"
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
    """Attach document name, revision, etc. to each chunk."""
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
            "chunk_id": c.get("id"),
            "document_id": c.get("document_id"),
            "document_name": d.get("name"),
            "revision": d.get("revision"),
            "document_type": d.get("document_type"),
            "page_start": c.get("page_start"),
            "page_end": c.get("page_end"),
            "content": c.get("content"),
        })
    return out


def answer_question(question: str, organization_id: str) -> Dict[str, Any]:
    supabase = get_supabase_admin()
    query_vec = embed_query(question)
    top_k = settings.MAX_CHUNKS_PER_QUERY

    # Retrieve
    try:
        raw = _retrieve_via_rpc(supabase, query_vec, organization_id, top_k)
    except Exception:
        raw = _retrieve_in_memory(supabase, query_vec, organization_id, top_k)

    chunks = _hydrate_chunks(supabase, raw)

    # Generate
    answer = generate_answer(question, chunks)

    # Build citation payload
    citations = []
    for c in chunks:
        citations.append({
            "chunk_id": c.get("chunk_id"),
            "document_name": c.get("document_name") or "Unknown document",
            "revision": c.get("revision"),
            "section": None,
            "excerpt": (c.get("content") or "")[:280],
        })

    return {"answer": answer, "citations": citations}
