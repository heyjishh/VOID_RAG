from __future__ import annotations
from urllib.parse import urlparse
from langchain_core.messages import HumanMessage
from app.config.settings import settings
from app.core.graph.state import JuryAIState
from app.core.llm.provider import get_llm
from app.core.retrieval.hybrid import hybrid_search
from app.core.retrieval.reranker import get_reranker
from app.core.retrieval.citation import derive_citations
from app.core.graph.evidence_merger import ensure_content_hashes
from app.core.web_search.searcher import web_search
from app.core.memory import format_history as _format_history

_ANSWER_PROMPT = """You are a precise legal AI. Answer based ONLY on the context below.
Quote relevant text in double-quotes. Cite sources as [Source: filename, Page N].
If insufficient context, say so — never hallucinate.

Conversation so far (for follow-up context only — do NOT treat as evidence):
{history}

Question: {question}

Legal Context:
{legal_ctx}

Web Context:
{web_ctx}

Answer:"""


def _domain_of(url: str) -> str:
    netloc = urlparse(url).netloc
    return netloc.removeprefix("www.") if netloc else url


# ---------------------------------------------------------------------------
# Retrieval nodes
# ---------------------------------------------------------------------------

async def legal_retrieve_node(state: JuryAIState, qdrant=None, quickwit=None) -> dict:
    import asyncio
    from app.core.retrieval.qdrant_store import QdrantStore
    from app.core.retrieval.quickwit_store import QuickwitStore

    steps = list(state.get("reasoning_steps") or [])
    steps.append({
        "step": "internal_retrieval_start",
        "detail": "Searching internal legal corpus",
    })
    if state.get("on_step"):
        state["on_step"](steps[-1])

    def _sync_retrieve():
        _qdrant = qdrant or QdrantStore()
        _quickwit = quickwit or QuickwitStore()
        chunks = hybrid_search(state["question"], top_k=20, qdrant=_qdrant, quickwit=_quickwit)
        return get_reranker().rerank(state["question"], chunks, top_k=5)

    reranked = ensure_content_hashes(await asyncio.to_thread(_sync_retrieve))

    files = list(dict.fromkeys(c.get("source", "unknown") for c in reranked))
    detail = (
        f"{len(reranked)} chunks retrieved from: {', '.join(files)}"
        if files else "No matching chunks found in corpus"
    )
    steps.append({
        "step": "internal_retrieval_done",
        "detail": detail,
        "files": files,
    })
    if state.get("on_step"):
        state["on_step"](steps[-1])
    return {"legal_chunks": reranked, "reasoning_steps": steps}


async def web_search_node(state: JuryAIState) -> dict:
    steps = list(state.get("reasoning_steps") or [])
    steps.append({
        "step": "web_search_start",
        "detail": "Searching web for current legal information",
    })
    if state.get("on_step"):
        state["on_step"](steps[-1])

    results = await web_search(state["question"], max_results=settings.WEB_SEARCH_MAX_RESULTS)

    sites = list(dict.fromkeys(_domain_of(r.get("url", "")) for r in results if r.get("url")))
    detail = (
        f"{len(results)} web sources retrieved from: {', '.join(sites)}"
        if sites else "No web sources found"
    )
    steps.append({
        "step": "web_search_done",
        "detail": detail,
        "sites": sites,
    })
    if state.get("on_step"):
        state["on_step"](steps[-1])
    # Return both web_evidence (new field) and web_results (backward compat)
    return {"web_evidence": results, "web_results": results, "reasoning_steps": steps}


# ---------------------------------------------------------------------------
# Evidence merge node (new — streaming workflow only)
# ---------------------------------------------------------------------------

async def evidence_merge_node(state: JuryAIState) -> dict:
    from app.config.settings import settings as _settings
    from app.core.graph.evidence_merger import merge_evidence

    legal_chunks = list(state.get("legal_chunks") or [])
    web_evidence = list(state.get("web_evidence") or [])

    merged = merge_evidence(legal_chunks, web_evidence, _settings)

    internal_count = sum(1 for e in merged if e.get("domain") == "internal")
    web_count = sum(1 for e in merged if e.get("domain") == "web")

    steps = list(state.get("reasoning_steps") or [])
    steps.append({
        "step": "evidence_merged",
        "detail": (
            f"{len(merged)} evidence items ranked by authority "
            f"({internal_count} from corpus, {web_count} from web)"
        ),
    })
    if state.get("on_step"):
        state["on_step"](steps[-1])
    return {"merged_evidence": merged, "reasoning_steps": steps}


# ---------------------------------------------------------------------------
# Answer generation node
# ---------------------------------------------------------------------------

async def generate_answer_node(state: JuryAIState) -> dict:
    merged = list(state.get("merged_evidence") or [])

    if merged:
        # New path: merged_evidence available — group by domain
        legal_ctx = "\n\n".join(
            f"[{c['source']} p.{c['page']}]\n{c['text']}"
            for c in merged
            if c.get("domain") == "internal" and c.get("text") and c.get("source")
        ) or "(none)"
        web_ctx = "\n\n".join(
            f"[{r.get('title', '')}]({r.get('url', '')})\n{r.get('content', '')}"
            for r in merged
            if r.get("domain") == "web"
        ) or "(none)"
    else:
        # Old path: use raw legal_chunks and web_results (legacy POST endpoint)
        legal_ctx = "\n\n".join(
            f"[{c['source']} p.{c['page']}]\n{c['text']}"
            for c in state.get("legal_chunks") or []
        ) or "(none)"
        web_ctx = "\n\n".join(
            f"[{r['title']}]({r['url']})\n{r['content']}"
            for r in state.get("web_results") or []
        ) or "(none)"

    prompt = (
        _ANSWER_PROMPT
        .replace("{question}", state["question"])
        .replace("{history}", _format_history(state.get("history")))
        .replace("{legal_ctx}", legal_ctx)
        .replace("{web_ctx}", web_ctx)
    )

    steps = list(state.get("reasoning_steps") or [])
    steps.append({
        "step": "generating_answer",
        "detail": "Generating answer from merged evidence",
    })
    if state.get("on_step"):
        state["on_step"](steps[-1])

    if state.get("streaming", False):
        # Streaming mode: store prompt so the SSE generator can call astream()
        return {"answer_prompt": prompt, "reasoning_steps": steps}

    # Non-streaming: run inference now and return the full answer. Citations
    # are computed in verify_answer_node — they need the groundedness verdict,
    # which doesn't exist until after this node runs.
    resp = await get_llm().ainvoke([HumanMessage(content=prompt)])
    meta = resp.response_metadata or {}
    return {
        "answer": resp.content,
        "answer_prompt": prompt,
        "reasoning_steps": steps,
        "model_provider": meta.get("model_provider", ""),
        "model_name": meta.get("model_name", ""),
    }


# ---------------------------------------------------------------------------
# Meta-verification node
# ---------------------------------------------------------------------------

async def verify_answer_node(state: JuryAIState) -> dict:
    from app.core.graph.verifier import verify_answer

    answer = state.get("answer") or ""
    merged = list(state.get("merged_evidence") or [])
    if merged:
        # Full mixed-domain evidence — _build_evidence_text applies its own
        # internal-preference policy when rendering the verifier prompt.
        evidence = merged
    else:
        evidence = list(state.get("legal_chunks") or [])

    verification = await verify_answer(answer, evidence)
    citations = derive_citations(verification, evidence)

    steps = list(state.get("reasoning_steps") or [])
    steps.append({
        "step": "verifying_answer",
        "detail": (
            f"Verdict: {verification.get('verdict', 'unsupported')} "
            f"(groundedness {verification.get('groundedness_score', 0.0):.2f})"
        ),
    })
    return {"verification": verification, "citations": citations, "reasoning_steps": steps}
