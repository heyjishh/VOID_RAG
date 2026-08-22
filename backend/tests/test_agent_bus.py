import pytest

from app.core.graph.agent_bus import AgentBus, AgentMessage


def test_broadcast_delivers_to_all_agents_except_sender():
    bus = AgentBus(["a", "b", "c"])
    bus.send(AgentMessage(from_agent="a", to_agent="*", type="finding", content="hi"))

    assert bus._inboxes["a"].empty()
    assert not bus._inboxes["b"].empty()
    assert not bus._inboxes["c"].empty()


def test_targeted_message_delivers_only_to_recipient():
    bus = AgentBus(["a", "b", "c"])
    bus.send(AgentMessage(from_agent="a", to_agent="b", type="request", content="help"))

    assert bus._inboxes["a"].empty()
    assert not bus._inboxes["b"].empty()
    assert bus._inboxes["c"].empty()


def test_send_appends_to_transcript_and_notifies_on_message():
    seen = []
    bus = AgentBus(["a", "b"], on_message=seen.append)
    msg = AgentMessage(from_agent="a", to_agent="b", type="finding", content="x")
    bus.send(msg)

    assert bus.transcript == [msg]
    assert seen == [msg.to_dict()]


@pytest.mark.asyncio
async def test_receive_times_out_and_returns_none_when_inbox_empty():
    bus = AgentBus(["a"])
    result = await bus.receive("a", timeout=0.05)
    assert result is None


@pytest.mark.asyncio
async def test_wait_for_returns_first_matching_message_and_discards_others():
    bus = AgentBus(["a", "b"])
    bus.send(AgentMessage(from_agent="b", to_agent="a", type="finding", content="irrelevant"))
    bus.send(AgentMessage(from_agent="b", to_agent="a", type="request", content="the one we want"))

    result = await bus.wait_for("a", lambda m: m.type == "request", timeout=1.0)

    assert result is not None
    assert result.content == "the one we want"
    # The non-matching "finding" was consumed off the queue while filtering —
    # it stays in the transcript (already delivered to on_message at send
    # time), it just isn't what this particular wait_for() call reacted to.
    assert bus._inboxes["a"].empty()


@pytest.mark.asyncio
async def test_wait_for_returns_none_when_deadline_passes_with_no_match():
    bus = AgentBus(["a", "b"])
    bus.send(AgentMessage(from_agent="b", to_agent="a", type="finding", content="not a request"))

    result = await bus.wait_for("a", lambda m: m.type == "request", timeout=0.1)
    assert result is None
