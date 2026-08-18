"""Evaluation pipeline for legal RAG system.

Based on LegalBench-RAG methodology (Pipitone et al., 2024):
- Precise snippet extraction evaluation (not document-level)
- Recall@k, Precision@k, MRR, NDCG metrics
- Span-level ground truth matching
- Chunking strategy impact analysis
- Reranker effectiveness measurement

Also incorporates:
- IN-ABS / AILA benchmark methodology for Indian legal QA
- CLERC: Case Law Evaluation Retrieval Corpus metrics
- LexRAG multi-turn evaluation framework
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum
import json
import time
import statistics
from pathlib import Path
from app.config.settings import settings


class EvalMetric(Enum):
    RECALL = "recall"
    PRECISION = "precision"
    MRR = "mrr"              # Mean Reciprocal Rank
    NDCG = "ndcg"            # Normalized Discounted Cumulative Gain
    HIT_RATE = "hit_rate"    # At least one relevant in top-k
    GROUNDEDNESS = "groundedness"
    LATENCY = "latency"


@dataclass
class RetrievalExample:
    """Single evaluation example with query and ground truth."""
    query: str
    query_id: str
    relevant_spans: list[dict]  # List of {"source": str, "page": int, "text": str, "char_start": int, "char_end": int}
    intent: Optional[str] = None
    difficulty: str = "medium"  # easy, medium, hard
    metadata: dict = field(default_factory=dict)


@dataclass
class RetrievalResult:
    """Result of retrieval for a single query."""
    query_id: str
    retrieved_chunks: list[dict]  # List of {"source": str, "page": int, "text": str, "score": float, "rank": int}
    latency_ms: float
    intent: Optional[str] = None


@dataclass
class EvaluationResult:
    """Complete evaluation results."""
    metric_scores: dict[EvalMetric, float]
    per_query_results: list[dict]
    summary: str
    config: dict
    timestamp: str


class SpanMatcher:
    """Match retrieved chunks to ground truth spans (LegalBench-RAG methodology)."""
    
    def __init__(self, iou_threshold: float = 0.5, text_overlap_threshold: float = 0.3):
        self._iou_threshold = iou_threshold
        self._text_overlap_threshold = text_overlap_threshold
    
    def _text_overlap(self, text1: str, text2: str) -> float:
        """Compute Jaccard similarity of word sets."""
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        if not words1 or not words2:
            return 0.0
        intersection = len(words1 & words2)
        union = len(words1 | words2)
        return intersection / union if union > 0 else 0.0
    
    def _span_overlap(self, span1: dict, span2: dict) -> float:
        """Compute character-level IOU for spans in same document."""
        if span1.get("source") != span2.get("source") or span1.get("page") != span2.get("page"):
            return 0.0
        
        start1, end1 = span1.get("char_start", 0), span1.get("char_end", 0)
        start2, end2 = span2.get("char_start", 0), span2.get("char_end", 0)
        
        if start1 >= end1 or start2 >= end2:
            return 0.0
        
        inter_start = max(start1, start2)
        inter_end = min(end1, end2)
        intersection = max(0, inter_end - inter_start)
        
        union_start = min(start1, start2)
        union_end = max(end1, end2)
        union = union_end - union_start
        
        return intersection / union if union > 0 else 0.0
    
    def match(self, retrieved: dict, ground_truth: list[dict]) -> tuple[bool, float, Optional[dict]]:
        """
        Match a retrieved chunk to ground truth spans.
        
        Returns: (is_match, best_score, matched_gt_span)
        """
        best_score = 0.0
        best_match = None
        
        for gt in ground_truth:
            # Try span IOU first (for same document)
            span_score = self._span_overlap(retrieved, gt)
            
            # Fallback to text overlap
            text_score = self._text_overlap(
                retrieved.get("text", ""),
                gt.get("text", "")
            )
            
            score = max(span_score, text_score)
            
            if score > best_score:
                best_score = score
                best_match = gt
        
        is_match = best_score >= max(self._iou_threshold, self._text_overlap_threshold)
        return is_match, best_score, best_match


class RetrievalEvaluator:
    """
    Legal RAG retrieval evaluator following LegalBench-RAG methodology.
    
    Key principles from LegalBench-RAG:
    1. Evaluate at span level, not document level
    2. Use precise snippet extraction (character-level spans)
    3. Weight metrics equally across query types
    4. Test multiple chunking strategies
    4. Evaluate reranker impact separately
    """
    
    def __init__(
        self,
        iou_threshold: float = 0.5,
        text_overlap_threshold: float = 0.3,
        k_values: list[int] = None,
    ):
        self._matcher = SpanMatcher(iou_threshold, text_overlap_threshold)
        self._k_values = k_values or [1, 3, 5, 10, 20]
    
    def evaluate_retrieval(
        self,
        examples: list[RetrievalExample],
        results: list[RetrievalResult],
    ) -> EvaluationResult:
        """Evaluate retrieval results against ground truth."""
        
        per_query = []
        # Use string keys for all metrics (includes recall@k, precision@k, etc.)
        all_metrics = {}
        
        # Initialize with base metrics
        base_metrics = [m.value for m in EvalMetric if m != EvalMetric.LATENCY]
        for k in self._k_values:
            base_metrics.extend([f"recall@{k}", f"precision@{k}", f"hit_rate@{k}"])
        for m in base_metrics:
            all_metrics[m] = []
        
        # Build lookup for results
        result_map = {r.query_id: r for r in results}
        
        for example in examples:
            result = result_map.get(example.query_id)
            if not result:
                continue
            
            query_metrics = self._evaluate_single(example, result)
            per_query.append({
                "query_id": example.query_id,
                "query": example.query,
                "intent": example.intent,
                "difficulty": example.difficulty,
                "metrics": query_metrics,
                "num_relevant": len(example.relevant_spans),
                "num_retrieved": len(result.retrieved_chunks),
            })
            
            for metric, value in query_metrics.items():
                if metric not in all_metrics:
                    all_metrics[metric] = []
                all_metrics[metric].append(value)
        
        # Aggregate metrics (macro-average across queries)
        aggregated = {}
        for metric, values in all_metrics.items():
            if values:
                aggregated[metric] = statistics.mean(values)
            else:
                aggregated[metric] = 0.0
        
        # Latency
        latencies = [r.latency_ms for r in results]
        aggregated[EvalMetric.LATENCY.value] = statistics.mean(latencies) if latencies else 0.0
        
        # Summary
        summary = self._generate_summary(aggregated, len(examples))
        
        return EvaluationResult(
            metric_scores=aggregated,
            per_query_results=per_query,
            summary=summary,
            config={
                "iou_threshold": self._matcher._iou_threshold,
                "text_overlap_threshold": self._matcher._text_overlap_threshold,
                "k_values": self._k_values,
                "num_examples": len(examples),
            },
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
        )
    
    def _evaluate_single(
        self,
        example: RetrievalExample,
        result: RetrievalResult,
    ) -> dict[EvalMetric, float]:
        """Evaluate retrieval for a single query."""
        relevant = example.relevant_spans
        retrieved = result.retrieved_chunks
        
        if not relevant:
            return {metric: 0.0 for metric in EvalMetric if metric != EvalMetric.LATENCY}
        
        # Match each retrieved chunk
        matches = []
        matched_gt_indices = set()
        
        for i, chunk in enumerate(retrieved):
            is_match, score, matched_gt = self._matcher.match(chunk, relevant)
            matches.append({
                "rank": i + 1,
                "is_relevant": is_match,
                "score": score,
                "matched_gt": matched_gt,
            })
            if is_match and matched_gt:
                # Find index in relevant
                for j, gt in enumerate(relevant):
                    if gt is matched_gt:
                        matched_gt_indices.add(j)
                        break
        
        metrics = {}
        
        # Recall@k, Precision@k, Hit Rate@k
        for k in self._k_values:
            top_k = matches[:k]
            relevant_in_k = sum(1 for m in top_k if m["is_relevant"])
            retrieved_in_k = len(top_k)
            
            recall = relevant_in_k / len(relevant) if relevant else 0.0
            precision = relevant_in_k / retrieved_in_k if retrieved_in_k > 0 else 0.0
            hit_rate = 1.0 if relevant_in_k > 0 else 0.0
            
            metrics[f"recall@{k}"] = recall
            metrics[f"precision@{k}"] = precision
            metrics[f"hit_rate@{k}"] = hit_rate
        
        # Overall metrics (using full retrieved list)
        total_relevant_retrieved = sum(1 for m in matches if m["is_relevant"])
        metrics[EvalMetric.RECALL] = total_relevant_retrieved / len(relevant) if relevant else 0.0
        metrics[EvalMetric.PRECISION] = total_relevant_retrieved / len(retrieved) if retrieved else 0.0
        metrics[EvalMetric.HIT_RATE] = 1.0 if total_relevant_retrieved > 0 else 0.0
        
        # MRR (Mean Reciprocal Rank)
        mrr = 0.0
        for m in matches:
            if m["is_relevant"]:
                mrr = 1.0 / m["rank"]
                break
        metrics[EvalMetric.MRR] = mrr
        
        # NDCG
        metrics[EvalMetric.NDCG] = self._compute_ndcg(matches, len(relevant))
        
        return metrics
    
    def _compute_ndcg(self, matches: list[dict], num_relevant: int) -> float:
        """Compute NDCG@k for full ranking."""
        if not matches:
            return 0.0
        
        # DCG
        dcg = 0.0
        for m in matches:
            rel = 1.0 if m["is_relevant"] else 0.0
            dcg += rel / math.log2(m["rank"] + 1)
        
        # IDCG (ideal ranking: all relevant first)
        idcg = 0.0
        for i in range(min(num_relevant, len(matches))):
            idcg += 1.0 / math.log2(i + 2)
        
        return dcg / idcg if idcg > 0 else 0.0
    
    def _generate_summary(self, metrics: dict, num_queries: int) -> str:
        """Generate human-readable summary."""
        parts = [f"Evaluated {num_queries} queries"]
        
        for k in self._k_values:
            r_key, p_key = f"recall@{k}", f"precision@{k}"
            if r_key in metrics and p_key in metrics:
                parts.append(f"R@{k}={metrics[r_key]:.3f} P@{k}={metrics[p_key]:.3f}")
        
        if EvalMetric.MRR in metrics:
            parts.append(f"MRR={metrics[EvalMetric.MRR]:.3f}")
        if EvalMetric.NDCG in metrics:
            parts.append(f"NDCG={metrics[EvalMetric.NDCG]:.3f}")
        
        return " | ".join(parts)


class EndToEndEvaluator:
    """
    End-to-end evaluation including generation and verification.
    
    Based on LRAGE (Legal RAG Evaluation) framework - holistic evaluation
    across retrieval, generation, and verification stages.
    """
    
    def __init__(self):
        from app.core.retrieval.claim_verifier import get_claim_verifier
        self._claim_verifier = get_claim_verifier()
        self._retrieval_evaluator = RetrievalEvaluator()
    
    def evaluate(
        self,
        examples: list[RetrievalExample],
        pipeline_results: list[dict],  # Each dict: query_id, answer, verification, retrieved_chunks, latency_ms
    ) -> dict:
        """Evaluate full pipeline: retrieval + generation + verification."""
        
        # Retrieval evaluation
        retrieval_results = [
            RetrievalResult(
                query_id=r["query_id"],
                retrieved_chunks=r["retrieved_chunks"],
                latency_ms=r.get("retrieval_latency_ms", r.get("latency_ms", 0)),
            )
            for r in pipeline_results
        ]
        
        retrieval_eval = self._retrieval_evaluator.evaluate_retrieval(examples, retrieval_results)
        
        # Generation/Verification evaluation
        gen_metrics = {
            "groundedness": [],
            "verification_verdict": [],
            "claims_per_answer": [],
            "supported_claims_ratio": [],
            "answer_length": [],
        }
        
        for r in pipeline_results:
            verification = r.get("verification", {})
            if verification:
                gen_metrics["groundedness"].append(verification.get("groundedness_score", 0))
                gen_metrics["verification_verdict"].append(verification.get("verdict", "unknown"))
                
                claim_vers = verification.get("claim_verifications", [])
                gen_metrics["claims_per_answer"].append(len(claim_vers))
                if claim_vers:
                    supported = sum(1 for cv in claim_vers if cv.get("verdict") == "supported")
                    gen_metrics["supported_claims_ratio"].append(supported / len(claim_vers))
            
            answer = r.get("answer", "")
            gen_metrics["answer_length"].append(len(answer))
        
        # Aggregate
        results = {
            "retrieval": {
                "metrics": {m.value: v for m, v in retrieval_eval.metric_scores.items()},
                "summary": retrieval_eval.summary,
            },
            "generation": {
                "mean_groundedness": statistics.mean(gen_metrics["groundedness"]) if gen_metrics["groundedness"] else 0,
                "verdict_distribution": self._count_distribution(gen_metrics["verification_verdict"]),
                "mean_claims_per_answer": statistics.mean(gen_metrics["claims_per_answer"]) if gen_metrics["claims_per_answer"] else 0,
                "mean_supported_ratio": statistics.mean(gen_metrics["supported_claims_ratio"]) if gen_metrics["supported_claims_ratio"] else 0,
                "mean_answer_length": statistics.mean(gen_metrics["answer_length"]) if gen_metrics["answer_length"] else 0,
            },
            "pipeline_latency_ms": statistics.mean([r.get("latency_ms", 0) for r in pipeline_results]) if pipeline_results else 0,
        }
        
        return results
    
    def _count_distribution(self, items: list[str]) -> dict[str, int]:
        dist = {}
        for item in items:
            dist[item] = dist.get(item, 0) + 1
        return dist


class ChunkingStrategyEvaluator:
    """
    Evaluate impact of chunking strategies (LegalBench-RAG methodology).
    
    Tests different chunking approaches:
    - Fixed-size sliding window
    - Markdown heading-based
    - Semantic chunking (embedding-based)
    - Summary-augmented chunking (SAC)
    """
    
    def __init__(self, evaluator: RetrievalEvaluator):
        self._evaluator = evaluator
    
    def evaluate_strategies(
        self,
        examples: list[RetrievalExample],
        strategy_results: dict[str, list[RetrievalResult]],
    ) -> dict:
        """Compare retrieval performance across chunking strategies."""
        
        results = {}
        for strategy_name, results_list in strategy_results.items():
            eval_result = self._evaluator.evaluate_retrieval(examples, results_list)
            results[strategy_name] = {
                "metrics": {m.value: v for m, v in eval_result.metric_scores.items()},
                "summary": eval_result.summary,
            }
        
        # Rank strategies
        ranked = sorted(
            results.items(),
            key=lambda x: x[1]["metrics"].get(EvalMetric.RECALL.value, 0),
            reverse=True
        )
        
        return {
            "strategies": results,
            "ranking": [name for name, _ in ranked],
            "best_strategy": ranked[0][0] if ranked else None,
        }


# LegalBench-RAG style dataset loader
class LegalBenchRAGDataset:
    """Load and manage LegalBench-RAG style evaluation datasets."""
    
    def __init__(self, data_path: str | Path):
        self._data_path = Path(data_path)
        self._examples: list[RetrievalExample] = []
    
    def load(self) -> list[RetrievalExample]:
        """Load evaluation examples from JSON/JSONL files."""
        if self._data_path.is_file():
            self._load_file(self._data_path)
        elif self._data_path.is_dir():
            for file in self._data_path.glob("*.json*"):
                self._load_file(file)
        return self._examples
    
    def _load_file(self, path: Path) -> None:
        """Load examples from a single file."""
        with open(path) as f:
            if path.suffix == ".jsonl":
                for line in f:
                    if line.strip():
                        self._examples.append(self._parse_example(json.loads(line)))
            else:
                data = json.load(f)
                if isinstance(data, list):
                    for item in data:
                        self._examples.append(self._parse_example(item))
                else:
                    self._examples.append(self._parse_example(data))
    
    def _parse_example(self, data: dict) -> RetrievalExample:
        """Parse raw data into RetrievalExample."""
        return RetrievalExample(
            query=data["query"],
            query_id=data.get("query_id", data.get("id", "")),
            relevant_spans=data.get("relevant_spans", data.get("gold_spans", [])),
            intent=data.get("intent"),
            difficulty=data.get("difficulty", "medium"),
            metadata=data.get("metadata", {}),
        )
    
    def filter_by_intent(self, intent: str) -> list[RetrievalExample]:
        """Filter examples by intent category."""
        return [ex for ex in self._examples if ex.intent == intent]
    
    def filter_by_difficulty(self, difficulty: str) -> list[RetrievalExample]:
        """Filter examples by difficulty level."""
        return [ex for ex in self._examples if ex.difficulty == difficulty]
    
    def get_stats(self) -> dict:
        """Get dataset statistics."""
        return {
            "total_examples": len(self._examples),
            "by_intent": self._count_field("intent"),
            "by_difficulty": self._count_field("difficulty"),
            "avg_relevant_spans": statistics.mean(
                len(ex.relevant_spans) for ex in self._examples
            ) if self._examples else 0,
        }
    
    def _count_field(self, field: str) -> dict[str, int]:
        counts = {}
        for ex in self._examples:
            val = getattr(ex, field, "unknown")
            counts[val] = counts.get(val, 0) + 1
        return counts


# Import math for NDCG
import math