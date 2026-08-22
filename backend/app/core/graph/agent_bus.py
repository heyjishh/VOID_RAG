from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Callable, Literal

MessageType = Literal["finding", "request", "challenge", "clarify", "done"]


@dataclass
class AgentMessage:
    from_agent: str
    to_agent: str  # "*" = broadcast to every agent except the sender
    type: MessageType
    content: str
    ref_id: str | None = None
    ts: float = field(default_factory=time.monotonic)

    def to_dict(self) -> dict:
        return {
            "from": self.from_agent,
            "to": self.to_agent,
            "type": self.type,
            "content": self.content,
            "ref_id": self.ref_id,
        }


class AgentBus:
    """Mailbox-based message bus for concurrent agent tasks.

    Each agent gets its own asyncio.Queue. send() both routes the message to
    its recipient(s) AND appends it to the transcript / forwards it to
    on_message — the transcript is the actual visible "conversation" surfaced
    to the frontend, not a simulation reconstructed after the fact.
    """

    def __init__(self, agent_ids: list[str], on_message: Callable[[dict], None] | None = None):
        self._inboxes: dict[str, asyncio.Queue[AgentMessage]] = {a: asyncio.Queue() for a in agent_ids}
        self.transcript: list[AgentMessage] = []
        self._on_message = on_message

    def send(self, msg: AgentMessage) -> None:
        self.transcript.append(msg)
        if self._on_message:
            self._on_message(msg.to_dict())
        if msg.to_agent == "*":
            for agent_id, inbox in self._inboxes.items():
                if agent_id != msg.from_agent:
                    inbox.put_nowait(msg)
        else:
            inbox = self._inboxes.get(msg.to_agent)
            if inbox is not None:
                inbox.put_nowait(msg)

    async def receive(self, agent_id: str, timeout: float) -> AgentMessage | None:
        try:
            return await asyncio.wait_for(self._inboxes[agent_id].get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None

    async def wait_for(
        self, agent_id: str, predicate: Callable[[AgentMessage], bool], timeout: float,
    ) -> AgentMessage | None:
        """Loop the inbox until a message matching `predicate` arrives or the
        deadline passes. Non-matching messages (e.g. an unrelated broadcast)
        are discarded from the queue but stay in the transcript/SSE stream —
        this only decides what the *waiting agent* reacts to."""
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            msg = await self.receive(agent_id, timeout=remaining)
            if msg is None:
                return None
            if predicate(msg):
                return msg
