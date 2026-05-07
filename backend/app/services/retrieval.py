from anthropic import Anthropic
from app.db.client import supabase_admin
from app.core.config import settings

anthropic = Anthropic(api_key=settings.anthropic_api_key)

def embed_query(query: str) -> list[float]:
    """
    Embed the user's question using the same method as the document chunks.
    This ensures the query and chunks live in the same vector space —
    like tuning both a transmitter and receiver to the same frequency.
    """
    response = anthropic.messages.create(
        model="claude-opus-4-5",
        max_tokens=1,
        messages=[{"role": "user", "content": query}],
        system="Return only a JSON array of 1536 floats representing the embedding. No other text.",
    )
    import json
    return json.loads(response.content[0].text)

def retrieve_chunks(
    query: str,
    organization_id: str,
    document_ids: list[str] | None = None,
    match_count: int = 8,
) -> list[dict]:
    """
    Convert the query to a vector and find the most semantically
    similar chunks in the database using the match_chunks() function
    we defined in the SQL schema.
    """
    embedding = embed_query(query)

    result = supabase_admin.rpc("match_chunks", {
        "query_embedding": embedding,
        "org_id": organization_id,
        "match_count": match_count,
        "min_similarity": 0.5,
        "filter_doc_ids": document_ids,
    }).execute()

    return result.data or []

def build_context(chunks: list[dict]) -> str:
    """
    Format retrieved chunks into a structured context block
    that gets inserted into the Claude prompt.
    Each chunk is labeled with its source so Claude can cite it.
    """
    if not chunks:
        return "No relevant documents found."

    context_parts = []
    for i, chunk in enumerate(chunks):
        source = f"[Source {i+1}]"
        if chunk.get("section_title"):
            source += f" {chunk['section_title']}"
        if chunk.get("page_start"):
            source += f" (p.{chunk['page_start']})"
        context_parts.append(f"{source}\n{chunk['content']}")

    return "\n\n---\n\n".join(context_parts)

def generate_answer(
    query: str,
    chunks: list[dict],
    conversation_history: list[dict] | None = None,
) -> tuple[str, bool]:
    """
    Send the query + retrieved context to Claude and get a grounded answer.
    Returns the answer text and a boolean (True/False) indicating
    whether the question could not be answered from the documents.
    """
    context = build_context(chunks)
    history = conversation_history or []

    system_prompt = """You are CrewBrief, an aviation document assistant for Royal Jordanian pilots.
Your answers must be grounded strictly in the provided document excerpts.

Rules:
- Only answer from the provided context. Never use general aviation knowledge not present in the documents.
- Always cite your sources using [Source N] references.
- If the answer is not found in the context, respond with exactly: UNRESOLVED: followed by a brief explanation.
- Be precise and concise. Pilots need clear, actionable information.
- For procedures, preserve the exact steps and order from the source.
- Never paraphrase safety-critical limits or values — quote them exactly."""

    messages = history + [
        {
            "role": "user",
            "content": f"Context from documents:\n\n{context}\n\nQuestion: {query}"
        }
    ]

    response = anthropic.messages.create(
        model="claude-opus-4-5",
        max_tokens=1500,
        system=system_prompt,
        messages=messages,
    )

    answer = response.content[0].text
    has_unresolved = answer.startswith("UNRESOLVED:")

    return answer, has_unresolved
