from __future__ import annotations
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Optional
from enum import Enum
import re
import json
import asyncio
from app.core.llm.provider import get_llm
from app.core.retrieval.citation_extractor import extract_citations, LegalCitation
from app.config.settings import settings
from app.core.prompts.claim_verifier import (
    CLAIM_EXTRACTION_PROMPT,
    CLAIM_VERIFICATION_PROMPT,
    GROUNDEDNESS_PROMPT,
)


class VerificationVerdict(Enum):
    SUPPORTED = "supported"
    PARTIALLY_SUPPORTED = "partially_supported"
    REFUTED = "refuted"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    CONFLICTING_EVIDENCE = "conflicting_evidence"


class ClaimType(Enum):
    STATUTORY = "statutory"           # "Section 302 IPC provides death penalty"
    CASE_LAW = "case_law"             # "Supreme Court held in XYZ that..."
    PROCEDURAL = "procedural"         # "Writ petition must be filed within 90 days"
    DEFINITIONAL = "definitional"     # "Mens rea means guilty mind"
    FACTUAL = "factual"               # "The case was decided in 2023"
    COMPARATIVE = "comparative"       # "Article 19 is broader than Article 21"


@dataclass(frozen=True)
class AtomicClaim:
    """Single atomic claim extracted from answer."""
    text: str
    claim_type: ClaimType
    citations: list[LegalCitation] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    span: tuple[int, int] = (0, 0)


@dataclass(frozen=True)
class ClaimVerification:
    """Verification result for a single claim."""
    claim: AtomicClaim
    verdict: VerificationVerdict
    confidence: float
    supporting_evidence: list[str] = field(default_factory=list)
    refuting_evidence: list[str] = field(default_factory=list)
    explanation: str = ""
    matched_citation: Optional[LegalCitation] = None


@dataclass(frozen=True)
class AnswerVerification:
    """Complete verification result for an answer."""
    overall_verdict: VerificationVerdict
    overall_confidence: float
    claim_verifications: list[ClaimVerification]
    groundedness_score: float
    summary: str
    unsupported_claims: list[str] = field(default_factory=list)


class ClaimVerifier:
    """
    Atomic claim extraction and verification against evidence.
    
    Based on:
    - InFact (Chen et al., NAACL 2024): 6-stage claim verification with evidence retrieval
    - LegalReasoner (Shi et al., 2025): Step-wise verification-correction for legal reasoning
    - FACTIFY-5WQA (Rani et al., 2023): 5W question-answering for fact verification
    - Step-by-step verification (EmergentMind survey, 2025): Decompose → Verify → Aggregate
    
    Key principles:
    1. Decompose answer into atomic, independently verifiable claims
    2. Verify each claim against retrieved evidence
    3. Aggregate claim-level verdicts into overall groundedness
    4. Provide explanations and evidence citations for each verdict
    """
    
    def __init__(self):
        self._llm = get_llm()
    
    async def extract_claims(self, answer: str) -> list[AtomicClaim]:
        """
        Extract atomic claims from answer using LLM.

        Uses structured prompt based on InFact claim decomposition methodology.
        """
        if not answer or not answer.strip():
            return []

        prompt = CLAIM_EXTRACTION_PROMPT.format(answer=answer)

        try:
            from langchain_core.messages import HumanMessage
            resp = await self._llm.ainvoke([HumanMessage(content=prompt)])
            content = getattr(resp, "content", "") or ""
            
            # Parse JSON from response
            claims_data = self._parse_json_array(content)
            
            claims = []
            for i, claim_data in enumerate(claims_data):
                claim_text = claim_data.get("text", "").strip()
                if not claim_text:
                    continue
                
                # Find span in original answer
                start = answer.find(claim_text)
                end = start + len(claim_text) if start != -1 else 0
                
                # Extract citations from claim
                citations = extract_citations(claim_text)
                
                # Determine claim type
                claim_type_str = claim_data.get("type", "factual")
                try:
                    claim_type = ClaimType(claim_type_str)
                except ValueError:
                    claim_type = ClaimType.FACTUAL
                
                entities = claim_data.get("entities", [])
                
                claims.append(AtomicClaim(
                    text=claim_text,
                    claim_type=claim_type,
                    citations=citations,
                    entities=entities,
                    span=(start, end),
                ))
            
            return claims
            
        except Exception as e:
            # Fallback: simple sentence splitting
            return self._fallback_claim_extraction(answer)
    
    def _parse_json_array(self, text: str) -> list[dict]:
        """Extract JSON array from LLM response."""
        text = text.strip()
        # Find first [ and last ]
        start = text.find('[')
        end = text.rfind(']')
        if start != -1 and end != -1 and end > start:
            json_str = text[start:end+1]
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                pass
        # Try direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return []
    
    def _fallback_claim_extraction(self, answer: str) -> list[AtomicClaim]:
        """Fallback: split by sentences and treat each as a claim."""
        # Simple sentence splitting on legal text
        sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', answer)
        claims = []
        for sent in sentences:
            sent = sent.strip()
            if len(sent) < 20:  # Too short to be meaningful
                continue
            citations = extract_citations(sent)
            claims.append(AtomicClaim(
                text=sent,
                claim_type=ClaimType.FACTUAL,
                citations=citations,
                entities=[],
                span=(0, 0),
            ))
        return claims
    
    async def verify_claim(self, claim: AtomicClaim, evidence: list[dict]) -> ClaimVerification:
        """
        Verify a single claim against evidence.
        
        Uses LLM to assess support/refutation based on evidence.
        """
        if not evidence:
            return ClaimVerification(
                claim=claim,
                verdict=VerificationVerdict.INSUFFICIENT_EVIDENCE,
                confidence=0.0,
                explanation="No evidence provided for verification",
            )
        
        # Format evidence for prompt
        evidence_texts = []
        for i, ev in enumerate(evidence):
            src = ev.get("source", f"Source {i+1}")
            txt = ev.get("text", ev.get("content", ""))
            evidence_texts.append(f"[{i+1}] {src}: {txt[:1500]}")
        
        evidence_str = "\n\n".join(evidence_texts)
        
        prompt = CLAIM_VERIFICATION_PROMPT.format(
            claim=claim.text,
            claim_type=claim.claim_type.value,
            evidence=evidence_str,
        )
        
        try:
            from langchain_core.messages import HumanMessage
            resp = await self._llm.ainvoke([HumanMessage(content=prompt)])
            content = getattr(resp, "content", "") or ""

            result = self._parse_json_object(content)
            
            verdict_str = result.get("verdict", "insufficient_evidence")
            try:
                verdict = VerificationVerdict(verdict_str)
            except ValueError:
                verdict = VerificationVerdict.INSUFFICIENT_EVIDENCE
            
            confidence = float(result.get("confidence", 0.5))
            supporting = result.get("supporting_evidence", [])
            refuting = result.get("refuting_evidence", [])
            explanation = result.get("explanation", "")
            
            # Parse matched citation
            matched_cite = None
            cite_data = result.get("matched_citation")
            if cite_data and isinstance(cite_data, dict):
                try:
                    matched_cite = LegalCitation(
                        raw_text=cite_data.get("raw_text", ""),
                        citation_type=LegalCitation.__annotations__["citation_type"].__args__[0](cite_data.get("citation_type", "unknown")),
                        court_level=LegalCitation.__annotations__["court_level"].__args__[0](cite_data.get("court_level", 0)),
                        normalized=cite_data.get("normalized", ""),
                    )
                except Exception:
                    pass
            
            return ClaimVerification(
                claim=claim,
                verdict=verdict,
                confidence=confidence,
                supporting_evidence=supporting,
                refuting_evidence=refuting,
                explanation=explanation,
                matched_citation=matched_cite,
            )
            
        except Exception as e:
            return ClaimVerification(
                claim=claim,
                verdict=VerificationVerdict.INSUFFICIENT_EVIDENCE,
                confidence=0.0,
                explanation=f"Verification failed: {str(e)}",
            )
    
    def _parse_json_object(self, text: str) -> dict:
        """Extract JSON object from LLM response."""
        text = text.strip()
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1 and end > start:
            json_str = text[start:end+1]
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                pass
        return {}
    
    async def verify_answer(self, answer: str, evidence: list[dict]) -> AnswerVerification:
        """
        Complete answer verification pipeline.

        1. Extract atomic claims from answer
        2. Verify each claim against evidence
        3. Aggregate into overall groundedness assessment
        """
        # Step 1: Extract claims
        claims = await self.extract_claims(answer)

        if not claims:
            return AnswerVerification(
                overall_verdict=VerificationVerdict.INSUFFICIENT_EVIDENCE,
                overall_confidence=0.0,
                claim_verifications=[],
                groundedness_score=0.0,
                summary="No verifiable claims found in answer",
            )

        # Step 2: Verify each claim concurrently — was a sequential N+1 LLM
        # call loop, serializing latency on the number of claims extracted.
        verifications = await asyncio.gather(
            *(self.verify_claim(claim, evidence) for claim in claims)
        )

        # Step 3: Aggregate
        overall = self._aggregate_verifications(answer, verifications)
        
        return AnswerVerification(
            overall_verdict=overall["overall_verdict"],
            overall_confidence=overall["overall_confidence"],
            claim_verifications=verifications,
            groundedness_score=overall["groundedness_score"],
            summary=overall["summary"],
            unsupported_claims=overall["unsupported_claims"],
        )
    
    def _aggregate_verifications(
        self,
        answer: str,
        verifications: list[ClaimVerification],
    ) -> dict:
        """Aggregate claim-level verifications into overall assessment."""
        
        # Count verdicts
        verdict_counts = {}
        for v in verifications:
            verdict_counts[v.verdict] = verdict_counts.get(v.verdict, 0) + 1
        
        total = len(verifications)
        supported = verdict_counts.get(VerificationVerdict.SUPPORTED, 0)
        partially = verdict_counts.get(VerificationVerdict.PARTIALLY_SUPPORTED, 0)
        refuted = verdict_counts.get(VerificationVerdict.REFUTED, 0)
        insufficient = verdict_counts.get(VerificationVerdict.INSUFFICIENT_EVIDENCE, 0)
        conflicting = verdict_counts.get(VerificationVerdict.CONFLICTING_EVIDENCE, 0)
        
        # Groundedness = (supported + 0.5 * partially) / total
        groundedness = (supported + 0.5 * partially) / total if total > 0 else 0.0
        
        # Determine overall verdict
        if refuted > 0:
            overall_verdict = VerificationVerdict.REFUTED
        elif conflicting > 0:
            overall_verdict = VerificationVerdict.CONFLICTING_EVIDENCE
        elif supported == total:
            overall_verdict = VerificationVerdict.SUPPORTED
        elif supported + partially > total * 0.5:
            overall_verdict = VerificationVerdict.PARTIALLY_SUPPORTED
        elif insufficient == total:
            overall_verdict = VerificationVerdict.INSUFFICIENT_EVIDENCE
        else:
            overall_verdict = VerificationVerdict.PARTIALLY_SUPPORTED
        
        # Overall confidence
        confidences = [v.confidence for v in verifications]
        overall_confidence = sum(confidences) / len(confidences) if confidences else 0.0
        
        # Unsupported claims
        unsupported = [
            v.claim.text for v in verifications
            if v.verdict in (VerificationVerdict.INSUFFICIENT_EVIDENCE, VerificationVerdict.REFUTED)
        ]
        
        # Summary
        summary_parts = []
        if supported:
            summary_parts.append(f"{supported}/{total} claims fully supported")
        if partially:
            summary_parts.append(f"{partially} partially supported")
        if refuted:
            summary_parts.append(f"{refuted} refuted")
        if insufficient:
            summary_parts.append(f"{insufficient} insufficient evidence")
        if conflicting:
            summary_parts.append(f"{conflicting} conflicting")
        
        summary = "; ".join(summary_parts) + f". Groundedness: {groundedness:.0%}"
        
        return {
            "overall_verdict": overall_verdict,
            "overall_confidence": overall_confidence,
            "groundedness_score": groundedness,
            "summary": summary,
            "unsupported_claims": unsupported,
        }


@lru_cache(maxsize=1)
def get_claim_verifier() -> ClaimVerifier:
    return ClaimVerifier()