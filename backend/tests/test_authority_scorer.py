"""Tests for source type detection and authority scoring.

Coverage:
- detect_source_type: >= 10 distinct source categories
- AuthorityScorer.score: known inputs and expected ranges
- Weight sum invariant: α + β + γ + δ == 1.0 ± 0.001
"""
from __future__ import annotations
import math
import pytest


# ===========================================================================
# detect_source_type — URL-based tests
# ===========================================================================

class TestDetectSourceTypeUrl:
    """URL-based detection tests covering >= 10 distinct categories."""

    def test_sci_gov_in_supreme_court(self):
        from app.core.retrieval.source_type import detect_source_type
        assert detect_source_type(url="https://sci.gov.in/judgment/2023") == "supreme_court_judgment"

    def test_main_sci_gov_in_supreme_court(self):
        from app.core.retrieval.source_type import detect_source_type
        assert detect_source_type(url="https://main.sci.gov.in/judgment/2023-SC-001") == "supreme_court_judgment"

    def test_subdomain_sci_gov_in_supreme_court(self):
        """Any subdomain of sci.gov.in is still supreme court."""
        from app.core.retrieval.source_type import detect_source_type
        assert detect_source_type(url="https://efiles.sci.gov.in/doc/123") == "supreme_court_judgment"

    def test_indiankanoon_doc_with_sc_metadata(self):
        from app.core.retrieval.source_type import detect_source_type
        result = detect_source_type(
            url="https://indiankanoon.org/doc/12345/",
            metadata={"title": "Supreme Court of India: State of Maharashtra v XYZ"},
        )
        assert result == "supreme_court_judgment"

    def test_indiankanoon_doc_defaults_to_high_court(self):
        from app.core.retrieval.source_type import detect_source_type
        result = detect_source_type(url="https://indiankanoon.org/doc/67890/")
        assert result == "high_court_judgment"

    def test_delhi_high_court_domain_set(self):
        from app.core.retrieval.source_type import detect_source_type
        assert detect_source_type(url="https://delhihighcourt.nic.in/") == "high_court_judgment"

    def test_bombay_high_court_domain_set(self):
        from app.core.retrieval.source_type import detect_source_type
        assert detect_source_type(url="https://hcbombay.nic.in/judgment/2022") == "high_court_judgment"

    def test_allahabad_high_court_domain_set(self):
        from app.core.retrieval.source_type import detect_source_type
        assert detect_source_type(url="https://hcallahabad.nic.in/case/xyz") == "high_court_judgment"

    def test_indiacode_statute(self):
        from app.core.retrieval.source_type import detect_source_type
        assert detect_source_type(url="https://indiacode.nic.in/handle/123456789/2061") == "statute"

    def test_legislative_gov_in_statute(self):
        from app.core.retrieval.source_type import detect_source_type
        assert detect_source_type(url="https://legislative.gov.in/sites/default/files/A2020-50.pdf") == "statute"

    def test_egazette_gov_in_notification(self):
        from app.core.retrieval.source_type import detect_source_type
        assert detect_source_type(url="https://egazette.gov.in/WriteReadData/2022/notice.pdf") == "government_notification"

    def test_generic_gov_in_notification(self):
        """Any *.gov.in not matched by specific rules → government_notification."""
        from app.core.retrieval.source_type import detect_source_type
        assert detect_source_type(url="https://income.tax.gov.in/notice/2023.pdf") == "government_notification"

    def test_barandbench_legal_news(self):
        from app.core.retrieval.source_type import detect_source_type
        assert detect_source_type(url="https://barandbench.com/news/article") == "legal_news"

    def test_livelaw_legal_news(self):
        from app.core.retrieval.source_type import detect_source_type
        assert detect_source_type(url="https://livelaw.in/top-stories/xyz") == "legal_news"

    def test_taxmann_legal_news(self):
        from app.core.retrieval.source_type import detect_source_type
        assert detect_source_type(url="https://taxmann.com/research/gst") == "legal_news"

    def test_reddit_forum(self):
        from app.core.retrieval.source_type import detect_source_type
        assert detect_source_type(url="https://reddit.com/r/india/comments/abc") == "forum"

    def test_quora_forum(self):
        from app.core.retrieval.source_type import detect_source_type
        assert detect_source_type(url="https://quora.com/What-is-IPC-302") == "forum"

    def test_blog_subdomain_prefix(self):
        from app.core.retrieval.source_type import detect_source_type
        assert detect_source_type(url="https://blog.example.com/legal-update") == "blog"

    def test_blog_path_segment(self):
        from app.core.retrieval.source_type import detect_source_type
        assert detect_source_type(url="https://example.com/blog/legal-update") == "blog"

    def test_unknown_url(self):
        from app.core.retrieval.source_type import detect_source_type
        assert detect_source_type(url="https://example.com/some-random-page") == "unknown"

    def test_no_false_positive_mysci(self):
        """'mysci.gov.in' must NOT match the sci.gov.in pattern."""
        from app.core.retrieval.source_type import detect_source_type
        # mysci.gov.in should fall through to generic gov.in
        result = detect_source_type(url="https://mysci.gov.in/page")
        assert result == "government_notification"

    def test_egazette_not_caught_by_generic_govin(self):
        """egazette.gov.in must be caught by the specific rule, not the generic one."""
        from app.core.retrieval.source_type import detect_source_type
        # Both rules would give "government_notification", but the specific rule fires first
        result = detect_source_type(url="https://egazette.gov.in/gazette")
        assert result == "government_notification"


# ===========================================================================
# detect_source_type — filename-based tests (internal S3 docs)
# ===========================================================================

class TestDetectSourceTypeFilename:
    """Filename-based detection tests for internal S3 documents."""

    def test_sc_prefix_supreme_court(self):
        from app.core.retrieval.source_type import detect_source_type
        assert detect_source_type(filename="SC_2023_0001.pdf") == "supreme_court_judgment"

    def test_sci_prefix_supreme_court(self):
        from app.core.retrieval.source_type import detect_source_type
        assert detect_source_type(filename="SCI_JudgmentID_2022.pdf") == "supreme_court_judgment"

    def test_supreme_prefix_supreme_court(self):
        from app.core.retrieval.source_type import detect_source_type
        assert detect_source_type(filename="supreme_court_2023_abc.pdf") == "supreme_court_judgment"

    def test_hc_prefix_high_court(self):
        from app.core.retrieval.source_type import detect_source_type
        assert detect_source_type(filename="HC_Bombay_2022_Case.pdf") == "high_court_judgment"

    def test_high_court_prefix(self):
        from app.core.retrieval.source_type import detect_source_type
        assert detect_source_type(filename="high_court_delhi_2021.pdf") == "high_court_judgment"

    def test_act_pattern_statute(self):
        from app.core.retrieval.source_type import detect_source_type
        assert detect_source_type(filename="indian_penal_act_1860.pdf") == "statute"

    def test_statute_pattern(self):
        from app.core.retrieval.source_type import detect_source_type
        assert detect_source_type(filename="companies_statute_2013.pdf") == "statute"

    def test_code_pattern_statute(self):
        from app.core.retrieval.source_type import detect_source_type
        assert detect_source_type(filename="ipc_code.pdf") == "statute"

    def test_notification_pattern(self):
        from app.core.retrieval.source_type import detect_source_type
        assert detect_source_type(filename="notification_2023_gst.pdf") == "government_notification"

    def test_circular_pattern(self):
        from app.core.retrieval.source_type import detect_source_type
        assert detect_source_type(filename="circular_sebi_2022.pdf") == "government_notification"

    def test_gazette_pattern(self):
        from app.core.retrieval.source_type import detect_source_type
        assert detect_source_type(filename="gazette_extraordinary_2021.pdf") == "government_notification"

    def test_default_internal_is_case_doc(self):
        """Files with no matching pattern default to 'case_doc', not 'unknown'."""
        from app.core.retrieval.source_type import detect_source_type
        assert detect_source_type(filename="contract_draft_v2.pdf") == "case_doc"

    def test_default_internal_is_case_doc_generic(self):
        from app.core.retrieval.source_type import detect_source_type
        assert detect_source_type(filename="pleading_2022.pdf") == "case_doc"

    def test_s3_key_with_path_uses_basename(self):
        """S3 key with prefix path — only basename is pattern-matched."""
        from app.core.retrieval.source_type import detect_source_type
        result = detect_source_type(filename="documents/judgments/SC_2022_001.pdf")
        assert result == "supreme_court_judgment"

    def test_no_args_returns_unknown(self):
        from app.core.retrieval.source_type import detect_source_type
        assert detect_source_type() == "unknown"


# ===========================================================================
# HIGH_COURT_DOMAINS — verify it is a set (frozenset), not a list/tuple
# ===========================================================================

def test_high_court_domains_is_frozenset():
    from app.core.retrieval.source_type import HIGH_COURT_DOMAINS
    assert isinstance(HIGH_COURT_DOMAINS, frozenset), (
        "HIGH_COURT_DOMAINS must be a frozenset for O(1) lookup"
    )

def test_high_court_domains_populated():
    from app.core.retrieval.source_type import HIGH_COURT_DOMAINS
    assert len(HIGH_COURT_DOMAINS) >= 5


# ===========================================================================
# AuthorityScorer — unit tests
# ===========================================================================

class TestAuthorityScorer:

    def test_weight_sum_equals_one(self):
        """α + β + γ + δ must equal 1.0 ± 0.001 with default settings."""
        from app.config.settings import settings
        total = (
            settings.AUTHORITY_SCORE_ALPHA
            + settings.AUTHORITY_SCORE_BETA
            + settings.AUTHORITY_SCORE_GAMMA
            + settings.AUTHORITY_SCORE_DELTA
        )
        assert abs(total - 1.0) <= 0.001, (
            f"Weights α+β+γ+δ = {total:.6f}; expected 1.0 ± 0.001"
        )

    def test_max_citations_constant_is_10000(self):
        from app.core.retrieval.authority_scorer import MAX_CITATIONS
        assert MAX_CITATIONS == 10000

    def test_score_returns_float_in_unit_range(self):
        from app.core.retrieval.authority_scorer import AuthorityScorer
        scorer = AuthorityScorer()
        result = scorer.score({"source_type": "supreme_court_judgment"}, query_relevance=0.8)
        assert isinstance(result, float)
        assert 0.0 <= result <= 1.0

    def test_score_zero_relevance_non_negative(self):
        from app.core.retrieval.authority_scorer import AuthorityScorer
        scorer = AuthorityScorer()
        result = scorer.score({"source_type": "case_doc"}, query_relevance=0.0)
        assert result >= 0.0

    def test_score_clamps_relevance_above_one(self):
        """query_relevance > 1 must be clamped, not produce score > 1."""
        from app.core.retrieval.authority_scorer import AuthorityScorer
        scorer = AuthorityScorer()
        result = scorer.score({"source_type": "case_doc"}, query_relevance=5.0)
        assert 0.0 <= result <= 1.0

    def test_score_unknown_source_type_uses_default(self):
        """When source_type is not in AUTHORITY_TABLE, the 'default' key is used."""
        from app.core.retrieval.authority_scorer import AuthorityScorer
        from app.config.settings import settings
        scorer = AuthorityScorer()
        chunk = {"source_type": "totally_unknown_type_xyz"}
        result = scorer.score(chunk, query_relevance=1.0)
        default_authority = settings.AUTHORITY_TABLE.get("default", 0.60)
        # recency with no published_at = RECENCY_UNKNOWN_DATE_SCORE, citation_q with 0 cites = 0.0
        expected = (
            settings.AUTHORITY_SCORE_ALPHA * 1.0
            + settings.AUTHORITY_SCORE_BETA * default_authority
            + settings.AUTHORITY_SCORE_GAMMA * settings.RECENCY_UNKNOWN_DATE_SCORE
            + settings.AUTHORITY_SCORE_DELTA * 0.0
        )
        assert abs(result - expected) < 1e-9

    def test_score_literal_unknown_source_type_uses_dedicated_key(self):
        """detect_source_type()'s literal 'unknown' fallback must map to its
        own low-authority entry, not silently collide with 'default' — an
        unclassifiable source (forum spam, driver-support threads, etc.)
        should score below a merely-uncatalogued-but-plausible source."""
        from app.core.retrieval.authority_scorer import AuthorityScorer
        from app.config.settings import settings
        scorer = AuthorityScorer()
        unknown_score = scorer.score({"source_type": "unknown"}, query_relevance=0.5)
        default_score = scorer.score({"source_type": "totally_unknown_type_xyz"}, query_relevance=0.5)
        assert settings.AUTHORITY_TABLE["unknown"] < settings.AUTHORITY_TABLE.get("default", 0.60)
        assert unknown_score < default_score

    def test_score_higher_relevance_gives_higher_score(self):
        """Higher query_relevance → higher score (all else equal)."""
        from app.core.retrieval.authority_scorer import AuthorityScorer
        scorer = AuthorityScorer()
        chunk = {"source_type": "case_doc"}
        assert scorer.score(chunk, query_relevance=0.9) > scorer.score(chunk, query_relevance=0.1)

    def test_score_more_citations_gives_higher_score(self):
        """More citations → higher score (all else equal)."""
        from app.core.retrieval.authority_scorer import AuthorityScorer
        scorer = AuthorityScorer()
        chunk = {"source_type": "case_doc"}
        low = scorer.score(chunk, query_relevance=0.5, citation_count=0)
        high = scorer.score(chunk, query_relevance=0.5, citation_count=500)
        assert high > low

    def test_score_recent_document_beats_old(self):
        """A recent document scores higher on recency than an old one."""
        from app.core.retrieval.authority_scorer import AuthorityScorer
        scorer = AuthorityScorer()
        chunk = {"source_type": "case_doc"}
        recent = scorer.score(chunk, query_relevance=0.5, published_at="2025-01-01")
        old = scorer.score(chunk, query_relevance=0.5, published_at="1990-01-01")
        assert recent > old

    def test_score_max_citations_citation_q_is_one(self):
        """citation_count=MAX_CITATIONS gives citation_q=1.0 exactly."""
        from app.core.retrieval.authority_scorer import AuthorityScorer, MAX_CITATIONS
        from app.config.settings import settings
        scorer = AuthorityScorer()
        chunk = {}  # no source_type -> falls back to "default"
        default_authority = settings.AUTHORITY_TABLE.get("default", 0.60)
        result = scorer.score(chunk, query_relevance=1.0, citation_count=MAX_CITATIONS)
        # citation_q = log(1001)/log(1001) = 1.0; recency=RECENCY_UNKNOWN_DATE_SCORE (no published_at)
        expected = (
            settings.AUTHORITY_SCORE_ALPHA * 1.0
            + settings.AUTHORITY_SCORE_BETA * default_authority
            + settings.AUTHORITY_SCORE_GAMMA * settings.RECENCY_UNKNOWN_DATE_SCORE
            + settings.AUTHORITY_SCORE_DELTA * 1.0
        )
        assert abs(result - expected) < 1e-9

    def test_score_invalid_published_at_does_not_crash(self):
        """Invalid date string falls back to recency=1.0 (no penalty), no exception."""
        from app.core.retrieval.authority_scorer import AuthorityScorer
        scorer = AuthorityScorer()
        chunk = {"source_type": "case_doc"}
        result = scorer.score(chunk, query_relevance=0.5, published_at="not-a-date")
        assert 0.0 <= result <= 1.0

    def test_score_no_source_type_uses_default(self):
        """Missing source_type key falls back to AUTHORITY_TABLE default."""
        from app.core.retrieval.authority_scorer import AuthorityScorer
        scorer = AuthorityScorer()
        result = scorer.score({}, query_relevance=0.5)
        assert 0.0 <= result <= 1.0

    def test_score_citation_q_formula(self):
        """Verify citation_q = log(1 + cites) / log(1 + MAX_CITATIONS)."""
        from app.core.retrieval.authority_scorer import AuthorityScorer, MAX_CITATIONS
        from app.config.settings import settings
        scorer = AuthorityScorer()
        citation_count = 100
        expected_citation_q = math.log1p(citation_count) / math.log1p(MAX_CITATIONS)
        default_authority = settings.AUTHORITY_TABLE.get("default", 0.60)
        result = scorer.score({}, query_relevance=1.0, citation_count=citation_count)
        expected = (
            settings.AUTHORITY_SCORE_ALPHA * 1.0
            + settings.AUTHORITY_SCORE_BETA * default_authority
            + settings.AUTHORITY_SCORE_GAMMA * settings.RECENCY_UNKNOWN_DATE_SCORE
            + settings.AUTHORITY_SCORE_DELTA * expected_citation_q
        )
        assert abs(result - expected) < 1e-9

    def test_get_authority_scorer_returns_singleton(self):
        """get_authority_scorer() must return the same instance on repeated calls."""
        from app.core.retrieval.authority_scorer import get_authority_scorer
        scorer1 = get_authority_scorer()
        scorer2 = get_authority_scorer()
        assert scorer1 is scorer2

    def test_recency_no_date_uses_configured_unknown_score(self):
        """published_at=None uses RECENCY_UNKNOWN_DATE_SCORE, not full credit."""
        from app.core.retrieval.authority_scorer import AuthorityScorer
        from app.config.settings import settings
        scorer = AuthorityScorer()
        expected = (
            settings.AUTHORITY_SCORE_ALPHA * 1.0
            + settings.AUTHORITY_SCORE_BETA * settings.AUTHORITY_TABLE.get("default", 0.60)
            + settings.AUTHORITY_SCORE_GAMMA * settings.RECENCY_UNKNOWN_DATE_SCORE
            + settings.AUTHORITY_SCORE_DELTA * 0.0
        )
        result = scorer.score({}, query_relevance=1.0, published_at=None)
        assert abs(result - expected) < 1e-9

    def test_score_datetime_with_z_suffix(self):
        """ISO datetime with Z suffix must parse without error."""
        from app.core.retrieval.authority_scorer import AuthorityScorer
        scorer = AuthorityScorer()
        result = scorer.score({}, query_relevance=0.5, published_at="2024-06-15T12:00:00Z")
        assert 0.0 <= result <= 1.0

    def test_score_date_only_string(self):
        """Date-only string (no time component) must parse without error."""
        from app.core.retrieval.authority_scorer import AuthorityScorer
        scorer = AuthorityScorer()
        result = scorer.score({}, query_relevance=0.5, published_at="2023-03-01")
        assert 0.0 <= result <= 1.0
