from app.config.settings import settings

def test_llm_provider_chain_has_at_least_one():
    chain = settings.llm_provider_chain
    assert len(chain) >= 1
    for p in chain:
        assert "model" in p and "api_key" in p

def test_web_search_provider_returns_string():
    p = settings.web_search_provider
    assert p in ("tavily", "brave", "duckduckgo")
