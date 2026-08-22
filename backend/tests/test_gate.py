from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.core.graph import gate


def _verification(score: float, unsupported: list[str] | None = None) -> dict:
    return {
        "groundedness_score": score,
        "verdict": "grounded" if score >= 0.8 else ("partially_grounded" if score >= 0.5 else "unsupported"),
        "supported_claims": [],
        "unsupported_claims": unsupported or [],
    }


def _chunk(text="new evidence text", source="Some Act, 1950", content_hash="new-hash"):
    return {"text": text, "source": source, "page": 1, "score": 0.7, "domain": "internal", "content_hash": content_hash}


@pytest.fixture
def gate_settings():
    with patch.object(gate, "settings", SimpleNamespace(
        VERIFIER_GATE_ENABLED=True, GROUNDEDNESS_MIN=0.8,
        GATE_MAX_CORRECTION_ROUNDS=3, GATE_MAX_CLAIMS_PER_ROUND=3,
    )):
        yield


@pytest.mark.asyncio
async def test_answer_that_already_passes_is_returned_unchanged(gate_settings):
    verification = _verification(0.9)
    result = await gate.gate_answer("Q", "answer", [], "evidence text", verification)
    assert result.answer == "answer"
    assert result.blocked is False
    assert result.regenerated is False
    assert result.rounds == 0


@pytest.mark.asyncio
async def test_correction_searches_for_specific_unsupported_claims(gate_settings):
    """The whole point of auto-correct: it must search using the claim text,
    not blindly retry with the same evidence."""
    verification = _verification(0.3, unsupported=["Section 99 defines X"])

    with patch.object(gate, "_search_for_claim", AsyncMock(return_value=[_chunk()])) as mock_search, \
         patch.object(gate, "_regenerate", AsyncMock(return_value=("corrected answer", "groq", "m"))), \
         patch.object(gate, "verify_answer", AsyncMock(return_value=_verification(0.9))):
        result = await gate.gate_answer("Q", "bad answer", [], "evidence text", verification)

    mock_search.assert_called_once_with("Section 99 defines X")
    assert result.answer == "corrected answer"
    assert result.blocked is False
    assert result.regenerated is True
    assert result.rounds == 1


@pytest.mark.asyncio
async def test_stops_early_once_grounded_without_using_all_rounds(gate_settings):
    verification = _verification(0.3, unsupported=["claim A"])
    call_count = {"n": 0}

    async def _regen(question, evidence_text):
        call_count["n"] += 1
        return f"attempt {call_count['n']}", "groq", "m"

    with patch.object(gate, "_search_for_claim", AsyncMock(return_value=[_chunk()])), \
         patch.object(gate, "_regenerate", AsyncMock(side_effect=_regen)), \
         patch.object(gate, "verify_answer", AsyncMock(return_value=_verification(0.95))):
        result = await gate.gate_answer("Q", "bad answer", [], "evidence text", verification)

    assert call_count["n"] == 1  # passed on round 1 — must not burn the remaining rounds
    assert result.rounds == 1
    assert result.blocked is False


@pytest.mark.asyncio
async def test_stops_when_a_round_finds_no_new_evidence(gate_settings):
    """Round 2+ finding zero new evidence means looping further can't help —
    stop instead of burning the remaining rounds on an identical retry."""
    verification = _verification(0.3, unsupported=["claim A"])
    search_calls = {"n": 0}

    async def _search(claim):
        search_calls["n"] += 1
        return [_chunk()] if search_calls["n"] == 1 else []  # first round finds evidence, later rounds don't

    regen_calls = {"n": 0}

    async def _regen(question, evidence_text):
        regen_calls["n"] += 1
        return f"attempt {regen_calls['n']}", "groq", "m"

    with patch.object(gate, "_search_for_claim", AsyncMock(side_effect=_search)), \
         patch.object(gate, "_regenerate", AsyncMock(side_effect=_regen)), \
         patch.object(gate, "verify_answer", AsyncMock(return_value=_verification(0.3, unsupported=["claim A"]))):
        result = await gate.gate_answer("Q", "bad answer", [], "evidence text", verification)

    # Round 1 finds evidence and regenerates; round 2 finds nothing new, so
    # the loop stops BEFORE regenerating again (an identical retry can't help).
    assert regen_calls["n"] == 1
    assert result.rounds == 1
    assert result.blocked is True


@pytest.mark.asyncio
async def test_blocks_when_still_unsupported_after_all_rounds(gate_settings):
    """Evidence keeps coming (so the loop never stops early on 'no new
    evidence'), but the answer never actually clears the grounding bar —
    all GATE_MAX_CORRECTION_ROUNDS rounds should run before blocking."""
    verification = _verification(0.2, unsupported=["claim A", "claim B"])
    counter = {"n": 0}

    async def _search(claim):
        counter["n"] += 1
        return [_chunk(content_hash=f"h{counter['n']}")]  # a genuinely new hash every call

    with patch.object(gate, "_search_for_claim", AsyncMock(side_effect=_search)), \
         patch.object(gate, "_regenerate", AsyncMock(return_value=("still bad", "groq", "m"))), \
         patch.object(gate, "verify_answer", AsyncMock(return_value=_verification(0.2, unsupported=["claim A"]))):
        result = await gate.gate_answer("Q", "bad answer", [], "evidence text", verification)

    assert result.blocked is True
    assert result.rounds == gate.settings.GATE_MAX_CORRECTION_ROUNDS


@pytest.mark.asyncio
async def test_on_round_callback_fires_per_round(gate_settings):
    verification = _verification(0.3, unsupported=["claim A"])
    rounds_seen = []

    with patch.object(gate, "_search_for_claim", AsyncMock(return_value=[_chunk()])), \
         patch.object(gate, "_regenerate", AsyncMock(return_value=("fixed", "groq", "m"))), \
         patch.object(gate, "verify_answer", AsyncMock(return_value=_verification(0.9))):
        await gate.gate_answer(
            "Q", "bad answer", [], "evidence text", verification,
            on_round=lambda d: rounds_seen.append(d),
        )

    assert len(rounds_seen) == 1
    assert rounds_seen[0]["round"] == 1
    assert "claim" in rounds_seen[0]["detail"].lower()


@pytest.mark.asyncio
async def test_disabled_gate_skips_everything(gate_settings):
    with patch.object(gate.settings, "VERIFIER_GATE_ENABLED", False):
        result = await gate.gate_answer("Q", "answer", [], "evidence", _verification(0.0))
    assert result.blocked is False
    assert result.regenerated is False
