import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.core.graph import jv_agents


def _fixed_plan(**overrides):
    plan = {
        "domain": "criminal law",
        "sub_queries": ["q1", "q2"],
        "key_statutes": ["Section 100"],
        "key_terms": ["punishment", "offence"],
        "needs_case_law": True,
        "needs_web_check": True,
        "nql_query": "q",
    }
    plan.update(overrides)
    return plan


def _chunk(text="Some statute text", source="Section 100", content_hash="fixed-hash"):
    return {
        "text": text, "source": source, "page": 1, "score": 0.5,
        "domain": "internal", "content_hash": content_hash,
    }


def _spice_text_search_stub(case_law_hits=2):
    """Distinguishes statute_researcher's sub-query searches from
    case_analyst's "case law interpreting X" / "judicial interpretation X"
    queries, so each test can control case-law thinness independently of
    whether statute_researcher itself finds anything."""
    async def _fake(question, dataset, limit=10):
        if question.startswith("case law interpreting") or question.startswith("judicial interpretation"):
            return [_chunk(text=f"Case {i}", content_hash=f"case-hash-{i}") for i in range(case_law_hits)]
        return [_chunk(content_hash="statute-hash")]
    return _fake


async def _fake_tool_loop(llm, tools, system_prompt, user_prompt, max_iterations=4):
    """Stands in for the real LLM-driven ReAct loop: instead of letting a
    model decide what to search for, deterministically calls the REAL
    search_corpus_keyword tool (which still goes through the mocked
    spice_text_search below) with a query that matches what
    _spice_text_search_stub distinguishes on. This keeps the tests' actual
    subject — agent negotiation over the AgentBus — under test, while the
    "which query text was used" concern (an LLM's actual choice in
    production) is deliberately out of scope here."""
    tools_by_name = {t.name: t for t in tools}
    query = "case law interpreting Section 100" if "case law" in system_prompt.lower() else "q1"
    await tools_by_name["search_corpus_keyword"].ainvoke({"query": query})
    return "stub summary"


@pytest.fixture
def base_mocks():
    """Patches every I/O boundary of the collaborative pipeline so tests only
    exercise the agent-communication logic itself, never real network/LLM
    calls. _run_tool_loop is the boundary between "agent orchestration" and
    "an LLM deciding what to search for" — mocked deterministically via
    _fake_tool_loop above rather than scripting a fake chat model."""
    with patch.object(jv_agents, "_plan_research", AsyncMock(return_value=_fixed_plan())), \
         patch.object(jv_agents, "_run_tool_loop", AsyncMock(side_effect=_fake_tool_loop)), \
         patch.object(jv_agents, "spice_nql", AsyncMock(return_value=[])), \
         patch.object(jv_agents, "legal_retrieve_node", AsyncMock(return_value={"legal_chunks": []})), \
         patch.object(jv_agents, "spice_jv_search", AsyncMock(return_value=[])), \
         patch.object(jv_agents, "evidence_merge_node", AsyncMock(return_value={"merged_evidence": []})), \
         patch.object(jv_agents, "_compose_challenge", AsyncMock(return_value="No web corroboration for Section 100.")):
        yield


@pytest.mark.asyncio
async def test_case_analyst_requests_broader_search_when_case_law_is_thin(base_mocks):
    """Case-law search comes back with 0 hits — case_analyst must treat that
    as thin and negotiate with statute_researcher rather than silently
    accepting it."""
    with patch.object(jv_agents, "spice_text_search", AsyncMock(side_effect=_spice_text_search_stub(case_law_hits=0))), \
         patch.object(jv_agents, "web_search_node", AsyncMock(return_value={"web_evidence": []})):
        queue: asyncio.Queue = asyncio.Queue()
        result = await jv_agents.run_collaborative_pipeline("What is Section 100?", {"use_web_search": True}, queue)

    requests = [m for m in result["coordination_summary"].split(" · ") if "requested help from" in m]
    assert requests, f"expected a request in the coordination summary, got: {result['coordination_summary']}"
    assert "Case Law Analyst" in requests[0]
    assert "Statute Researcher" in requests[0]


@pytest.mark.asyncio
async def test_web_verifier_challenges_when_corpus_has_no_web_corroboration(base_mocks):
    """statute_researcher finds something, web_verifier finds nothing — that
    gap must surface as a challenge to synthesizer, not be silently merged.
    Case-law search returns enough hits that case_analyst does NOT also
    negotiate, isolating this test to the challenge path specifically."""
    with patch.object(jv_agents, "spice_text_search", AsyncMock(side_effect=_spice_text_search_stub(case_law_hits=3))), \
         patch.object(jv_agents, "web_search_node", AsyncMock(return_value={"web_evidence": []})):
        queue: asyncio.Queue = asyncio.Queue()
        result = await jv_agents.run_collaborative_pipeline("What is Section 100?", {"use_web_search": True}, queue)

    assert "No web corroboration" in result["coordination_summary"]
    assert "requested help from" not in result["coordination_summary"]


@pytest.mark.asyncio
async def test_no_challenge_when_web_verifier_finds_corroboration(base_mocks):
    web_hit = {"title": "News", "url": "https://example.com", "content": "c", "score": 0.5,
               "domain": "web", "content_hash": "web-hash"}
    with patch.object(jv_agents, "spice_text_search", AsyncMock(side_effect=_spice_text_search_stub(case_law_hits=3))), \
         patch.object(jv_agents, "web_search_node", AsyncMock(return_value={"web_evidence": [web_hit]})):
        queue: asyncio.Queue = asyncio.Queue()
        result = await jv_agents.run_collaborative_pipeline("What is Section 100?", {"use_web_search": True}, queue)

    assert result["coordination_summary"] == (
        "No cross-agent requests or challenges — all findings were accepted as-is."
    )


@pytest.mark.asyncio
async def test_agent_messages_are_pushed_through_the_queue_live(base_mocks):
    """The bus's on_message hook must actually reach the SSE queue as
    agent_message events — this is what makes the negotiation visible to the
    frontend, not just present in the final return value."""
    with patch.object(jv_agents, "spice_text_search", AsyncMock(side_effect=_spice_text_search_stub(case_law_hits=0))), \
         patch.object(jv_agents, "web_search_node", AsyncMock(return_value={"web_evidence": []})):
        queue: asyncio.Queue = asyncio.Queue()
        await jv_agents.run_collaborative_pipeline("What is Section 100?", {"use_web_search": True}, queue)

    drained = []
    while not queue.empty():
        drained.append(queue.get_nowait())

    agent_messages = [d for d in drained if d.get("step") == "agent_message"]
    assert any(m["type"] == "request" for m in agent_messages)
    assert any(m["type"] == "challenge" for m in agent_messages)


@pytest.mark.asyncio
async def test_case_analyst_skips_cleanly_when_plan_says_no_case_law_needed(base_mocks):
    with patch.object(jv_agents, "_plan_research", AsyncMock(return_value=_fixed_plan(needs_case_law=False))), \
         patch.object(jv_agents, "spice_text_search", AsyncMock(return_value=[_chunk()])), \
         patch.object(jv_agents, "web_search_node", AsyncMock(return_value={"web_evidence": []})):
        queue: asyncio.Queue = asyncio.Queue()
        result = await jv_agents.run_collaborative_pipeline("What is Section 100?", {"use_web_search": True}, queue)

    assert result["plan"]["needs_case_law"] is False
    requests = [m for m in result["coordination_summary"].split(" · ") if "requested help from" in m]
    assert not requests


@pytest.mark.asyncio
async def test_case_analyst_is_never_spawned_when_not_needed(base_mocks):
    """On-demand spawning: the supervisor must decide NOT to create the
    case_analyst task at all when the plan doesn't call for it — not spawn
    it and let it skip itself internally."""
    with patch.object(jv_agents, "_plan_research", AsyncMock(return_value=_fixed_plan(needs_case_law=False))), \
         patch.object(jv_agents, "_agent_case_analyst", AsyncMock()) as mock_case_analyst, \
         patch.object(jv_agents, "spice_text_search", AsyncMock(return_value=[_chunk()])), \
         patch.object(jv_agents, "web_search_node", AsyncMock(return_value={"web_evidence": []})):
        queue: asyncio.Queue = asyncio.Queue()
        await jv_agents.run_collaborative_pipeline("What is Section 100?", {"use_web_search": True}, queue)

    mock_case_analyst.assert_not_called()


@pytest.mark.asyncio
async def test_web_verifier_is_never_spawned_when_web_search_disabled(base_mocks):
    with patch.object(jv_agents, "_agent_web_verifier", AsyncMock()) as mock_web_verifier, \
         patch.object(jv_agents, "spice_text_search", AsyncMock(side_effect=_spice_text_search_stub(case_law_hits=3))):
        queue: asyncio.Queue = asyncio.Queue()
        await jv_agents.run_collaborative_pipeline("What is Section 100?", {"use_web_search": False}, queue)

    mock_web_verifier.assert_not_called()


@pytest.mark.asyncio
async def test_needed_sub_agents_are_spawned_exactly_once(base_mocks):
    """The flip side: when the plan does call for them, both sub-agents must
    actually be spawned (not silently dropped) — exactly once each."""
    with patch.object(jv_agents, "_agent_case_analyst", AsyncMock()) as mock_case_analyst, \
         patch.object(jv_agents, "_agent_web_verifier", AsyncMock()) as mock_web_verifier, \
         patch.object(jv_agents, "spice_text_search", AsyncMock(side_effect=_spice_text_search_stub(case_law_hits=3))):
        queue: asyncio.Queue = asyncio.Queue()
        await jv_agents.run_collaborative_pipeline("What is Section 100?", {"use_web_search": True}, queue)

    mock_case_analyst.assert_called_once()
    mock_web_verifier.assert_called_once()
