from __future__ import annotations
import asyncio
import uuid
from functools import lru_cache
from langgraph.graph import StateGraph, END
from app.core.graph.state import JuryAIState
from app.core.graph.intent import classify_intent
from app.core.graph.nodes import (
    legal_retrieve_node,
    interact_retrieve_node,
    web_search_node,
    generate_answer_node,
    evidence_merge_node,
    verify_answer_node,
    query_analysis_node,
    prompt_improvement_node,
)


# ---------------------------------------------------------------------------
# Shared retrieve node (used by both workflows)
# ---------------------------------------------------------------------------

async def route_and_retrieve(state: JuryAIState) -> dict:
    """Run legal retrieval and optionally web search in parallel.

    Web search is triggered only when ``state["use_web_search"]`` is True.
    Both tasks emit reasoning_steps independently; they are concatenated in
    deterministic order (internal first, web second).
    """
    intent = classify_intent(state["question"])
    interact_mode = state.get("mode") == "interact"

    tasks = [interact_retrieve_node(state) if interact_mode else legal_retrieve_node(state)]
    if not interact_mode and state.get("use_web_search", False):
        tasks.append(web_search_node(state))

    results = await asyncio.gather(*tasks)

    merged: dict = {
        "intent": intent,
        "legal_chunks": [],
        "web_evidence": [],
        "web_results": [],
        "reasoning_steps": [],
    }
    for r in results:
        steps = r.get("reasoning_steps", [])
        merged["reasoning_steps"].extend(steps)
        for k, v in r.items():
            if k != "reasoning_steps":
                merged[k] = v

    return merged


# ---------------------------------------------------------------------------
# Progress tracking utilities
# ---------------------------------------------------------------------------

PROGRESS_STEPS = [
    ("query_analysis", "Analyzing your question..."),
    ("internal_retrieval", "Searching internal legal corpus..."),
    ("web_search", "Searching web for current legal information..."),
    ("evidence_merge", "Ranking evidence by authority..."),
    ("generating_answer", "Generating answer from merged evidence..."),
    ("verifying_answer", "Verifying citations and groundedness..."),
]

def emit_progress(state: JuryAIState, step_id: str, detail: str = ""):
    """Emit a progress event if on_step callback is registered."""
    message = next((msg for sid, msg in PROGRESS_STEPS if sid == step_id), detail)
    if state.get("on_step"):
        state["on_step"]({
            "step": step_id,
            "detail": detail or message,
            "message": message,
        })


# ---------------------------------------------------------------------------
# Legacy 2-node workflow — used by the POST /chat endpoint (unchanged)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def get_workflow():
    """retrieve → merge → answer → verify (mirrors the streaming graph's
    merge step so verify_answer_node always sees mixed-domain evidence)."""
    graph = StateGraph(JuryAIState)
    graph.add_node("retrieve", route_and_retrieve)
    graph.add_node("merge", evidence_merge_node)
    graph.add_node("answer", generate_answer_node)
    graph.add_node("verify", verify_answer_node)
    graph.set_entry_point("retrieve")
    graph.add_edge("retrieve", "merge")
    graph.add_edge("merge", "answer")
    graph.add_edge("answer", "verify")
    graph.add_edge("verify", END)
    return graph.compile()


# ---------------------------------------------------------------------------
# Streaming 3-node workflow — used by the SSE /chat/stream endpoint
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def get_streaming_workflow():
    """retrieve → merge → answer (3-node graph for the SSE streaming endpoint)."""
    graph = StateGraph(JuryAIState)
    graph.add_node("retrieve", route_and_retrieve)
    graph.add_node("merge", evidence_merge_node)
    graph.add_node("answer", generate_answer_node)
    graph.set_entry_point("retrieve")
    graph.add_edge("retrieve", "merge")
    graph.add_edge("merge", "answer")
    graph.add_edge("answer", END)
    return graph.compile()


# ---------------------------------------------------------------------------
# Enhanced workflow with progress tracking and query analysis
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def get_enhanced_workflow():
    """
    Enhanced workflow with:
    - Run ID generation
    - Query analysis & prompt improvement
    - Progress tracking at each stage
    - Structured answer generation (CREAC/IRAC/Brief)
    """
    graph = StateGraph(JuryAIState)
    
    graph.add_node("init", init_run_node)
    graph.add_node("query_analysis", query_analysis_node)
    graph.add_node("prompt_improvement", prompt_improvement_node)
    graph.add_node("retrieve", route_and_retrieve_with_progress)
    graph.add_node("merge", evidence_merge_node)
    graph.add_node("answer", generate_structured_answer_node)
    graph.add_node("verify", verify_answer_node)
    
    graph.set_entry_point("init")
    graph.add_edge("init", "query_analysis")
    graph.add_edge("query_analysis", "prompt_improvement")
    graph.add_edge("prompt_improvement", "retrieve")
    graph.add_edge("retrieve", "merge")
    graph.add_edge("merge", "answer")
    graph.add_edge("answer", "verify")
    graph.add_edge("verify", END)
    
    return graph.compile()


async def init_run_node(state: JuryAIState) -> dict:
    """Initialize run with unique ID and extract output format preference."""
    run_id = str(uuid.uuid4())[:8]
    output_format = state.get("output_format", "CREAC").upper()
    if output_format not in ("CREAC", "IRAC", "BRIEF"):
        output_format = "CREAC"
    
    emit_progress(state, "init", "Initializing research run...")
    
    return {
        "run_id": run_id,
        "output_format": output_format,
        "reasoning_steps": [{"step": "init", "detail": f"Run {run_id} started", "run_id": run_id}],
    }


async def route_and_retrieve_with_progress(state: JuryAIState) -> dict:
    """Wrapper around route_and_retrieve with progress emissions."""
    emit_progress(state, "internal_retrieval")
    result = await route_and_retrieve(state)
    emit_progress(state, "web_search" if state.get("use_web_search") else "evidence_merge")
    return result


async def generate_structured_answer_node(state: JuryAIState) -> dict:
    """Generate answer using the same prompt/style as the legacy v1 endpoint."""
    from app.core.graph.nodes import _format_history, answer_format_instructions
    from app.core.prompts.answer import ANSWER_PROMPT
    from langchain_core.messages import HumanMessage
    from app.core.llm.provider import get_llm
    
    merged = list(state.get("merged_evidence") or [])
    run_id = state.get("run_id", "")
    output_format = state.get("output_format", "CREAC")
    
    emit_progress(state, "generating_answer")
    
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
            f"{r['title']} ({r['url']})\n{r.get('content', '')}"
            for r in state.get("web_results") or []
        ) or "(none)"
    
    prompt = (
        ANSWER_PROMPT
        .replace("{history}", _format_history(state.get("history")))
        .replace("{question}", state["question"])
        .replace("{legal_ctx}", legal_ctx)
        .replace("{web_ctx}", web_ctx)
        .replace("{format_instructions}", answer_format_instructions(output_format))
    )
    
    steps = list(state.get("reasoning_steps") or [])
    steps.append({
        "step": "generating_answer",
        "detail": "Generating answer",
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
        "run_id": run_id,
        "output_format": output_format,
    }


# Export the enhanced workflow getter
__all__ = [
    "get_workflow",
    "get_streaming_workflow", 
    "get_enhanced_workflow",
    "emit_progress",
    "PROGRESS_STEPS",
]
