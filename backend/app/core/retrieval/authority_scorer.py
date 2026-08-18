"""Authority scoring for legal document chunks and web evidence.

Multi-factor formula with citation graph PageRank:
------------------------------------------------
    z_relevance = clip(query_relevance, 0, 1)
    authority   = court_hierarchy * citation_pagerank * treatment_factor * jurisdiction_factor
    recency     = exp(-λ * years_since)  with landmark exception
    citation_q  = log(1 + cites) / log(1 + MAX_CITATIONS)
    score       = α*z_relevance + β*authority + γ*recency + δ*citation_q

All weights (α, β, γ, δ) are loaded from settings; they MUST sum to 1.0.

Based on:
- Precedential Authority Scoring (Inferensys glossary)
- LeCNet: Indian Legal Citation Network (JUST-NLP 2025)
- PageRank variants for legal citation networks (Ding et al., 2009; Zhou et al., 2025)
- STRank: Fusing structural and temporal information (Zhou et al., 2025)
"""
from __future__ import annotations
import math
from datetime import datetime, timezone
from functools import lru_cache
from dataclasses import dataclass, field
from typing import Optional

from app.config.settings import settings
from app.core.retrieval.citation_extractor import CourtLevel, CitationType, LegalCitation

# Maximum citation count used for citation-quality normalisation
MAX_CITATIONS: int = 10000

# Landmark cases that retain full authority despite age (Indian context)
_LANDMARK_CASES = frozenset([
    "kesavananda bharati", "maneka gandhi", "golak nath", "minerva mills",
    "s.r. bommai", "indira gandhi", "keshavananda", "a.k. gopalan",
    "shreya singhal", "pragati mahila", "vineet narain", "d.k. basu",
    "vishaka", "olga tellis", "bombay hospital", "l. chandra kumar",
])

_STATUTE_SUCCESSION: list[tuple[str, str, str]] = [
    ("indian penal code", "bharatiya nyaya sanhita", "2024-07-01"),
    ("code of criminal procedure", "bharatiya nagarik suraksha sanhita", "2024-07-01"),
    ("indian evidence act", "bharatiya sakshya adhiniyam", "2024-07-01"),
]


def temporal_relevance(text: str, as_of_date: str) -> float:
    try:
        target = _parse_iso(as_of_date)
    except (ValueError, TypeError):
        return 1.0
    lowered = text.lower()
    for old_name, new_name, transition in _STATUTE_SUCCESSION:
        old_in_force = target < _parse_iso(transition)
        if old_in_force and new_name in lowered:
            return 0.15
        if not old_in_force and old_name in lowered:
            return 0.15
    return 1.0


@dataclass
class CitationGraphNode:
    """Node in citation graph for PageRank computation."""
    doc_id: str
    court_level: CourtLevel = CourtLevel.UNKNOWN
    citation_type: CitationType = CitationType.UNKNOWN
    year: Optional[int] = None
    is_landmark: bool = False
    outgoing_edges: list[str] = field(default_factory=list)  # docs this cites
    incoming_edges: list[str] = field(default_factory=list)  # docs citing this
    pagerank: float = 1.0
    treatment_history: str = "unknown"  # followed, distinguished, overruled, questioned


class CitationGraph:
    """Citation graph with PageRank computation for authority scoring."""
    
    def __init__(self, damping: float = 0.85, max_iter: int = 100, tol: float = 1e-6):
        self._nodes: dict[str, CitationGraphNode] = {}
        self._damping = damping
        self._max_iter = max_iter
        self._tol = tol
        self._pagerank_computed = False
    
    def add_node(self, doc_id: str, court_level: CourtLevel = CourtLevel.UNKNOWN,
                 citation_type: CitationType = CitationType.UNKNOWN,
                 year: Optional[int] = None, is_landmark: bool = False) -> None:
        """Add or update a node in the graph."""
        if doc_id not in self._nodes:
            self._nodes[doc_id] = CitationGraphNode(
                doc_id=doc_id,
                court_level=court_level,
                citation_type=citation_type,
                year=year,
                is_landmark=is_landmark,
            )
        else:
            node = self._nodes[doc_id]
            node.court_level = max(node.court_level, court_level, key=lambda c: c.value)
            if citation_type != CitationType.UNKNOWN:
                node.citation_type = citation_type
            if year and (not node.year or year < node.year):
                node.year = year
            node.is_landmark = node.is_landmark or is_landmark
        self._pagerank_computed = False
    
    def add_citation(self, citing_doc: str, cited_doc: str,
                     treatment: str = "followed") -> None:
        """Add citation edge with treatment history."""
        # Ensure both nodes exist
        if citing_doc not in self._nodes:
            self.add_node(citing_doc)
        if cited_doc not in self._nodes:
            self.add_node(cited_doc)
        
        # Add edges
        self._nodes[citing_doc].outgoing_edges.append(cited_doc)
        self._nodes[cited_doc].incoming_edges.append(citing_doc)
        
        # Update treatment history on cited node
        # Most severe treatment wins: overruled > questioned > distinguished > followed
        severity = {"overruled": 4, "questioned": 3, "distinguished": 2, "followed": 1}
        current_severity = severity.get(self._nodes[cited_doc].treatment_history, 1)
        new_severity = severity.get(treatment, 1)
        if new_severity > current_severity:
            self._nodes[cited_doc].treatment_history = treatment
        
        self._pagerank_computed = False
    
    def compute_pagerank(self) -> dict[str, float]:
        """Compute PageRank scores for all nodes."""
        if self._pagerank_computed:
            return {doc_id: node.pagerank for doc_id, node in self._nodes.items()}
        
        n = len(self._nodes)
        if n == 0:
            return {}
        
        # Initialize
        doc_ids = list(self._nodes.keys())
        ranks = {doc_id: 1.0 / n for doc_id in doc_ids}
        
        # Build adjacency
        out_links = {doc_id: self._nodes[doc_id].outgoing_edges for doc_id in doc_ids}
        in_links = {doc_id: self._nodes[doc_id].incoming_edges for doc_id in doc_ids}
        
        # Power iteration
        for _ in range(self._max_iter):
            new_ranks = {}
            max_diff = 0.0
            
            for doc_id in doc_ids:
                # Dangling node handling
                out_edges = out_links.get(doc_id, [])
                if not out_edges:
                    # Distribute rank evenly (dangling node)
                    rank_sum = sum(ranks.values()) / n
                else:
                    rank_sum = sum(ranks[cited] / len(out_links[cited]) 
                                  for cited in out_edges 
                                  if cited in ranks and out_links.get(cited))
                
                new_rank = (1 - self._damping) / n + self._damping * rank_sum
                new_ranks[doc_id] = new_rank
                max_diff = max(max_diff, abs(new_rank - ranks[doc_id]))
            
            ranks = new_ranks
            if max_diff < self._tol:
                break
        
        # Store and normalize
        max_rank = max(ranks.values()) if ranks else 1.0
        for doc_id, rank in ranks.items():
            self._nodes[doc_id].pagerank = rank / max_rank
        
        self._pagerank_computed = True
        return {doc_id: self._nodes[doc_id].pagerank for doc_id in doc_ids}
    
    def get_authority_score(self, doc_id: str) -> float:
        """Get composite authority score for a document."""
        if doc_id not in self._nodes:
            return 0.15  # default for unknown
        
        node = self._nodes[doc_id]
        
        # Ensure PageRank is computed
        if not self._pagerank_computed:
            self.compute_pagerank()
        
        # Court hierarchy weight (0.2 - 1.0)
        court_weight = node.court_level.value / 5.0
        
        # PageRank centrality (0 - 1)
        pagerank_score = node.pagerank
        
        # Treatment history factor
        treatment_factors = {
            "followed": 1.0,
            "distinguished": 0.7,
            "questioned": 0.4,
            "overruled": 0.05,
            "unknown": 0.85,
        }
        treatment_factor = treatment_factors.get(node.treatment_history, 0.85)
        
        # Landmark exception: full authority regardless of age/treatment
        if node.is_landmark:
            treatment_factor = 1.0
            court_weight = 1.0
        
        # Citation type bonus
        type_bonus = 1.0
        if node.citation_type in (CitationType.CONSTITUTIONAL, CitationType.STATUTE, CitationType.ORDINANCE):
            type_bonus = 1.2
        
        # Combine: court_hierarchy * pagerank * treatment * type_bonus
        authority = court_weight * pagerank_score * treatment_factor * type_bonus
        
        return min(1.0, max(0.0, authority))


_TREATMENT_SIGNALS: list[tuple[str, str]] = [
    ("no longer good law", "overruled"),
    ("overrul", "overruled"),
    ("set aside", "overruled"),
    ("reversed on appeal", "overruled"),
    ("doubt", "questioned"),
    ("distinguish", "distinguished"),
]


def _detect_treatment(text: str, raw_citation: str) -> str:
    pos = text.find(raw_citation)
    if pos == -1:
        return "followed"
    window = text[max(0, pos - 80): pos + len(raw_citation) + 80].lower()
    for keyword, treatment in _TREATMENT_SIGNALS:
        if keyword in window:
            return treatment
    return "followed"


def build_citation_graph_from_chunks(chunks: list[dict]) -> CitationGraph:
    """Build a fresh citation graph scoped to one query's retrieved chunks.

    Scoped per call (not a shared global) — the candidate set differs on every
    query, and reusing one graph across queries would let unrelated chunks'
    citation edges and PageRank leak into each other."""
    graph = CitationGraph(
        damping=settings.PAGERANK_DAMPING if hasattr(settings, 'PAGERANK_DAMPING') else 0.85,
    )

    for i, chunk in enumerate(chunks):
        doc_id = f"chunk_{chunk.get('source', 'unknown')}_{chunk.get('page', i)}"
        
        # Extract citations from chunk text
        text = chunk.get("text", "")
        citations = []
        try:
            from app.core.retrieval.citation_extractor import extract_citations
            citations = extract_citations(text)
        except ImportError:
            pass
        
        # Determine node properties
        court_level = CourtLevel.UNKNOWN
        citation_type = CitationType.UNKNOWN
        year = None
        is_landmark = False
        
        if citations:
            # Use highest court level from citations
            court_level = max((c.court_level for c in citations), key=lambda c: c.value)
            citation_type = citations[0].citation_type
            year = citations[0].year
            
            # Check for landmark cases
            for cite in citations:
                if any(lm in cite.raw_text.lower() for lm in _LANDMARK_CASES):
                    is_landmark = True
                    break
        
        graph.add_node(doc_id, court_level, citation_type, year, is_landmark)
        
        # Add citation edges
        for cite in citations:
            if cite.normalized:
                cited_id = cite.normalized.replace(" ", "_").replace("(", "").replace(")", "")
                treatment = _detect_treatment(text, cite.raw_text)
                graph.add_citation(doc_id, cited_id, treatment)
    
    return graph


class AuthorityScorer:
    """Multi-factor authority scorer with citation graph PageRank."""
    
    def __init__(self) -> None:
        self._table: dict[str, float] = dict(settings.AUTHORITY_TABLE)
        self._alpha: float = settings.AUTHORITY_SCORE_ALPHA
        self._beta: float = settings.AUTHORITY_SCORE_BETA
        self._gamma: float = settings.AUTHORITY_SCORE_GAMMA
        self._delta: float = settings.AUTHORITY_SCORE_DELTA
        self._lambda: float = settings.RECENCY_DECAY_LAMBDA
        self._recency_unknown: float = settings.RECENCY_UNKNOWN_DATE_SCORE
        
        # Citation graph for PageRank-based authority — built per query batch
        # by build_graph(), not at construction time.
        self._citation_graph: Optional[CitationGraph] = None
        self._graph_built = False

    def build_graph(self, chunks: list[dict]) -> None:
        """Build the citation graph for this query's retrieved chunks.

        Rebuilds every call — the candidate chunk set is different per query,
        so there is no valid "already built" state to skip."""
        self._citation_graph = build_citation_graph_from_chunks(chunks)
        self._citation_graph.compute_pagerank()
        self._graph_built = True
    
    def score(
        self,
        chunk_or_evidence: dict,
        query_relevance: float,
        published_at: str | None = None,
        citation_count: int = 0,
    ) -> float:
        """Compute composite authority score with PageRank."""
        source_type: str = chunk_or_evidence.get("source_type") or ""
        doc_id = f"chunk_{chunk_or_evidence.get('source', 'unknown')}_{chunk_or_evidence.get('page', 0)}"
        
        z_relevance: float = max(0.0, min(1.0, query_relevance))
        
        # PageRank-based authority (overrides table lookup when graph available)
        if self._graph_built and self._citation_graph and doc_id in self._citation_graph._nodes:
            authority = self._citation_graph.get_authority_score(doc_id)
        else:
            authority = self._authority(source_type)
        
        recency = self._recency(published_at)
        citation_q = math.log1p(citation_count) / math.log1p(MAX_CITATIONS)
        
        return (
            self._alpha * z_relevance
            + self._beta * authority
            + self._gamma * recency
            + self._delta * citation_q
        )
    
    def _authority(self, source_type: str) -> float:
        """Look up authority score from AUTHORITY_TABLE; fall back to default."""
        return self._table.get(source_type, self._table.get("default", 0.60))
    
    def _recency(self, published_at: str | None) -> float:
        """Compute recency decay with landmark exception."""
        if not published_at:
            return self._recency_unknown
        try:
            pub_dt = _parse_iso(published_at)
            now = datetime.now(tz=timezone.utc)
            years_since = max(0.0, (now - pub_dt).days / 365.25)
            
            # Check if this is a landmark case (would need doc_id)
            # For now, apply standard decay
            return math.exp(-self._lambda * years_since)
        except (ValueError, TypeError, OverflowError):
            return self._recency_unknown
    
    def get_citation_graph_stats(self) -> dict:
        """Get citation graph statistics for monitoring."""
        if not self._graph_built or self._citation_graph is None:
            return {"status": "not_built"}
        return {
            "nodes": len(self._citation_graph._nodes),
            "edges": sum(len(n.outgoing_edges) for n in self._citation_graph._nodes.values()),
            "pagerank_computed": self._citation_graph._pagerank_computed,
        }


def _parse_iso(date_str: str) -> datetime:
    """Parse an ISO-8601 date/datetime string into an aware datetime."""
    s = date_str.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    s = s.replace(" ", "T")
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


@lru_cache(maxsize=1)
def get_authority_scorer() -> AuthorityScorer:
    """Return the singleton AuthorityScorer instance (lru_cache-backed)."""
    return AuthorityScorer()