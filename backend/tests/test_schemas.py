from __future__ import annotations
from datetime import date

from app.api.schemas import ChatRequest


def test_as_of_date_defaults_to_today():
    request = ChatRequest(question="What is Section 302 IPC?")
    assert request.as_of_date == date.today().isoformat()


def test_as_of_date_explicit_override_preserved():
    request = ChatRequest(question="What is Section 302 IPC?", as_of_date="2020-01-01")
    assert request.as_of_date == "2020-01-01"
