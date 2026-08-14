from __future__ import annotations
import asyncio
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

    # Interact mode is scoped strictly to the user's own uploaded documents —
    # never fan out to the global corpus or web search, regardless of
    # use_web_search, so the answer can't be grounded in another user's data
    # or the wider web.
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
        # Accumulate reasoning_steps from all parallel tasks
        steps = r.get("reasoning_steps", [])
        merged["reasoning_steps"].extend(steps)
        # Merge all other keys
        for k, v in r.items():
            if k != "reasoning_steps":
                merged[k] = v

    return merged


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
