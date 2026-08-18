from __future__ import annotations
from functools import lru_cache
from dataclasses import dataclass
from typing import Optional
from enum import Enum
import numpy as np
from sentence_transformers import SentenceTransformer
from app.config.settings import settings


class LegalIntent(Enum):
    """Legal query intent categories based on JUST-NLP 2025 and LegalBench taxonomies."""
    STATUTE_LOOKUP = "statute_lookup"              # "Section 302 IPC punishment"
    CASE_LAW_SEARCH = "case_law_search"            # "Supreme Court judgment on privacy"
    PROCEDURAL_QUERY = "procedural_query"          # "How to file writ petition"
    PRECEDENT_ANALYSIS = "precedent_analysis"      # "Overruling of Kesavananda Bharati"
    CONSTITUTIONAL_INTERPRETATION = "constitutional_interpretation"  # "Article 19 scope"
    DRAFTING_REQUEST = "drafting_request"          # "Draft bail application"
    COMPARATIVE_ANALYSIS = "comparative_analysis"  # "Difference between Art 19 and 21"
    LEGAL_DEFINITION = "legal_definition"          # "Define mens rea"
    JURISDICTION_QUERY = "jurisdiction_query"      # "Which court has jurisdiction"
    TIMELINE_LIMITATION = "timeline_limitation"    # "Limitation period for appeal"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class IntentResult:
    """Intent classification result with confidence."""
    intent: LegalIntent
    confidence: float
    all_scores: dict[str, float]
    routing_hint: str  # Which retrieval strategy to use


# Intent descriptions for embedding-based classification (zero-shot)
_INTENT_DESCRIPTIONS = {
    LegalIntent.STATUTE_LOOKUP: "Query asking for specific statutory provision, section, or act text",
    LegalIntent.CASE_LAW_SEARCH: "Query searching for court judgments, precedents, or case law",
    LegalIntent.PROCEDURAL_QUERY: "Query about legal procedure, filing process, or court rules",
    LegalIntent.PRECEDENT_ANALYSIS: "Query analyzing precedent relationships, overruling, or distinguishing cases",
    LegalIntent.CONSTITUTIONAL_INTERPRETATION: "Query about constitutional articles, fundamental rights, or interpretation",
    LegalIntent.DRAFTING_REQUEST: "Query requesting document drafting, petition, or legal writing",
    LegalIntent.COMPARATIVE_ANALYSIS: "Query comparing legal provisions, articles, or judgments",
    LegalIntent.LEGAL_DEFINITION: "Query asking for definition of legal term or concept",
    LegalIntent.JURISDICTION_QUERY: "Query about court jurisdiction, forum, or territorial limits",
    LegalIntent.TIMELINE_LIMITATION: "Query about limitation periods, deadlines, or time limits",
}


# Routing hints for retrieval strategy
_ROUTING_HINTS = {
    LegalIntent.STATUTE_LOOKUP: "statute_index",
    LegalIntent.CASE_LAW_SEARCH: "case_law_index",
    LegalIntent.PROCEDURAL_QUERY: "procedural_index",
    LegalIntent.PRECEDENT_ANALYSIS: "citation_graph",
    LegalIntent.CONSTITUTIONAL_INTERPRETATION: "constitutional_index",
    LegalIntent.DRAFTING_REQUEST: "template_index",
    LegalIntent.COMPARATIVE_ANALYSIS: "hybrid",
    LegalIntent.LEGAL_DEFINITION: "statute_index",
    LegalIntent.JURISDICTION_QUERY: "case_law_index",
    LegalIntent.TIMELINE_LIMITATION: "statute_index",
}


class IntentClassifier:
    """
    Legal intent classifier using legal-domain sentence embeddings.
    
    Based on LegalModernBERT and LEGAL-BERT research (Chalkidis et al., 2020;
    Stammbach & Henderson, 2026) showing domain-adapted encoders outperform
    general models on legal tasks. Uses embedding similarity for zero-shot
    classification, avoiding training data bias.
    """
    
    def __init__(
        self,
        model_name: Optional[str] = None,
        threshold: float = 0.35,
    ):
        self._model_name = model_name or settings.EMBED_MODEL
        self._model = SentenceTransformer(self._model_name)
        self._threshold = threshold
        
        # Pre-compute intent embeddings
        self._intent_labels = list(_INTENT_DESCRIPTIONS.keys())
        self._intent_texts = [_INTENT_DESCRIPTIONS[i] for i in self._intent_labels]
        self._intent_embeddings = self._model.encode(
            self._intent_texts,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
    
    def classify(self, query: str) -> IntentResult:
        """
        Classify legal query intent using embedding similarity.
        
        Zero-shot approach: embed query and compare with intent description
        embeddings. No fine-tuning needed, works out-of-the-box with
        legal-domain embedder.
        """
        if not query or not query.strip():
            return IntentResult(
                intent=LegalIntent.UNKNOWN,
                confidence=0.0,
                all_scores={},
                routing_hint="hybrid",
            )
        
        # Embed query
        query_emb = self._model.encode(
            [query],
            normalize_embeddings=True,
            show_progress_bar=False,
        )[0]
        
        # Compute cosine similarities
        similarities = self._intent_embeddings @ query_emb
        
        # Get top intent
        best_idx = int(np.argmax(similarities))
        best_score = float(similarities[best_idx])
        best_intent = self._intent_labels[best_idx]
        
        # All scores
        all_scores = {
            intent.value: float(score)
            for intent, score in zip(self._intent_labels, similarities)
        }
        
        # Apply threshold
        if best_score < self._threshold:
            best_intent = LegalIntent.UNKNOWN
            best_score = 0.0
        
        routing_hint = _ROUTING_HINTS.get(best_intent, "hybrid")
        
        return IntentResult(
            intent=best_intent,
            confidence=best_score,
            all_scores=all_scores,
            routing_hint=routing_hint,
        )
    
    def classify_batch(self, queries: list[str]) -> list[IntentResult]:
        """Classify multiple queries efficiently."""
        if not queries:
            return []
        
        query_embs = self._model.encode(
            queries,
            normalize_embeddings=True,
            show_progress_bar=False,
            batch_size=32,
        )
        
        results = []
        for query_emb in query_embs:
            similarities = self._intent_embeddings @ query_emb
            best_idx = int(np.argmax(similarities))
            best_score = float(similarities[best_idx])
            best_intent = self._intent_labels[best_idx]
            
            all_scores = {
                intent.value: float(score)
                for intent, score in zip(self._intent_labels, similarities)
            }
            
            if best_score < self._threshold:
                best_intent = LegalIntent.UNKNOWN
                best_score = 0.0
            
            routing_hint = _ROUTING_HINTS.get(best_intent, "hybrid")
            
            results.append(IntentResult(
                intent=best_intent,
                confidence=best_score,
                all_scores=all_scores,
                routing_hint=routing_hint,
            ))
        
        return results


@lru_cache(maxsize=1)
def get_intent_classifier() -> IntentClassifier:
    return IntentClassifier()


# Keyword-based fallback for edge cases (no model loading needed)
_INTENT_KEYWORDS = {
    LegalIntent.STATUTE_LOOKUP: [
        "section", "provision", "act", "statute", "rule", "regulation",
        "ipc", "crpc", "cpc", "constitution", "evidence act", "contract act"
    ],
    LegalIntent.CASE_LAW_SEARCH: [
        "judgment", "case", "precedent", "supreme court", "high court",
        "ruling", "decision", "order", "bench", "justice", "v.", "vs"
    ],
    LegalIntent.PROCEDURAL_QUERY: [
        "how to", "procedure", "file", "filing", "process", "steps",
        "writ petition", "appeal", "revision", "review", "application"
    ],
    LegalIntent.PRECEDENT_ANALYSIS: [
        "overruled", "distinguished", "followed", "cited", "precedent",
        "stare decisis", "binding", "persuasive", "authority"
    ],
    LegalIntent.CONSTITUTIONAL_INTERPRETATION: [
        "article", "fundamental right", "constitution", "amendment",
        "directive principle", "basic structure", "judicial review"
    ],
    LegalIntent.DRAFTING_REQUEST: [
        "draft", "prepare", "write", "format", "template", "petition",
        "application", "affidavit", "plaint", "written statement"
    ],
    LegalIntent.COMPARATIVE_ANALYSIS: [
        "difference", "compare", "versus", "vs", "distinction", "contrast",
        "similar", "unlike", "better", "preferable"
    ],
    LegalIntent.LEGAL_DEFINITION: [
        "define", "definition", "meaning", "what is", "what does", "explain"
    ],
    LegalIntent.JURISDICTION_QUERY: [
        "jurisdiction", "forum", "court", "territorial", "pecuniary",
        "subject matter", "which court", "where to file"
    ],
    LegalIntent.TIMELINE_LIMITATION: [
        "limitation", "period", "time limit", "deadline", "within",
        "days", "months", "years", "prescribed", "statute of limitation"
    ],
}


def classify_intent_keywords(query: str) -> IntentResult:
    """
    Fast keyword-based intent classification fallback.
    Used when embedder is unavailable or for quick routing.
    """
    if not query:
        return IntentResult(
            intent=LegalIntent.UNKNOWN,
            confidence=0.0,
            all_scores={},
            routing_hint="hybrid",
        )
    
    query_lower = query.lower()
    scores = {}
    
    for intent, keywords in _INTENT_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in query_lower)
        if score > 0:
            # Normalize by keyword count
            scores[intent.value] = score / len(keywords)
    
    if not scores:
        return IntentResult(
            intent=LegalIntent.UNKNOWN,
            confidence=0.0,
            all_scores={},
            routing_hint="hybrid",
        )
    
    best_intent = max(scores, key=scores.get)
    best_score = scores[best_intent]
    
    return IntentResult(
        intent=LegalIntent(best_intent),
        confidence=min(best_score * 2, 1.0),  # Scale up
        all_scores=scores,
        routing_hint=_ROUTING_HINTS.get(LegalIntent(best_intent), "hybrid"),
    )