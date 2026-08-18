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
    with patch.dict("os.environ", {
        "GATEWAY_KEY": "testkey123", "GATEWAY_URL": "http://localhost:8080/v1",
        "GROQ_API_KEY": "", "NVIDIA_API_KEY": "", "MISTRAL_API_KEY": "",
        "OPENAI_API_KEY": "", "ANTHROPIC_API_KEY": "",
        "MISTRAL_KEY": "", "GOOGLE_GEMINI_KEY": "", "SAMBANOVA_KEY": "", "CLOUDFLARE_KEY": "", "CLOUDFLARE_ACCOUNT_ID": "",
    }):
        importlib.reload(sm)
        chain = sm.Settings().llm_provider_chain
    assert chain[0]["base_url"] == "http://localhost:8080/v1"
    assert chain[0]["api_key"] == "testkey123"


def test_settings_groq_takes_priority_over_gateway():
    import importlib
    import app.config.settings as sm
    from unittest.mock import patch
    with patch.dict("os.environ", {
        "GATEWAY_KEY": "gatewaykey", "GATEWAY_URL": "http://localhost:8080/v1",
        "GROQ_API_KEY": "groqkey123", "NVIDIA_API_KEY": "",
        "MISTRAL_KEY": "", "GOOGLE_GEMINI_KEY": "", "SAMBANOVA_KEY": "", "CLOUDFLARE_KEY": "", "CLOUDFLARE_ACCOUNT_ID": "",
    }):
        importlib.reload(sm)
        chain = sm.Settings().llm_provider_chain
    assert chain[0]["provider_name"] == "groq"
    assert chain[0]["api_key"] == "groqkey123"
    assert chain[1]["provider_name"] == "gateway"


def test_settings_nvidia_falls_between_groq_and_gateway():
    import importlib
    import app.config.settings as sm
    from unittest.mock import patch
    with patch.dict("os.environ", {
        "GATEWAY_KEY": "gatewaykey", "GATEWAY_URL": "http://localhost:8080/v1",
        "GROQ_API_KEY": "groqkey123",
        "NVIDIA_API_KEY": "nvapi-testkey",
        "MISTRAL_KEY": "", "GOOGLE_GEMINI_KEY": "", "SAMBANOVA_KEY": "", "CLOUDFLARE_KEY": "", "CLOUDFLARE_ACCOUNT_ID": "",
    }):
        importlib.reload(sm)
        chain = sm.Settings().llm_provider_chain
    assert [p["provider_name"] for p in chain[:3]] == ["groq", "nvidia", "gateway"]
    assert chain[1]["api_key"] == "nvapi-testkey"
    assert chain[1]["base_url"] == "https://integrate.api.nvidia.com/v1"


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

def test_settings_all_direct_providers_present_when_keys_set():
    import importlib
    import app.config.settings as sm
    from unittest.mock import patch
    with patch.dict("os.environ", {
        "GROQ_API_KEY": "g", "NVIDIA_API_KEY": "n", "MISTRAL_KEY": "m",
        "GOOGLE_GEMINI_KEY": "gg", "SAMBANOVA_KEY": "s",
        "CLOUDFLARE_KEY": "c", "CLOUDFLARE_ACCOUNT_ID": "acct123",
        "GATEWAY_KEY": "", "MISTRAL_API_KEY": "", "OPENAI_API_KEY": "", "ANTHROPIC_API_KEY": "",
    }):
        importlib.reload(sm)
        chain = sm.Settings().llm_provider_chain
    names = [p["provider_name"] for p in chain]
    assert names == ["groq", "nvidia", "mistral", "gemini", "sambanova", "cloudflare"]
    cf = next(p for p in chain if p["provider_name"] == "cloudflare")
    assert cf["base_url"] == "https://api.cloudflare.com/client/v4/accounts/acct123/ai/v1"
