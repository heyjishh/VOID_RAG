from __future__ import annotations
from urllib.parse import urlparse
from langchain_core.messages import HumanMessage, SystemMessage
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
Each evidence item is prefixed with a fixed bracketed number, e.g. [1], [2]. Cite
your sources by placing that exact number inline immediately after the claim it
supports — like [1] or [2] — combining them as [1][3] when a claim draws on more
than one. Use only the numbers shown; never renumber, merge, or invent them.
Quote pivotal statutory or holding language in double-quotes. If the context is
insufficient, say so plainly — never hallucinate. If the evidence only covers a
predecessor or superseded statute/section rather than the one actually asked
about, say so explicitly instead of presenting it as directly on-point.

Style:
- When analyzing a specific case or precedent, break it down as labeled bullets
  (Court:, Citation:, Facts:, Held:, Followed:, Applied by: — use only the labels
  that apply, skip any you have no evidence for).
- When an answer works through several distinct errors, grounds, or issues,
  classify each by its own nature (e.g. jurisdictional / factual / question of
  law) rather than listing them as one undifferentiated set.
- For a long or multi-part answer, close with a short (one- or two-sentence)
  synthesis that ties the parts together.
- When the answer naturally invites a next step, end with a single relevant
  follow-up — either a next-step question, or, if answering precisely depends on
  a fact not in the context (a date, an amount, a missing document), ask for
  that fact instead. Only when it genuinely helps, not every time.
- When the answer lays out multiple alternative options or remedies, present them
  as a markdown comparison table.

Output format:
{format_instructions}
{as_of_clause}
Conversation so far (for follow-up context only — do NOT treat as evidence):
{history}

Question: {question}

Legal Context:
{legal_ctx}

Web Context:
{web_ctx}

Answer:"""


_FORMAT_INSTRUCTIONS = {
    "CREAC": (
        "Structure the answer with these exact markdown section headers, in order:\n"
        "## Conclusion\nA short, direct answer to the question (2-4 sentences).\n"
        "## Rule\nThe governing statutes, sections, and legal tests that apply.\n"
        "## Explanation\nCase law elaborating the rule (use the labeled-bullet case style above where applicable).\n"
        "## Application\nApply the rule to the facts in the question.\n"
        "## Conclusion\nRestate the answer in light of the analysis above."
    ),
    "IRAC": (
        "Structure the answer with these exact markdown section headers, in order:\n"
        "## Issue\n## Rule\n## Application\n## Conclusion"
    ),
    "BRIEF": (
        "Write a concise legal memo in plain prose paragraphs. Do NOT use CREAC or IRAC "
        "section headers — keep it tight and direct."
    ),
}


def answer_format_instructions(output_format: str) -> str:
    return _FORMAT_INSTRUCTIONS.get((output_format or "CREAC").upper(), _FORMAT_INSTRUCTIONS["CREAC"])


_AS_OF_CLAUSE = (
    "\nThe user is asking as of {date}. Answer strictly using the law as it stood on that "
    "date — apply the version of each statute/section in force then. If a provision was later "
    "amended, repealed, or renumbered (e.g. IPC 1860 -> Bharatiya Nyaya Sanhita 2023, CrPC 1973 "
    "-> Bharatiya Nagarik Suraksha Sanhita 2023, Evidence Act 1872 -> Bharatiya Sakshya Adhiniyam "
    "2023, all effective 1 July 2024), use the version applicable on {date} and state which one "
    "you used.\n"
)


def as_of_clause(as_of_date: str | None) -> str:
    return _AS_OF_CLAUSE.format(date=as_of_date) if as_of_date else ""


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
        intent = state.get("intent", "unknown")
        chunks = hybrid_search(
            state["question"], top_k=settings.TOP_K_RETRIEVE, qdrant=_qdrant, quickwit=_quickwit,
            intent=intent, source_filter=state.get("source_filter"),
        )
        return get_reranker().rerank(
            state["question"], chunks, top_k=settings.TOP_K_FINAL, as_of_date=state.get("as_of_date"),
        )

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


async def interact_retrieve_node(state: JuryAIState) -> dict:
    """Scoped variant of legal_retrieve_node for the Interact feature.

    Searches ONLY the current session's uploaded documents (see
    app.core.retrieval.session_store) — never the global Qdrant/Quickwit
    corpus — so one user's uploads can never surface in another user's chat.
    Reuses the same reranker as legal_retrieve_node so scores/citations stay
    on the same scale as the ask-mode pipeline.
    """
    import asyncio
    from app.core.retrieval import session_store

    steps = list(state.get("reasoning_steps") or [])
    steps.append({
        "step": "internal_retrieval_start",
        "detail": "Searching your uploaded documents",
    })
    if state.get("on_step"):
        state["on_step"](steps[-1])

    session_id = state.get("session_id") or ""

    def _sync_retrieve():
        chunks = session_store.search(session_id, state["question"], top_k=20)
        return get_reranker().rerank(state["question"], chunks, top_k=5, as_of_date=state.get("as_of_date"))

    reranked = ensure_content_hashes(await asyncio.to_thread(_sync_retrieve))

    files = list(dict.fromkeys(c.get("source", "unknown") for c in reranked))
    detail = (
        f"{len(reranked)} chunks retrieved from your uploads: {', '.join(files)}"
        if files else "No matching content found in your uploaded documents"
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

    results = await web_search(
        state["question"],
        max_results=settings.WEB_SEARCH_MAX_RESULTS,
        on_step=state.get("on_step"),
    )

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
    return {"web_evidence": results, "web_results": results, "reasoning_steps": steps}


# ---------------------------------------------------------------------------
# Evidence merge node (streaming workflow only)
# ---------------------------------------------------------------------------

async def evidence_merge_node(state: JuryAIState) -> dict:
    from app.config.settings import settings as _settings
    from app.core.graph.evidence_merger import merge_evidence

    legal_chunks = list(state.get("legal_chunks") or [])
    web_evidence = list(state.get("web_evidence") or [])

    merged = merge_evidence(legal_chunks, web_evidence, _settings)

    internal_count = sum(1 for e in merged if e.get("domain") == "internal")
    web_count = sum(1 for e in merged if e.get("domain") == "web")

    if state.get("mode") == "interact":
        # merge_evidence always tags legal_chunks-derived items "internal",
        # which doesn't distinguish session_store (never-ingested-to-S3)
        # chunks from the shared Qdrant corpus — the frontend's document
        # viewer 404s trying to fetch a session upload from S3. Relabel only
        # internal items; web items keep their real "web" domain.
        merged = [
            {**item, "domain": "session"} if item.get("domain") == "internal" else item
            for item in merged
        ]

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
# Query analysis node (v1 parity: prompt quality scoring)
# ---------------------------------------------------------------------------

_QUERY_ANALYSIS_PROMPT = """You are a legal research strategist. Analyze the user's question and provide:

1. A quality score from 1-10 based on:
   - Jurisdiction clarity (India, specific state, court level)
   - Practice area specificity (direct tax, GST, constitutional, etc.)
   - Fact pattern detail (order type, section, assessment year, parties)
   - Legal issue clarity (limitation, jurisdiction, procedure, merits)

2. Specific gaps identified (what's missing that would improve results) — name the
   exact missing element where possible: the specific statute Article/Section number,
   the nature of the claim, or the accrual/computation point in question. If a selected
   practice area or source filter looks inconsistent with what the question is actually
   about, call that out as a gap too. If the question cites a statute since superseded
   by India's 2023 recodification (IPC 1860 -> Bharatiya Nyaya Sanhita 2023, CrPC 1973
   -> Bharatiya Nagarik Suraksha Sanhita 2023, Indian Evidence Act 1872 -> Bharatiya
   Sakshya Adhiniyam 2023), flag that as a gap and name the current equivalent section.
   Since old and new codes can both apply depending on the offense date (1 July 2024
   cutover), also flag missing enactment-year clarity when it would change which code
   governs.

3. A suggested rewrite that addresses the gaps

4. A one-sentence improvement_reason that explains WHY the rewrite is better — reference
   the specific legal elements it adds (article/section numbers, claim type, etc.), not a
   generic "clarified the question" statement.

Return ONLY a JSON object:
{
  "score": 5,
  "gaps": ["missing jurisdiction", "no specific statute cited", "no fact pattern"],
  "suggested_rewrite": "Improved question incorporating the missing elements",
  "improvement_reason": "Pins Article 65 vs Article 64 and the Section 18 accrual trigger, which the original question left unspecified"
}"""


async def query_analysis_node(state: JuryAIState) -> dict:
    """Analyze query quality and suggest improvements (v1 parity)."""
    question = state["question"]
    
    from app.core.graph.workflow import emit_progress
    emit_progress(state, "query_analysis")
    
    steps = list(state.get("reasoning_steps") or [])
    steps.append({
        "step": "query_analysis",
        "detail": "Analyzing question quality and identifying gaps",
    })
    if state.get("on_step"):
        state["on_step"](steps[-1])
    
    prompt = f"{_QUERY_ANALYSIS_PROMPT}\n\nQuestion: {question}"
    
    try:
        resp = await get_llm().ainvoke([
            SystemMessage(content="You are a legal research strategist. Return only valid JSON."),
            HumanMessage(content=prompt)
        ])
        content = resp.content.strip()
        
        # Extract JSON from response
        import json
        start = content.find('{')
        end = content.rfind('}') + 1
        if start >= 0 and end > start:
            analysis = json.loads(content[start:end])
        else:
            raise ValueError("No JSON found in response")
        
        # Ensure required fields
        analysis.setdefault("score", 5)
        analysis.setdefault("gaps", [])
        analysis.setdefault("suggested_rewrite", question)
        analysis.setdefault("improvement_reason", "Analysis complete")
        
    except Exception as e:
        # Fallback analysis
        analysis = {
            "score": 5,
            "gaps": ["Could not analyze - using default"],
            "suggested_rewrite": question,
            "improvement_reason": f"Analysis failed: {str(e)}"
        }
    
    steps.append({
        "step": "query_analysis_done",
        "detail": f"Query score: {analysis['score']}/10. Gaps: {', '.join(analysis['gaps']) if analysis['gaps'] else 'none'}",
        "score": analysis["score"],
        "gaps": analysis["gaps"],
        "suggested_rewrite": analysis["suggested_rewrite"],
    })
    if state.get("on_step"):
        state["on_step"](steps[-1])
    
    return {
        "query_analysis": analysis,
        "reasoning_steps": steps,
    }


# ---------------------------------------------------------------------------
# Prompt improvement node (v1 parity: suggested rewrite)
# ---------------------------------------------------------------------------

async def prompt_improvement_node(state: JuryAIState) -> dict:
    """Apply suggested rewrite if it significantly improves the query."""
    analysis = state.get("query_analysis", {})
    suggested = analysis.get("suggested_rewrite", "")
    score = analysis.get("score", 5)
    original = state["question"]
    
    steps = list(state.get("reasoning_steps") or [])
    
    # Keep original question for retrieval/answer parity with v1; store rewrite separately
    if score < 7 and suggested and suggested != original:
        steps.append({
            "step": "prompt_improved",
            "detail": f"Suggested rewrite available (score: {score}/10)",
            "original": original,
            "improved": suggested,
        })
        if state.get("on_step"):
            state["on_step"](steps[-1])
        return {
            "original_question": original,
            "improved_question": suggested,
            "query_analysis": analysis,
            "reasoning_steps": steps,
        }
    
    return {"reasoning_steps": steps}


# ---------------------------------------------------------------------------
# Answer generation node
# ---------------------------------------------------------------------------

async def generate_answer_node(state: JuryAIState) -> dict:
    merged = list(state.get("merged_evidence") or [])

    if merged:
        legal_ctx = "\n\n".join(
            f"[{i}] {c['source']} p.{c['page']}\n{c['text']}"
            for i, c in enumerate(merged, 1)
            if c.get("domain") == "internal" and c.get("text") and c.get("source")
        ) or "(none)"
        web_ctx = "\n\n".join(
            f"[{i}] {r.get('title', '')} ({r.get('url', '')})\n{r.get('content', '')}"
            for i, r in enumerate(merged, 1)
            if r.get("domain") == "web"
        ) or "(none)"
    else:
        legal_ctx = "\n\n".join(
            f"[{i}] {c['source']} p.{c['page']}\n{c['text']}"
            for i, c in enumerate(state.get("legal_chunks") or [], 1)
        ) or "(none)"
        web_ctx = "\n\n".join(
            f"{r['title']} ({r['url']})\n{r['content']}"
            for r in state.get("web_results") or []
        ) or "(none)"

    prompt = (
        _ANSWER_PROMPT
        .replace("{question}", state["question"])
        .replace("{history}", _format_history(state.get("history")))
        .replace("{legal_ctx}", legal_ctx)
        .replace("{web_ctx}", web_ctx)
        .replace("{format_instructions}", answer_format_instructions(state.get("output_format", "CREAC")))
        .replace("{as_of_clause}", as_of_clause(state.get("as_of_date")))
    )

    steps = list(state.get("reasoning_steps") or [])
    steps.append({
        "step": "generating_answer",
        "detail": "Generating answer from merged evidence",
    })
    if state.get("on_step"):
        state["on_step"](steps[-1])

    if state.get("streaming", False):
        return {"answer_prompt": prompt, "reasoning_steps": steps}

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
# Devil's Advocate — standalone counterargument pass over an existing answer
# ---------------------------------------------------------------------------

_DEVILS_ADVOCATE_PROMPT = """You are opposing counsel. Given the question, the answer below, and the
evidence it relies on, construct the strongest counterargument against that answer — the argument the
other side would make. Use only the evidence provided; do not invent new authority. Cite evidence the
same way the answer does, using its existing [N] numbers. If the evidence genuinely leaves no room for
a counterargument, say so plainly instead of manufacturing one.

Question: {question}

Answer being challenged:
{answer}

Evidence:
{evidence}

Counterargument:"""


async def generate_devils_advocate(question: str, answer: str, evidence: list[dict]) -> str:
    from app.core.graph.verifier import _build_evidence_text
    prompt = _DEVILS_ADVOCATE_PROMPT.format(
        question=question, answer=answer, evidence=_build_evidence_text(evidence)
    )
    resp = await get_llm().ainvoke([HumanMessage(content=prompt)])
    return resp.content


# ---------------------------------------------------------------------------
# Meta-verification node
# ---------------------------------------------------------------------------

async def verify_answer_node(state: JuryAIState) -> dict:
    from app.core.graph.verifier import verify_answer as _verify_answer

    answer = state.get("answer") or ""
    merged = list(state.get("merged_evidence") or [])
    if merged:
        evidence = merged
    else:
        evidence = list(state.get("legal_chunks") or [])

    verification = await _verify_answer(answer, evidence)
    citations = derive_citations(verification, evidence, answer)

    # Optional claim-level verification (legal-specific)
    claim_verification = None
    if settings.CLAIM_VERIFICATION_ENABLED and evidence:
        try:
            from app.core.retrieval.claim_verifier import ClaimVerifier
            cv = ClaimVerifier()
            av = await cv.verify_answer(answer, evidence)
            claim_verification = {
                "overall_verdict": av.overall_verdict.value,
                "overall_confidence": av.overall_confidence,
                "groundedness_score": av.groundedness_score,
                "summary": av.summary,
                "unsupported_claims": av.unsupported_claims,
                "claim_verifications": [
                    {
                        "claim": v.claim.text,
                        "verdict": v.verdict.value,
                        "confidence": v.confidence,
                        "supporting_evidence": v.supporting_evidence,
                        "refuting_evidence": v.refuting_evidence,
                        "explanation": v.explanation,
                    }
                    for v in av.claim_verifications
                ],
            }
            # Merge: use claim verifier's groundedness if higher
            if claim_verification["groundedness_score"] > verification.get("groundedness_score", 0.0):
                verification = dict(verification)
                verification["groundedness_score"] = claim_verification["groundedness_score"]
                verification["verdict"] = claim_verification["overall_verdict"]
                verification["summary"] = claim_verification["summary"]
            # Merge unsupported claims
            existing_unsupported = set(verification.get("unsupported_claims", []))
            for uc in claim_verification.get("unsupported_claims", []):
                if uc not in existing_unsupported:
                    verification.setdefault("unsupported_claims", []).append(uc)
            verification["claim_verification"] = claim_verification
        except Exception:
            pass

    steps = list(state.get("reasoning_steps") or [])
    steps.append({
        "step": "verifying_answer",
        "detail": (
            f"Verdict: {verification.get('verdict', 'unsupported')} "
            f"(groundedness {verification.get('groundedness_score', 0.0):.2f})"
        ),
    })
    return {"verification": verification, "citations": citations, "reasoning_steps": steps}
