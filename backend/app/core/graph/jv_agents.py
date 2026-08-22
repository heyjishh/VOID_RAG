from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from typing import Annotated

import httpx
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool

from app.config.settings import settings
from app.core.graph.agent_bus import AgentBus, AgentMessage
from app.core.graph.nodes import legal_retrieve_node, web_search_node, evidence_merge_node
from app.core.graph.state import JuryAIState
from app.core.graph.evidence_merger import ensure_content_hashes
from app.core.llm.provider import get_juris_void_llm, corpus_composition, composition_tuning_clause
from app.core.prompts.jv_agents import (
    STATUTE_SYSTEM_PROMPT,
    CASE_ANALYST_SYSTEM_PROMPT,
    TOOL_LOOP_FALLBACK_SUMMARY_PROMPT,
    PLAN_RESEARCH_PROMPT,
    CHALLENGE_PROMPT,
    STATUTE_RESEARCHER_USER_PROMPT,
    CASE_ANALYST_USER_PROMPT,
)

logger = logging.getLogger("juryai.jv_agents")

SPICE_TIMEOUT = 15.0

AGENT_ROSTER = [
    {"id": "planner", "label": "Planner"},
    {"id": "statute_researcher", "label": "Statute Researcher"},
    {"id": "case_analyst", "label": "Case Law Analyst"},
    {"id": "web_verifier", "label": "Web Verifier"},
    {"id": "synthesizer", "label": "Synthesizer"},
]

AGENT_LABEL_BY_ID = {a["id"]: a["label"] for a in AGENT_ROSTER}

# Bounded reaction windows for cross-agent requests — real negotiation, but
# capped so a slow/missed exchange degrades gracefully instead of hanging.
_STATUTE_REQUEST_WINDOW_SECONDS = 5.0
_CASE_ANALYST_FINDING_WAIT_SECONDS = 10.0
_CASE_ANALYST_FOLLOWUP_WAIT_SECONDS = 6.0
_WEB_VERIFIER_FINDING_WAIT_SECONDS = 8.0

# Bounded ReAct loop — the LLM decides which search tool to call and with
# what query, observes the result, and decides whether to search again or
# stop. Capped so an agent that keeps finding "not enough" can't spiral.
_MAX_AGENT_TOOL_ITERATIONS = 4
_MAX_BROADEN_TOOL_ITERATIONS = 2


async def spice_sql(query: str) -> list[dict]:
    async with httpx.AsyncClient(timeout=SPICE_TIMEOUT) as client:
        resp = await client.post(
            # SpiceAI's /v1/sql body shape is {sql, parameters}, not {query} —
            # a wrong field name here fails with a 4xx that this function used
            # to swallow silently (returning [] looks identical to "zero
            # results", so every corpus search failed invisibly).
            f"{settings.SPICE_HTTP_URL}/v1/sql", json={"sql": query, "parameters": []},
        )
        if resp.status_code != 200:
            logger.warning("SpiceAI /v1/sql failed (%s): %s", resp.status_code, resp.text[:300])
            return []
        return resp.json() or []


async def spice_nql(question: str) -> list[dict]:
    try:
        async with httpx.AsyncClient(timeout=SPICE_TIMEOUT) as client:
            resp = await client.post(
                f"{settings.SPICE_HTTP_URL}/v1/nsql", json={"query": question},
            )
            if resp.status_code != 200:
                logger.debug("SpiceAI /v1/nsql failed (%s): %s", resp.status_code, resp.text[:300])
                return []
            return resp.json() or []
    except Exception as exc:
        logger.debug("SpiceAI NQL unavailable: %s", exc)
        return []


async def spice_text_search(question: str, dataset: str, limit: int = 10) -> list[dict]:
    safe_q = question.replace("'", "''")
    rows = await spice_sql(
        f"SELECT * FROM text_search({dataset}, '{safe_q}') LIMIT {limit}"
    )
    results = []
    for row in rows:
        t = (
            row.get("chunk_text") or row.get("text")
            or row.get("content") or row.get("body") or ""
        )
        if not t:
            continue
        results.append({
            "text": t,
            "source": row.get("source") or row.get("filename") or row.get("title") or "Void-Space",
            "page": int(row.get("page", 0)),
            "score": float(row.get("_score", row.get("score", row.get("rank", 0.5)))),
            "domain": "internal",
            "content_hash": hashlib.md5(t.encode()).hexdigest()[:12],
            "doc_id": row.get("doc_id") or row.get("file_hash"),
            "chunk_id": row.get("chunk_id") or row.get("id"),
        })
    return results


async def spice_jv_search(question: str, session_id: str | None = None) -> list[dict]:
    where = f" WHERE session_id = '{session_id}'" if session_id else ""
    rows = await spice_sql(
        f"SELECT * FROM juris_void_chunks{where} ORDER BY chunk_text LIMIT 50"
    )
    if not rows:
        return []
    q_lower = question.lower().split()
    results = []
    for row in rows:
        t = row.get("chunk_text", "")
        if not t:
            continue
        relevance = sum(1 for w in q_lower if w in t.lower()) / max(len(q_lower), 1)
        if relevance < 0.1 and len(results) >= 10:
            continue
        results.append({
            "text": t,
            "source": row.get("filename", "Uploaded document"),
            "page": int(row.get("page", 0)),
            "score": round(relevance, 4),
            "domain": "internal",
            "content_hash": hashlib.md5(t.encode()).hexdigest()[:12],
            "doc_id": row.get("file_hash"),
            "chunk_id": row.get("id"),
        })
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:15]




async def spice_full_search(
    question: str, on_step, session_id: str | None = None,
) -> list[dict]:
    on_step({
        "step": "spice_search_start",
        "detail": "Void-Space: searching main corpus + uploaded documents",
    })
    corpus_results, jv_results = await asyncio.gather(
        spice_text_search(question, settings.SPICE_DATASET),
        spice_jv_search(question, session_id),
        return_exceptions=True,
    )
    all_results = []
    if isinstance(corpus_results, list):
        all_results.extend(corpus_results)
        on_step({"step": "spice_corpus_done", "detail": f"Void-Space corpus: {len(corpus_results)} chunks"})
    if isinstance(jv_results, list) and jv_results:
        all_results.extend(jv_results)
        on_step({"step": "spice_uploads_done", "detail": f"Void-Space uploads: {len(jv_results)} chunks"})
    on_step({"step": "spice_search_done", "detail": f"Void-Space total: {len(all_results)} chunks"})
    return all_results


async def _run_tool_loop(
    llm, tools: list, system_prompt: str, user_prompt: str,
    max_iterations: int = _MAX_AGENT_TOOL_ITERATIONS,
) -> str:
    """Generic bounded ReAct loop: bind tools, let the LLM decide what to call
    and with what query, execute, feed the result back as a ToolMessage,
    repeat until the LLM stops calling tools or the iteration cap hits.
    Returns the LLM's final text. Tool execution errors are fed back to the
    LLM as a tool result (not raised) so a single bad call doesn't abort the
    whole loop — the LLM can see the error and try a different query."""
    bound = llm.bind_tools(tools)
    tools_by_name = {t.name: t for t in tools}
    messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
    for _ in range(max_iterations):
        resp = await bound.ainvoke(messages)
        messages.append(resp)
        if not resp.tool_calls:
            return resp.content or ""
        for tc in resp.tool_calls:
            tool_fn = tools_by_name.get(tc["name"])
            try:
                result_text = await tool_fn.ainvoke(tc["args"]) if tool_fn else f"Unknown tool: {tc['name']}"
            except Exception as exc:
                result_text = f"Tool error: {exc}"
            messages.append(ToolMessage(content=str(result_text), tool_call_id=tc["id"]))
    # Hit the cap without a final answer — one more call with tools removed
    # forces a text response instead of silently returning nothing.
    try:
        final = await llm.ainvoke(messages + [HumanMessage(content=TOOL_LOOP_FALLBACK_SUMMARY_PROMPT)])
        return final.content or ""
    except Exception as exc:
        logger.warning("Tool loop final summary failed: %s", exc)
        return ""


def _tag(items: list[dict], agent_id: str) -> list[dict]:
    return [{**item, "found_by": agent_id} for item in items]


async def _plan_research(question: str) -> dict:
    prompt = PLAN_RESEARCH_PROMPT.format(question=question)
    try:
        resp = await get_juris_void_llm().ainvoke([HumanMessage(content=prompt)])
        content = resp.content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        return json.loads(content)
    except Exception:
        return {
            "domain": "general",
            "sub_queries": [question],
            "key_statutes": [],
            "key_terms": question.split()[:5],
            "needs_case_law": True,
            "needs_web_check": True,
            "nql_query": question,
        }


async def _compose_challenge(domain: str, primary_source: str) -> str:
    """One short, bounded LLM call — used only in the specific scenario where
    web_verifier has something concrete worth flagging to the team, not on
    every request. Keeps the added communication cost small and predictable."""
    prompt = CHALLENGE_PROMPT.format(primary_source=primary_source, domain=domain)
    try:
        resp = await get_juris_void_llm().ainvoke([HumanMessage(content=prompt)])
        return resp.content.strip()
    except Exception:
        return f"No web corroboration found for '{primary_source}' — currency unconfirmed."


def _summarize_transcript(transcript: list[AgentMessage]) -> str:
    """Deterministic (no extra LLM call) digest of what agents actually
    asked/challenged each other about, beyond plain findings — this is what
    makes the pipeline's cross-agent negotiation visible to the end user."""
    notable = [m for m in transcript if m.type in ("request", "challenge")]
    if not notable:
        return "No cross-agent requests or challenges — all findings were accepted as-is."
    parts = []
    for m in notable:
        verb = "requested help from" if m.type == "request" else "challenged"
        target = "the team" if m.to_agent == "*" else AGENT_LABEL_BY_ID.get(m.to_agent, m.to_agent)
        source = AGENT_LABEL_BY_ID.get(m.from_agent, m.from_agent)
        parts.append(f"{source} {verb} {target}: {m.content}")
    return " · ".join(parts)


def _make_research_tools(state: JuryAIState, session_id: str | None, agent_id: str, collected: list[dict]) -> list:
    """Search tools bound per-call — they close over the current question's
    state/session so the LLM can issue its OWN queries (not a fixed fan-out of
    the original question), and every chunk any tool call surfaces is
    appended to `collected` so the agent's final evidence set reflects
    everything it actually retrieved across the whole tool-calling loop, not
    just whichever call happened to run last."""

    @tool
    async def search_corpus(query: Annotated[str, "Semantic search query for the internal legal corpus"]) -> str:
        """Hybrid semantic + keyword search over the internal legal corpus
        (Qdrant + Quickwit, reranked). Best general-purpose search — use this first."""
        state_copy = dict(state)
        state_copy["question"] = query
        state_copy["on_step"] = lambda s: None
        try:
            result = await legal_retrieve_node(state_copy)
        except Exception as exc:
            return f"Search failed: {exc}"
        chunks = _tag(ensure_content_hashes(result.get("legal_chunks", [])), agent_id)
        collected.extend(chunks)
        if not chunks:
            return "No results found for this query."
        return "\n\n".join(f"[{c.get('source', 'unknown')}] {(c.get('text') or '')[:500]}" for c in chunks[:5])

    @tool
    async def search_corpus_keyword(query: Annotated[str, "Exact phrase, section number, or statute name"]) -> str:
        """Keyword/BM25 text search — use for exact phrases, section numbers,
        or statute names that semantic search might blur past."""
        try:
            found = await spice_text_search(query, settings.SPICE_DATASET, limit=5)
        except Exception as exc:
            return f"Search failed: {exc}"
        found = _tag(ensure_content_hashes(found), agent_id)
        collected.extend(found)
        if not found:
            return "No results found for this query."
        return "\n\n".join(f"[{r.get('source', 'unknown')}] {(r.get('text') or '')[:500]}" for r in found)

    @tool
    async def search_uploaded_documents(query: Annotated[str, "Search query for the user's session-uploaded documents"]) -> str:
        """Search documents the current user uploaded into this session
        (separate from the shared corpus) — use when the question likely
        refers to something the user attached themselves."""
        try:
            found = await spice_jv_search(query, session_id)
        except Exception as exc:
            return f"Search failed: {exc}"
        found = _tag(ensure_content_hashes(found), agent_id)
        collected.extend(found)
        if not found:
            return "No uploaded documents matched this query."
        return "\n\n".join(f"[{r.get('source', 'unknown')}] {(r.get('text') or '')[:500]}" for r in found)

    @tool
    async def ask_database(question: Annotated[str, "A natural-language question to translate into a database query"]) -> str:
        """Ask a natural-language question that SpiceAI translates into SQL
        against the corpus database — use for aggregate/structured questions
        (counts, listings, filters) that plain text search handles poorly."""
        try:
            rows = await spice_nql(question)
        except Exception as exc:
            return f"Query failed: {exc}"
        if not rows:
            return "The database query returned no results."
        found = []
        for row in rows:
            t = row.get("chunk_text") or row.get("text") or row.get("content") or str(row)
            if not t:
                continue
            found.append({
                "text": t, "source": row.get("source") or "SpiceAI NQL",
                "page": int(row.get("page", 0)) if str(row.get("page", 0)).isdigit() else 0,
                "score": 0.8, "domain": "internal",
                "content_hash": hashlib.md5(t.encode()).hexdigest()[:12],
            })
        found = _tag(found, agent_id)
        collected.extend(found)
        if not found:
            return "The database query returned no usable text results."
        return "\n\n".join(f"[{r.get('source', 'unknown')}] {(r.get('text') or '')[:500]}" for r in found)

    return [search_corpus, search_corpus_keyword, search_uploaded_documents, ask_database]


async def _agent_statute_researcher(
    bus: AgentBus, plan: dict, question: str, session_id: str | None,
    state: JuryAIState, emit, results: dict,
) -> None:
    emit({
        "step": "agent_active", "agent": "statute_researcher",
        "detail": "Searching corpus adaptively via tool-calling",
    })
    collected: list[dict] = []
    tools = _make_research_tools(state, session_id, "statute_researcher", collected)
    sub_queries = plan.get("sub_queries", [question])[:3]
    user_prompt = STATUTE_RESEARCHER_USER_PROMPT.format(
        question=question,
        domain=plan.get("domain", "general"),
        angles="; ".join(sub_queries) or question,
    )
    try:
        await _run_tool_loop(get_juris_void_llm(), tools, STATUTE_SYSTEM_PROMPT, user_prompt)
    except Exception as exc:
        logger.warning("Statute researcher tool loop failed: %s", exc)

    seen: set[str] = set()
    statute_chunks: list[dict] = []
    for c in collected:
        h = c.get("content_hash")
        if h and h not in seen:
            seen.add(h)
            statute_chunks.append(c)

    results["statute_researcher"] = {"chunks": statute_chunks}
    emit({
        "step": "agent_done", "agent": "statute_researcher",
        "detail": f"{len(statute_chunks)} findings via {len(collected)} tool-call results",
    })
    bus.send(AgentMessage(
        from_agent="statute_researcher", to_agent="*", type="finding",
        content=f"Found {len(statute_chunks)} statute/corpus sources.",
        ref_id="statute_researcher",
    ))

    # Real, bounded negotiation: react once if case_analyst asks for a
    # broader search, then rebroadcast — never a second round, so this can't
    # spiral into a back-and-forth loop. The broadening itself is now one
    # more (shorter) tool-calling pass instead of a fixed key-terms fan-out.
    req = await bus.wait_for(
        "statute_researcher",
        lambda m: m.type == "request" and m.to_agent == "statute_researcher",
        timeout=_STATUTE_REQUEST_WINDOW_SECONDS,
    )
    if req is not None:
        emit({
            "step": "agent_active", "agent": "statute_researcher",
            "detail": f"Broadening search — {req.content}",
        })
        extra_collected: list[dict] = []
        extra_tools = _make_research_tools(state, session_id, "statute_researcher", extra_collected)
        try:
            await _run_tool_loop(
                get_juris_void_llm(), extra_tools, STATUTE_SYSTEM_PROMPT,
                f"The previous search was too narrow — {req.content}\n"
                f"Try different search terms for: {question}",
                max_iterations=_MAX_BROADEN_TOOL_ITERATIONS,
            )
        except Exception as exc:
            logger.warning("Statute researcher broaden loop failed: %s", exc)
        new_items = [c for c in ensure_content_hashes(extra_collected) if c.get("content_hash") not in seen]
        for c in new_items:
            seen.add(c.get("content_hash"))
        statute_chunks.extend(new_items)
        results["statute_researcher"] = {"chunks": statute_chunks}
        emit({
            "step": "agent_done", "agent": "statute_researcher",
            "detail": f"Broadened search — {len(new_items)} additional findings",
        })
        bus.send(AgentMessage(
            from_agent="statute_researcher", to_agent="case_analyst", type="finding",
            content=f"Broadened search added {len(new_items)} sources.",
            ref_id="statute_researcher",
        ))

    bus.send(AgentMessage(from_agent="statute_researcher", to_agent="*", type="done", content="done"))


async def _agent_case_analyst(
    bus: AgentBus, plan: dict, session_id: str | None, state: JuryAIState, emit, results: dict,
) -> None:
    """Only ever called when the supervisor (run_collaborative_pipeline) has
    already decided, from the plan, that this agent is worth spawning — the
    on/off decision lives there, not here."""
    await bus.wait_for(
        "case_analyst",
        lambda m: m.type == "finding" and m.from_agent == "statute_researcher",
        timeout=_CASE_ANALYST_FINDING_WAIT_SECONDS,
    )

    statute_chunks = results.get("statute_researcher", {}).get("chunks", [])
    emit({
        "step": "agent_active", "agent": "case_analyst",
        "detail": "Searching case law based on statute findings",
    })
    refs = list(dict.fromkeys(c.get("source", "") for c in statute_chunks[:5] if c.get("source")))
    seen: set[str] = {c.get("content_hash") for c in statute_chunks if c.get("content_hash")}
    collected: list[dict] = []
    tools = _make_research_tools(state, session_id, "case_analyst", collected)
    user_prompt = CASE_ANALYST_USER_PROMPT.format(
        domain=plan.get("domain", "general"),
        refs=", ".join(refs[:5]) or "none yet",
        key_statutes=", ".join(plan.get("key_statutes", [])[:3]) or "none",
    )
    try:
        await _run_tool_loop(get_juris_void_llm(), tools, CASE_ANALYST_SYSTEM_PROMPT, user_prompt)
    except Exception as exc:
        logger.warning("Case analyst tool loop failed: %s", exc)

    case_chunks = [c for c in collected if c.get("content_hash") and c["content_hash"] not in seen]
    for c in case_chunks:
        seen.add(c["content_hash"])

    # Real communication: thin results → ask statute_researcher to broaden,
    # wait once for the reply, retry the case-law search against whatever new
    # refs it surfaced. Kept as an explicit cross-agent request rather than
    # just looping harder internally — this is the negotiation that's meant
    # to be visible to the user, not just a retry.
    if len(case_chunks) < 2 and refs:
        bus.send(AgentMessage(
            from_agent="case_analyst", to_agent="statute_researcher", type="request",
            content=f"Only {len(case_chunks)} case-law hits for {', '.join(refs[:2])} — broaden the corpus search?",
        ))
        follow_up = await bus.wait_for(
            "case_analyst",
            lambda m: m.type == "finding" and m.from_agent == "statute_researcher",
            timeout=_CASE_ANALYST_FOLLOWUP_WAIT_SECONDS,
        )
        if follow_up is not None:
            broadened = results.get("statute_researcher", {}).get("chunks", [])
            new_refs = [
                r for r in dict.fromkeys(c.get("source", "") for c in broadened[:8] if c.get("source"))
                if r not in refs
            ][:2]
            if new_refs:
                retry_collected: list[dict] = []
                retry_tools = _make_research_tools(state, session_id, "case_analyst", retry_collected)
                try:
                    await _run_tool_loop(
                        get_juris_void_llm(), retry_tools, CASE_ANALYST_SYSTEM_PROMPT,
                        f"Search for case law interpreting: {', '.join(new_refs)}",
                        max_iterations=_MAX_BROADEN_TOOL_ITERATIONS,
                    )
                except Exception as exc:
                    logger.warning("Case analyst broaden loop failed: %s", exc)
                more = [c for c in ensure_content_hashes(retry_collected) if c.get("content_hash") not in seen]
                for c in more:
                    seen.add(c.get("content_hash"))
                case_chunks.extend(more)

    results["case_analyst"] = {"chunks": case_chunks}
    emit({
        "step": "agent_done", "agent": "case_analyst",
        "detail": f"{len(case_chunks)} case law sources from {len(refs)} statute refs",
    })
    bus.send(AgentMessage(
        from_agent="case_analyst", to_agent="*", type="finding",
        content=f"Found {len(case_chunks)} case-law sources.", ref_id="case_analyst",
    ))
    bus.send(AgentMessage(from_agent="case_analyst", to_agent="*", type="done", content="done"))


async def _agent_web_verifier(bus: AgentBus, plan: dict, state: JuryAIState, emit, results: dict) -> None:
    """Only ever called when the supervisor has already decided, from the
    plan and the use_web_search toggle, that this agent is worth spawning."""
    emit({
        "step": "agent_active", "agent": "web_verifier",
        "detail": "Verifying against current web sources",
    })
    web_state = dict(state)
    web_state["on_step"] = lambda s: emit({**s, "agent": "web_verifier"})
    web_evidence = []
    try:
        wr = await web_search_node(web_state)
        web_evidence = _tag(wr.get("web_evidence", []), "web_verifier")
    except Exception as exc:
        logger.warning("Web verification failed: %s", exc)

    results["web_verifier"] = {"chunks": web_evidence}
    emit({
        "step": "agent_done", "agent": "web_verifier",
        "detail": f"{len(web_evidence)} web sources" if web_evidence else "No results",
    })
    bus.send(AgentMessage(
        from_agent="web_verifier", to_agent="*", type="finding",
        content=f"Found {len(web_evidence)} web sources.", ref_id="web_verifier",
    ))

    # Real communication: cheap rule-based coverage check against what
    # statute_researcher already broadcast. Wait for its finding first —
    # these agents run concurrently, so `results` may not be populated yet.
    # Only escalates to an LLM call (via _compose_challenge) in the specific
    # case worth flagging, so this doesn't add cost on every request.
    await bus.wait_for(
        "web_verifier",
        lambda m: m.type == "finding" and m.from_agent == "statute_researcher",
        timeout=_WEB_VERIFIER_FINDING_WAIT_SECONDS,
    )
    statute_chunks = results.get("statute_researcher", {}).get("chunks", [])
    if statute_chunks and not web_evidence:
        challenge_text = await _compose_challenge(
            plan.get("domain", "this question"),
            statute_chunks[0].get("source", "the primary source"),
        )
        bus.send(AgentMessage(
            from_agent="web_verifier", to_agent="synthesizer", type="challenge",
            content=challenge_text,
        ))

    bus.send(AgentMessage(from_agent="web_verifier", to_agent="*", type="done", content="done"))


async def _agent_synthesizer(
    bus: AgentBus, results: dict, state: JuryAIState, emit,
) -> tuple[list[dict], dict, str]:
    emit({"step": "agent_active", "agent": "synthesizer", "detail": "Merging all agent findings"})
    all_legal = results.get("statute_researcher", {}).get("chunks", []) + results.get("case_analyst", {}).get("chunks", [])
    web_evidence = results.get("web_verifier", {}).get("chunks", [])
    merge_state = dict(state)
    merge_state["legal_chunks"] = all_legal
    merge_state["web_evidence"] = web_evidence
    merged = (await evidence_merge_node(merge_state)).get("merged_evidence", [])

    provenance = {
        item.get("content_hash", ""): item.get("found_by")
        for item in all_legal + web_evidence if item.get("found_by")
    }
    for item in merged:
        h = item.get("content_hash", "")
        if h in provenance and "found_by" not in item:
            item["found_by"] = provenance[h]

    composition = corpus_composition(merged)
    composition_clause = composition_tuning_clause(composition)
    if composition_clause:
        state["composition_clause"] = composition_clause

    coordination_summary = _summarize_transcript(bus.transcript)

    emit({
        "step": "agent_done", "agent": "synthesizer",
        "detail": f"{len(merged)} items from {len(all_legal)} legal + {len(web_evidence)} web",
        "corpus_composition": composition,
        "coordination_summary": coordination_summary,
    })
    bus.send(AgentMessage(from_agent="synthesizer", to_agent="*", type="done", content="done"))
    return merged, composition, coordination_summary


async def run_collaborative_pipeline(
    question: str,
    state: JuryAIState,
    queue: asyncio.Queue,
    session_id: str | None = None,
) -> dict:
    """The orchestrator is a pure supervisor, not a fourth worker: it plans,
    decides — from the plan — which sub-agents are actually worth spawning,
    and only then hands off. statute_researcher, case_analyst, and
    web_verifier run as concurrent tasks talking over an AgentBus (findings,
    requests, challenges) rather than a fixed sequence of awaited calls —
    case_analyst can ask statute_researcher to broaden its search mid-flight,
    and web_verifier can challenge a claim that has no web corroboration.
    synthesizer runs last, since it genuinely needs everyone else's final
    output, and folds the negotiation itself into a coordination summary."""
    emit = queue.put_nowait
    emit({"step": "agent_roster", "agents": AGENT_ROSTER})

    emit({
        "step": "agent_active", "agent": "planner",
        "detail": "Analyzing question and planning research strategy",
    })
    plan = await _plan_research(question)
    emit({
        "step": "agent_done", "agent": "planner",
        "detail": f"Domain: {plan.get('domain')} · {len(plan.get('sub_queries', []))} sub-queries",
        "plan": plan,
    })

    def on_message(msg_dict: dict) -> None:
        emit({"step": "agent_message", **msg_dict})

    bus = AgentBus(
        ["statute_researcher", "case_analyst", "web_verifier", "synthesizer"],
        on_message=on_message,
    )
    results: dict[str, dict] = {}

    async def _guarded(coro, agent_id: str):
        try:
            await coro
        except Exception as exc:
            logger.exception("Agent %s crashed", agent_id)
            emit({"step": "agent_done", "agent": agent_id, "detail": f"Failed: {exc}"})
            bus.send(AgentMessage(from_agent=agent_id, to_agent="*", type="done", content="failed"))

    def _skip(agent_id: str, detail: str) -> None:
        """Supervisor decision to NOT spawn an agent at all — its coroutine
        is never created, unlike a spawned agent that decides to skip its
        own work internally."""
        emit({"step": "agent_done", "agent": agent_id, "detail": detail})
        bus.send(AgentMessage(from_agent=agent_id, to_agent="*", type="done", content="not spawned"))

    # statute_researcher always runs — the plan has no signal for skipping
    # primary evidence gathering. case_analyst and web_verifier are spawned
    # on demand, only when the plan (and, for web_verifier, the user's own
    # web-search toggle) actually calls for them.
    tasks = [
        _guarded(_agent_statute_researcher(bus, plan, question, session_id, state, emit, results), "statute_researcher"),
    ]

    if plan.get("needs_case_law"):
        tasks.append(_guarded(_agent_case_analyst(bus, plan, session_id, state, emit, results), "case_analyst"))
    else:
        _skip("case_analyst", "Not spawned — plan marked case law as unnecessary")

    if plan.get("needs_web_check") and state.get("use_web_search"):
        tasks.append(_guarded(_agent_web_verifier(bus, plan, state, emit, results), "web_verifier"))
    else:
        reason = "web search disabled" if not state.get("use_web_search") else "plan marked it as unnecessary"
        _skip("web_verifier", f"Not spawned — {reason}")

    await asyncio.gather(*tasks)

    merged, composition, coordination_summary = await _agent_synthesizer(bus, results, state, emit)

    return {
        "legal_chunks": results.get("statute_researcher", {}).get("chunks", []) + results.get("case_analyst", {}).get("chunks", []),
        "web_evidence": results.get("web_verifier", {}).get("chunks", []),
        "merged_evidence": merged,
        "plan": plan,
        "corpus_composition": composition,
        "coordination_summary": coordination_summary,
    }
