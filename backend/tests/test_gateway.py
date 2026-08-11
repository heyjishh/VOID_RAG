import os
import tempfile
from pathlib import Path
from unittest.mock import patch


def test_auto_configure_picks_known_bucket():
    with tempfile.TemporaryDirectory() as tmpdir:
        env_path = Path(tmpdir) / ".env"
        with patch("scripts.auto_configure.ENV_FILE", env_path), \
             patch("scripts.auto_configure._list_s3_buckets",
                   return_value=["all-acts-raw", "some-other-bucket"]), \
             patch("scripts.auto_configure._read_gateway_key", return_value="testkey"):
            from scripts.auto_configure import run_auto_configure
            written = run_auto_configure()
        assert "S3_BUCKET_NAME" in written
        content = env_path.read_text()
        assert "S3_BUCKET_NAME=all-acts-raw" in content
        assert "GATEWAY_KEY=testkey" in content


def test_auto_configure_skips_when_already_set():
    with tempfile.TemporaryDirectory() as tmpdir:
        env_path = Path(tmpdir) / ".env"
        env_path.write_text("S3_BUCKET_NAME=mybucket\nGATEWAY_KEY=existingkey\n")
        with patch("scripts.auto_configure.ENV_FILE", env_path):
            from scripts.auto_configure import run_auto_configure
            # must reload since ENV_FILE is module-level
            import importlib, scripts.auto_configure as m
            m.ENV_FILE = env_path
            written = m.run_auto_configure()
        assert written == {}


def test_settings_gateway_first_when_key_set():
    import importlib
    import app.config.settings as sm
    from unittest.mock import patch
    with patch.dict("os.environ", {"GATEWAY_KEY": "testkey123", "GATEWAY_URL": "http://localhost:8080/v1"}):
        importlib.reload(sm)
        chain = sm.Settings().llm_provider_chain
    assert chain[0]["api_base"] == "http://localhost:8080/v1"
    assert chain[0]["api_key"] == "testkey123"


def test_chat_response_has_source_chunks():
    from app.api.schemas import ChatResponse, SourceChunkOut, CitationOut
    r = ChatResponse(
        answer="test",
        citations=[],
        source_chunks=[SourceChunkOut(text="Murder is punishable", source="ipc.pdf", page=5, score=0.9, verified=True)],
        conversation_id="x",
        intent="legal",
        sources_used=1,
    )
    assert r.source_chunks[0].source == "ipc.pdf"
    assert r.source_chunks[0].verified is True
    assert r.source_chunks[0].domain == "internal"
