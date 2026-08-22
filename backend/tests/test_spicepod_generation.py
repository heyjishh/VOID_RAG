"""Regression tests for app.main._generate_spicepod.

Guards against the two silent-breakage bugs this function had: the corpus
dataset pointing at a Postgres table that doesn't exist, and the embedding
model living under the wrong top-level key (models: instead of embeddings:)
with no dataset ever wired to use it.
"""
from __future__ import annotations
from pathlib import Path

import pytest

import app.main as main_mod
from app.config.settings import settings
from app.main import _generate_spicepod

# _generate_spicepod imports pathlib.Path locally and derives its output
# path from its own __file__ — not mockable/redirectable, so this test
# writes to (and reads back) the real backend/spicepod.yaml, same as the
# app does at real startup. It's gitignored and fully disposable.
_REAL_SPICEPOD_PATH = Path(main_mod.__file__).resolve().parent.parent / "spicepod.yaml"


@pytest.fixture
def generated_spicepod(monkeypatch):
    # Clear every provider ahead of Gemini in llm_provider_chain's priority
    # order so this test is deterministic regardless of which real keys
    # happen to be set in the local .env — otherwise a real GROQ_API_KEY
    # (higher priority) silently wins and this test asserts the wrong key.
    for higher_priority_key in ("GROQ_API_KEY", "NVIDIA_API_KEY", "MISTRAL_KEY", "MISTRAL_API_KEY"):
        monkeypatch.setattr(settings, higher_priority_key, None)
    monkeypatch.setattr(settings, "GOOGLE_GEMINI_KEY", "unused-in-test")
    monkeypatch.setattr(settings, "EMBED_MODEL", "BAAI/bge-base-en-v1.5")

    original = _REAL_SPICEPOD_PATH.read_text() if _REAL_SPICEPOD_PATH.exists() else None
    try:
        _generate_spicepod()
        yield _REAL_SPICEPOD_PATH.read_text()
    finally:
        if original is not None:
            _REAL_SPICEPOD_PATH.write_text(original)
        else:
            _REAL_SPICEPOD_PATH.unlink(missing_ok=True)


def test_corpus_dataset_points_at_real_legal_chunks_table(generated_spicepod):
    expected = f"from: postgres:{settings.POSTGRES_DB}.{settings.POSTGRES_SCHEMA}.legal_chunks"
    assert expected in generated_spicepod
    assert "from: postgres:legal_chunks\n" not in generated_spicepod
    assert "from: postgres:juryai\n" not in generated_spicepod


def test_no_embeddings_component_since_nothing_queries_spice_vector_search(generated_spicepod):
    assert "embeddings:" not in generated_spicepod
    assert "legal_embeddings" not in generated_spicepod


def test_corpus_dataset_wires_full_text_search(generated_spicepod):
    assert "full_text_search:\n          enabled: true" in generated_spicepod
    assert generated_spicepod.count("full_text_search:") == 1


def test_datasets_use_append_refresh_mode_with_time_column(generated_spicepod):
    assert generated_spicepod.count("refresh_mode: append") == 2
    assert generated_spicepod.count("time_column: created_at") == 2
    assert generated_spicepod.count("time_format: timestamptz") == 2


def test_datasets_use_duckdb_acceleration(generated_spicepod):
    assert "engine: arrow" not in generated_spicepod
    assert generated_spicepod.count("engine: duckdb") == 2


def test_nql_model_skips_groq_even_when_highest_priority(monkeypatch):
    monkeypatch.setattr(settings, "GROQ_API_KEY", "unused-in-test")
    monkeypatch.setattr(settings, "NVIDIA_API_KEY", "unused-in-test")
    monkeypatch.setattr(settings, "MISTRAL_KEY", None)
    monkeypatch.setattr(settings, "MISTRAL_API_KEY", None)
    monkeypatch.setattr(settings, "EMBED_MODEL", "BAAI/bge-base-en-v1.5")

    original = _REAL_SPICEPOD_PATH.read_text() if _REAL_SPICEPOD_PATH.exists() else None
    try:
        _generate_spicepod()
        generated = _REAL_SPICEPOD_PATH.read_text()
    finally:
        if original is not None:
            _REAL_SPICEPOD_PATH.write_text(original)
        else:
            _REAL_SPICEPOD_PATH.unlink(missing_ok=True)

    assert "api.groq.com" not in generated
    assert "integrate.api.nvidia.com" in generated


def test_nql_model_uses_endpoint_param_not_openai_api_base(generated_spicepod):
    assert "openai_api_base" not in generated_spicepod
    assert "openai_model:" not in generated_spicepod
    assert "endpoint:" in generated_spicepod


def test_no_raw_secrets_written_to_disk(generated_spicepod):
    """Regression: this file used to carry a live provider API key and the
    Postgres password in plaintext — SpiceAI resolves ${secrets:VAR} itself,
    so neither should ever appear as a literal value."""
    assert "unused-in-test" not in generated_spicepod
    assert "${secrets:GOOGLE_GEMINI_KEY}" in generated_spicepod
    assert "${secrets:POSTGRES_PASSWORD}" in generated_spicepod
