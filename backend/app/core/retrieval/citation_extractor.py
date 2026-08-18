from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Optional
from enum import Enum


class CitationType(Enum):
    """Types of legal citations in Indian law."""
    SUPREME_COURT = "supreme_court"
    HIGH_COURT = "high_court"
    STATUTE = "statute"
    CONSTITUTIONAL = "constitutional"
    REGULATION = "regulation"
    ORDINANCE = "ordinance"
    RULES = "rules"
    NOTIFICATION = "notification"
    CIRCULAR = "circular"
    INTERNATIONAL = "international"
    TRIBUNAL_ORDER = "tribunal_order"
    ADVANCE_RULING = "advance_ruling"
    UNKNOWN = "unknown"


class CourtLevel(Enum):
    """Court hierarchy levels for authority scoring."""
    SUPREME_COURT = 5
    HIGH_COURT = 4
    DISTRICT_COURT = 3
    TRIBUNAL = 2
    FORUM = 1
    UNKNOWN = 0


@dataclass(frozen=True)
class LegalCitation:
    """Structured representation of a legal citation."""
    raw_text: str
    citation_type: CitationType
    court_level: CourtLevel
    normalized: str
    year: Optional[int] = None
    volume: Optional[str] = None
    reporter: Optional[str] = None
    page: Optional[str] = None
    section: Optional[str] = None
    act_name: Optional[str] = None
    article: Optional[str] = None
    jurisdiction: Optional[str] = None
    paragraph: Optional[str] = None
    confidence: float = 1.0

    def to_dict(self) -> dict:
        return {
            "raw_text": self.raw_text,
            "citation_type": self.citation_type.value,
            "court_level": self.court_level.value,
            "normalized": self.normalized,
            "year": self.year,
            "volume": self.volume,
            "reporter": self.reporter,
            "page": self.page,
            "section": self.section,
            "act_name": self.act_name,
            "article": self.article,
            "jurisdiction": self.jurisdiction,
            "paragraph": self.paragraph,
            "confidence": self.confidence,
        }

    @property
    def authority_weight(self) -> float:
        """Compute authority weight based on court hierarchy and citation type."""
        base_weight = self.court_level.value / 5.0
        if self.citation_type in (CitationType.CONSTITUTIONAL, CitationType.STATUTE, CitationType.ORDINANCE):
            return min(1.0, base_weight + 0.2)
        return base_weight


# Indian legal citation patterns based on LeCNet research and standard citation formats
_CITATION_PATTERNS = [
    # Supreme Court: (2023) 5 SCC 123, 2023 SCC OnLine SC 123, AIR 2023 SC 123
    (
        re.compile(
            r'(?:\((?P<year>\d{4})\)|(?P<year2>\d{4}))\s*'
            r'(?P<volume>\d+)?\s*'
            r'(?P<reporter>SCC|SCR|AIR|SCJ|SC\s*OnLine|SCC\s*OnLine)\s*'
            r'(?P<court>SC|Supreme\s*Court)?\s*'
            r'(?P<page>\d+)',
            re.IGNORECASE
        ),
        CitationType.SUPREME_COURT,
        CourtLevel.SUPREME_COURT,
    ),
    # National tribunals: 2023 SCC OnLine NCLAT 123, (2023) ITAT 456
    (
        re.compile(
            r'(?:\((?P<year>\d{4})\)|(?P<year2>\d{4}))\s*'
            r'(?P<volume>\d+)?\s*'
            r'(?:SCC\s*OnLine\s*)?'
            r'(?P<court>NCLAT|NCLT|ITAT|CESTAT|CAT|NGT|SAT|TDSAT|APTEL|NCDRC)\s*'
            r'(?P<page>\d+)',
            re.IGNORECASE
        ),
        CitationType.TRIBUNAL_ORDER,
        CourtLevel.TRIBUNAL,
    ),
    # GST/Income-Tax advance rulings: AAR No. GST-ARA-25/2023-24, AAAR order dated 2023
    (
        re.compile(
            r'(?P<court>AAAR|AAR)\b[^.\n]{0,40}?(?P<section>[A-Z0-9\-\/]+)\s*,?\s*'
            r'(?:dated\s+)?(?P<year>\d{4})?',
            re.IGNORECASE
        ),
        CitationType.ADVANCE_RULING,
        CourtLevel.FORUM,
    ),
    # High Court: 2023 SCC OnLine Del 123, AIR 2023 Del 123, 2023 Del HC 123
    (
        re.compile(
            r'(?:\((?P<year>\d{4})\)|(?P<year2>\d{4}))\s*'
            r'(?P<volume>\d+)?\s*'
            r'(?P<reporter>SCC\s*OnLine|AIR|HC|HCJ)\s*'
            r'(?P<court>[A-Za-z]{2,10})\s*'
            r'(?P<page>\d+)',
            re.IGNORECASE
        ),
        CitationType.HIGH_COURT,
        CourtLevel.HIGH_COURT,
    ),
    # Statute sections: Section 302 IPC, Section 19(1)(a) Constitution
    (
        re.compile(
            r'Section\s+(?P<section>\d+[A-Za-z]?(?:\(\d+\))?(?:\([a-z]\)?)*)\s+'
            r'(?P<act>IPC|CrPC|CPC|Constitution|Evidence\s*Act|Contract\s*Act|'
            r'Companies\s*Act|Income\s*Tax\s*Act|GST\s*Act|SEBI\s*Act|'
            r'RBI\s*Act|Arbitration\s*Act|Limitation\s*Act|Transfer\s*of\s*Property\s*Act|'
            r'Sale\s*of\s*Goods\s*Act|Partnership\s*Act|Negotiable\s*Instruments\s*Act)',
            re.IGNORECASE
        ),
        CitationType.STATUTE,
        CourtLevel.SUPREME_COURT,
    ),
    # Constitutional articles: Article 19, Article 21, Article 19(1)(a)
    (
        re.compile(
            r'Article\s+(?P<article>\d+[A-Za-z]?(?:\(\d+\))?(?:\([a-z]\)?)*)\s+'
            r'(?:of\s+)?(?P<act>the\s+)?Constitution',
            re.IGNORECASE
        ),
        CitationType.CONSTITUTIONAL,
        CourtLevel.SUPREME_COURT,
    ),
    # Regulations/Rules: Rule 3 of the X Rules, 2020
    (
        re.compile(
            r'(?:Rule|Regulation)\s+(?P<section>\d+[A-Za-z]?(?:\(\d+\))?)\s+'
            r'(?:of\s+)?(?P<act>the\s+)?(?P<act_name>[A-Za-z\s]+Rules?|[A-Za-z\s]+Regulations?)',
            re.IGNORECASE
        ),
        CitationType.RULES,
        CourtLevel.DISTRICT_COURT,
    ),
    # Ordinances
    (
        re.compile(
            r'(?P<act_name>[A-Za-z\s]+Ordinance),\s*(?P<year>\d{4})',
            re.IGNORECASE
        ),
        CitationType.ORDINANCE,
        CourtLevel.SUPREME_COURT,
    ),
    # Notifications/Circulars
    (
        re.compile(
            r'(?:Notification|Circular)\s+(?:No\.?\s*)?(?P<section>[\d\/\-]+)\s*,?\s*'
            r'(?:dated\s+)?(?P<year>\d{4})',
            re.IGNORECASE
        ),
        CitationType.NOTIFICATION,
        CourtLevel.TRIBUNAL,
    ),
    # Case citations with v.: A v. B, State v. Accused
    (
        re.compile(
            r'(?P<party1>[A-Za-z\s\.]+)\s+v\.\s+(?P<party2>[A-Za-z\s\.]+)\s*,?\s*'
            r'(?:\((?P<year>\d{4})\)\s*)?(?P<volume>\d+)?\s*'
            r'(?P<reporter>SCC|SCR|AIR|SCJ|SCC\s*OnLine|HC|HCJ)\s*'
            r'(?P<court>SC|[A-Za-z]{2,10})?\s*'
            r'(?P<page>\d+)',
            re.IGNORECASE
        ),
        CitationType.SUPREME_COURT,
        CourtLevel.SUPREME_COURT,
    ),
    # Parliamentary Acts: The X Act, 2023
    (
        re.compile(
            r'(?:The\s+)?(?P<act_name>[A-Za-z\s]+Act),\s*(?P<year>\d{4})',
            re.IGNORECASE
        ),
        CitationType.STATUTE,
        CourtLevel.SUPREME_COURT,
    ),
]


_JURISDICTION_MAP = {
    'SC': 'India',
    'Supreme Court': 'India',
    'Del': 'Delhi', 'Bom': 'Bombay', 'Cal': 'Calcutta', 'Mad': 'Madras',
    'All': 'Allahabad', 'Pat': 'Patna', 'Gau': 'Gauhati', 'Ker': 'Kerala',
    'Kar': 'Karnataka', 'Tel': 'Telangana', 'AP': 'Andhra Pradesh',
    'MP': 'Madhya Pradesh', 'Raj': 'Rajasthan', 'Guj': 'Gujarat',
    'Ori': 'Orissa', 'Pun': 'Punjab', 'Har': 'Haryana',
    'Utt': 'Uttarakhand', 'Jha': 'Jharkhand', 'Chh': 'Chhattisgarh',
    'Nag': 'Nagaland', 'Miz': 'Mizoram', 'Megh': 'Meghalaya',
    'Trip': 'Tripura', 'Mani': 'Manipur', 'Sik': 'Sikkim',
}


def _normalize_reporter(reporter: str) -> str:
    """Normalize reporter abbreviations."""
    reporter = reporter.upper().replace('.', '').replace(' ', '')
    mapping = {
        'SCC': 'SCC', 'SCR': 'SCR', 'AIR': 'AIR', 'SCJ': 'SCJ',
        'SCC ONLINE': 'SCC OnLine', 'SCC ONLINE SC': 'SCC OnLine SC',
        'SCC ONLINE DEL': 'SCC OnLine Del', 'HC': 'HC', 'HCJ': 'HCJ',
    }
    return mapping.get(reporter, reporter)


def _normalize_court(court: Optional[str]) -> Optional[str]:
    """Normalize court abbreviations."""
    if not court:
        return None
    court = court.strip().upper()
    return _JURISDICTION_MAP.get(court, court)


def extract_citations(text: str) -> list[LegalCitation]:
    """
    Extract structured legal citations from text.
    
    Based on LeCNet (Indian Legal Citation Network) methodology and
    standard Indian legal citation formats (SCC, AIR, SCR, etc.).
    
    Args:
        text: Raw text containing legal citations
        
    Returns:
        List of structured LegalCitation objects
    """
    if not text:
        return []
    
    citations = []
    seen = set()
    
    for pattern, cite_type, court_level in _CITATION_PATTERNS:
        for match in pattern.finditer(text):
            raw = match.group(0).strip()
            if raw in seen:
                continue
            seen.add(raw)
            
            groups = match.groupdict()
            
            # Extract year
            year = None
            if groups.get('year'):
                year = int(groups['year'])
            elif groups.get('year2'):
                year = int(groups['year2'])
            
            # Extract volume
            volume = groups.get('volume')
            
            # Normalize reporter
            reporter = _normalize_reporter(groups.get('reporter', ''))
            
            # Normalize court/jurisdiction
            court = _normalize_court(groups.get('court'))
            jurisdiction = court
            
            # Build normalized citation
            parts = []
            if year:
                parts.append(f"({year})")
            if volume:
                parts.append(volume)
            if reporter:
                parts.append(reporter)
            if court:
                parts.append(court)
            if groups.get('page'):
                parts.append(groups['page'])
            normalized = ' '.join(parts)
            
            # Determine citation type more precisely
            final_type = cite_type
            if cite_type == CitationType.STATUTE and groups.get('act'):
                act = groups['act'].lower()
                if 'constitution' in act:
                    final_type = CitationType.CONSTITUTIONAL
            
            citation = LegalCitation(
                raw_text=raw,
                citation_type=final_type,
                court_level=court_level,
                normalized=normalized,
                year=year,
                volume=volume,
                reporter=reporter,
                page=groups.get('page'),
                section=groups.get('section'),
                act_name=groups.get('act') or groups.get('act_name'),
                article=groups.get('article'),
                jurisdiction=jurisdiction,
                paragraph=groups.get('paragraph'),
                confidence=0.9 if year and reporter else 0.7,
            )
            citations.append(citation)
    
    # Sort by position in text
    citations.sort(key=lambda c: text.find(c.raw_text))
    return citations


def extract_citation_context(text: str, window: int = 200) -> list[dict]:
    """
    Extract citations with surrounding context for verification.
    
    Returns list of dicts with citation, preceding_text, following_text.
    """
    citations = extract_citations(text)
    results = []
    
    for cite in citations:
        pos = text.find(cite.raw_text)
        if pos == -1:
            continue
        start = max(0, pos - window)
        end = min(len(text), pos + len(cite.raw_text) + window)
        results.append({
            'citation': cite.to_dict(),
            'preceding_text': text[start:pos],
            'following_text': text[pos + len(cite.raw_text):end],
            'full_context': text[start:end],
        })
    
    return results


def get_citation_graph_edges(citations: list[LegalCitation]) -> list[tuple[str, str, float]]:
    """
    Build citation graph edges from extracted citations.
    
    Returns list of (citing_case, cited_case, weight) tuples.
    Used for PageRank authority computation.
    """
    edges = []
    for i, cite in enumerate(citations):
        if cite.citation_type in (CitationType.SUPREME_COURT, CitationType.HIGH_COURT):
            # This citation cites another case
            # In practice, would need document-level citation extraction
            # Here we create edges based on citation presence
            cited = cite.normalized
            citing = f"doc_{i}"  # Would be actual document ID in practice
            edges.append((citing, cited, cite.authority_weight))
    return edges