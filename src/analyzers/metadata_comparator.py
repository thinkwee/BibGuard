"""
Metadata comparison between bib entries and fetched metadata.
"""
from dataclasses import dataclass
from typing import Optional

from ..parsers.bib_parser import BibEntry
from ..fetchers.arxiv_fetcher import ArxivMetadata
from ..fetchers.scholar_fetcher import ScholarResult
from ..fetchers.crossref_fetcher import CrossRefResult
from ..fetchers.semantic_scholar_fetcher import SemanticScholarResult
from ..fetchers.openalex_fetcher import OpenAlexResult
from ..utils.normalizer import TextNormalizer


@dataclass
class ComparisonResult:
    """Result of comparing bib entry with fetched metadata."""
    entry_key: str
    
    # Title comparison
    title_match: bool
    title_similarity: float
    bib_title: str
    fetched_title: str
    
    # Author comparison
    author_match: bool
    author_similarity: float
    bib_authors: list[str]
    fetched_authors: list[str]
    
    # Year comparison
    year_match: bool
    bib_year: str
    fetched_year: str
    
    # Overall assessment
    is_match: bool
    confidence: float
    issues: list[str]
    source: str  # "arxiv", "semantic_scholar", "openalex", "crossref", "scholar", or "unable"
    
    @property
    def has_issues(self) -> bool:
        return len(self.issues) > 0


class MetadataComparator:
    """Compares bibliography entries with fetched metadata."""
    
    # Thresholds for matching
    TITLE_THRESHOLD = 0.8
    AUTHOR_THRESHOLD = 0.6
    
    def __init__(self):
        self.normalizer = TextNormalizer
    
    def compare_with_arxiv(self, bib_entry: BibEntry, arxiv_meta: ArxivMetadata) -> ComparisonResult:
        """Compare bib entry with arXiv metadata."""
        issues = []
        
        # Compare titles
        bib_title_norm = self.normalizer.normalize_for_comparison(bib_entry.title)
        arxiv_title_norm = self.normalizer.normalize_for_comparison(arxiv_meta.title)
        
        title_similarity = self.normalizer.similarity_ratio(bib_title_norm, arxiv_title_norm)
        # Also try Levenshtein for short titles
        if len(bib_title_norm) < 100:
            lev_sim = self.normalizer.levenshtein_similarity(bib_title_norm, arxiv_title_norm)
            title_similarity = max(title_similarity, lev_sim)
        
        title_match = title_similarity >= self.TITLE_THRESHOLD
        
        if not title_match:
            issues.append(f"Title mismatch (similarity: {title_similarity:.2%})")
        
        # Compare authors
        bib_authors = self.normalizer.normalize_author_list(bib_entry.author)
        arxiv_authors = [self.normalizer.normalize_author_name(a) for a in arxiv_meta.authors]
        
        author_similarity = self._compare_author_lists(bib_authors, arxiv_authors)
        author_match = author_similarity >= self.AUTHOR_THRESHOLD
        
        if not author_match:
            issues.append(f"Author mismatch (similarity: {author_similarity:.2%})")
        
        # Compare years
        bib_year = bib_entry.year.strip()
        arxiv_year = arxiv_meta.year
        year_match = bib_year == arxiv_year
        
        if not year_match and bib_year and arxiv_year:
            issues.append(f"Year mismatch: bib={bib_year}, arxiv={arxiv_year}")
        
        # Overall assessment
        is_match = title_match and author_match
        confidence = (title_similarity * 0.5 + author_similarity * 0.3 + (1.0 if year_match else 0.5) * 0.2)
        
        return ComparisonResult(
            entry_key=bib_entry.key,
            title_match=title_match,
            title_similarity=title_similarity,
            bib_title=bib_entry.title,
            fetched_title=arxiv_meta.title,
            author_match=author_match,
            author_similarity=author_similarity,
            bib_authors=bib_authors,
            fetched_authors=arxiv_authors,
            year_match=year_match,
            bib_year=bib_year,
            fetched_year=arxiv_year,
            is_match=is_match,
            confidence=confidence,
            issues=issues,
            source="arxiv"
        )
    
    def compare_with_scholar(self, bib_entry: BibEntry, scholar_result: ScholarResult) -> ComparisonResult:
        """Compare bib entry with Scholar search result."""
        issues = []
        
        # Compare titles
        bib_title_norm = self.normalizer.normalize_for_comparison(bib_entry.title)
        scholar_title_norm = self.normalizer.normalize_for_comparison(scholar_result.title)
        
        title_similarity = self.normalizer.similarity_ratio(bib_title_norm, scholar_title_norm)
        if len(bib_title_norm) < 100:
            lev_sim = self.normalizer.levenshtein_similarity(bib_title_norm, scholar_title_norm)
            title_similarity = max(title_similarity, lev_sim)
        
        title_match = title_similarity >= self.TITLE_THRESHOLD
        
        if not title_match:
            issues.append(f"Title mismatch (similarity: {title_similarity:.2%})")
        
        # Compare authors (Scholar format is less structured)
        bib_authors = self.normalizer.normalize_author_list(bib_entry.author)
        # Scholar authors are comma-separated
        scholar_authors_raw = scholar_result.authors.split(',')
        scholar_authors = [self.normalizer.normalize_author_name(a.strip()) for a in scholar_authors_raw]
        
        author_similarity = self._compare_author_lists(bib_authors, scholar_authors)
        author_match = author_similarity >= self.AUTHOR_THRESHOLD
        
        if not author_match:
            issues.append(f"Author mismatch (similarity: {author_similarity:.2%})")
        
        # Compare years
        bib_year = bib_entry.year.strip()
        scholar_year = scholar_result.year
        year_match = bib_year == scholar_year
        
        if not year_match and bib_year and scholar_year:
            issues.append(f"Year mismatch: bib={bib_year}, scholar={scholar_year}")
        
        # Overall assessment
        is_match = title_match and author_match
        confidence = (title_similarity * 0.5 + author_similarity * 0.3 + (1.0 if year_match else 0.5) * 0.2)
        
        return ComparisonResult(
            entry_key=bib_entry.key,
            title_match=title_match,
            title_similarity=title_similarity,
            bib_title=bib_entry.title,
            fetched_title=scholar_result.title,
            author_match=author_match,
            author_similarity=author_similarity,
            bib_authors=bib_authors,
            fetched_authors=scholar_authors,
            year_match=year_match,
            bib_year=bib_year,
            fetched_year=scholar_year,
            is_match=is_match,
            confidence=confidence,
            issues=issues,
            source="scholar"
        )
    
    def compare_with_crossref(self, bib_entry: BibEntry, crossref_result: CrossRefResult) -> ComparisonResult:
        """Compare bib entry with CrossRef search result."""
        issues = []
        
        # Compare titles
        bib_title_norm = self.normalizer.normalize_for_comparison(bib_entry.title)
        crossref_title_norm = self.normalizer.normalize_for_comparison(crossref_result.title)
        
        title_similarity = self.normalizer.similarity_ratio(bib_title_norm, crossref_title_norm)
        if len(bib_title_norm) < 100:
            lev_sim = self.normalizer.levenshtein_similarity(bib_title_norm, crossref_title_norm)
            title_similarity = max(title_similarity, lev_sim)
        
        title_match = title_similarity >= self.TITLE_THRESHOLD
        
        if not title_match:
            issues.append(f"Title mismatch (similarity: {title_similarity:.2%})")
        
        # Compare authors
        bib_authors = self.normalizer.normalize_author_list(bib_entry.author)
        crossref_authors = [self.normalizer.normalize_author_name(a) for a in crossref_result.authors]
        
        author_similarity = self._compare_author_lists(bib_authors, crossref_authors)
        author_match = author_similarity >= self.AUTHOR_THRESHOLD
        
        if not author_match:
            issues.append(f"Author mismatch (similarity: {author_similarity:.2%})")
        
        # Compare years
        bib_year = bib_entry.year.strip()
        crossref_year = crossref_result.year
        year_match = bib_year == crossref_year
        
        if not year_match and bib_year and crossref_year:
            issues.append(f"Year mismatch: bib={bib_year}, crossref={crossref_year}")
        
        # Overall assessment
        is_match = title_match and author_match
        confidence = (title_similarity * 0.5 + author_similarity * 0.3 + (1.0 if year_match else 0.5) * 0.2)
        
        return ComparisonResult(
            entry_key=bib_entry.key,
            title_match=title_match,
            title_similarity=title_similarity,
            bib_title=bib_entry.title,
            fetched_title=crossref_result.title,
            author_match=author_match,
            author_similarity=author_similarity,
            bib_authors=bib_authors,
            fetched_authors=crossref_authors,
            year_match=year_match,
            bib_year=bib_year,
            fetched_year=crossref_year,
            is_match=is_match,
            confidence=confidence,
            issues=issues,
            source="crossref"
        )
    
    def create_unable_result(self, bib_entry: BibEntry, reason: str = "Unable to fetch metadata") -> ComparisonResult:
        """Create result when metadata couldn't be fetched."""
        return ComparisonResult(
            entry_key=bib_entry.key,
            title_match=False,
            title_similarity=0.0,
            bib_title=bib_entry.title,
            fetched_title="",
            author_match=False,
            author_similarity=0.0,
            bib_authors=self.normalizer.normalize_author_list(bib_entry.author),
            fetched_authors=[],
            year_match=False,
            bib_year=bib_entry.year,
            fetched_year="",
            is_match=False,
            confidence=0.0,
            issues=[reason],
            source="unable"
        )
    
    def _compare_author_lists(self, list1: list[str], list2: list[str]) -> float:
        """Compare two author lists."""
        if not list1 and not list2:
            return 1.0
        if not list1 or not list2:
            return 0.0
        
        # Find best matches for each author in list1
        total_similarity = 0.0
        for author1 in list1:
            best_match = 0.0
            for author2 in list2:
                # Check if one name contains the other (handle abbreviated names)
                if self._names_match(author1, author2):
                    best_match = 1.0
                    break
                sim = self.normalizer.similarity_ratio(author1, author2)
                best_match = max(best_match, sim)
            total_similarity += best_match
        
        return total_similarity / len(list1)
    
    def _names_match(self, name1: str, name2: str) -> bool:
        """Check if two names match (handles abbreviated names)."""
        words1 = name1.split()
        words2 = name2.split()
        
        if not words1 or not words2:
            return False
        
        # Check if last names match
        if words1[-1] != words2[-1]:
            # Try first word as last name too
            if words1[0] != words2[-1] and words1[-1] != words2[0]:
                return False
        
        return True
    
    def compare_with_semantic_scholar(self, bib_entry: BibEntry, ss_result: SemanticScholarResult) -> ComparisonResult:
        """Compare bib entry with Semantic Scholar result."""
        issues = []
        
        # Compare titles
        bib_title_norm = self.normalizer.normalize_for_comparison(bib_entry.title)
        ss_title_norm = self.normalizer.normalize_for_comparison(ss_result.title)
        
        title_similarity = self.normalizer.similarity_ratio(bib_title_norm, ss_title_norm)
        if len(bib_title_norm) < 100:
            lev_sim = self.normalizer.levenshtein_similarity(bib_title_norm, ss_title_norm)
            title_similarity = max(title_similarity, lev_sim)
        
        title_match = title_similarity >= self.TITLE_THRESHOLD
        
        if not title_match:
            issues.append(f"Title mismatch (similarity: {title_similarity:.2%})")
        
        # Compare authors
        bib_authors = self.normalizer.normalize_author_list(bib_entry.author)
        ss_authors = [self.normalizer.normalize_author_name(a) for a in ss_result.authors]
        
        author_similarity = self._compare_author_lists(bib_authors, ss_authors)
        author_match = author_similarity >= self.AUTHOR_THRESHOLD
        
        if not author_match:
            issues.append(f"Author mismatch (similarity: {author_similarity:.2%})")
        
        # Compare years
        bib_year = bib_entry.year.strip()
        ss_year = ss_result.year
        year_match = bib_year == ss_year
        
        if not year_match and bib_year and ss_year:
            issues.append(f"Year mismatch: bib={bib_year}, semantic_scholar={ss_year}")
        
        # Overall assessment
        is_match = title_match and author_match
        confidence = (title_similarity * 0.5 + author_similarity * 0.3 + (1.0 if year_match else 0.5) * 0.2)
        
        return ComparisonResult(
            entry_key=bib_entry.key,
            title_match=title_match,
            title_similarity=title_similarity,
            bib_title=bib_entry.title,
            fetched_title=ss_result.title,
            author_match=author_match,
            author_similarity=author_similarity,
            bib_authors=bib_authors,
            fetched_authors=ss_authors,
            year_match=year_match,
            bib_year=bib_year,
            fetched_year=ss_year,
            is_match=is_match,
            confidence=confidence,
            issues=issues,
            source="semantic_scholar"
        )
    
    def compare_with_openalex(self, bib_entry: BibEntry, oa_result: OpenAlexResult) -> ComparisonResult:
        """Compare bib entry with OpenAlex result."""
        issues = []
        
        # Compare titles
        bib_title_norm = self.normalizer.normalize_for_comparison(bib_entry.title)
        oa_title_norm = self.normalizer.normalize_for_comparison(oa_result.title)
        
        title_similarity = self.normalizer.similarity_ratio(bib_title_norm, oa_title_norm)
        if len(bib_title_norm) < 100:
            lev_sim = self.normalizer.levenshtein_similarity(bib_title_norm, oa_title_norm)
            title_similarity = max(title_similarity, lev_sim)
        
        title_match = title_similarity >= self.TITLE_THRESHOLD
        
        if not title_match:
            issues.append(f"Title mismatch (similarity: {title_similarity:.2%})")
        
        # Compare authors
        bib_authors = self.normalizer.normalize_author_list(bib_entry.author)
        oa_authors = [self.normalizer.normalize_author_name(a) for a in oa_result.authors]
        
        author_similarity = self._compare_author_lists(bib_authors, oa_authors)
        author_match = author_similarity >= self.AUTHOR_THRESHOLD
        
        if not author_match:
            issues.append(f"Author mismatch (similarity: {author_similarity:.2%})")
        
        # Compare years
        bib_year = bib_entry.year.strip()
        oa_year = oa_result.year
        year_match = bib_year == oa_year
        
        if not year_match and bib_year and oa_year:
            issues.append(f"Year mismatch: bib={bib_year}, openalex={oa_year}")
        
        # Overall assessment
        is_match = title_match and author_match
        confidence = (title_similarity * 0.5 + author_similarity * 0.3 + (1.0 if year_match else 0.5) * 0.2)
        
        return ComparisonResult(
            entry_key=bib_entry.key,
            title_match=title_match,
            title_similarity=title_similarity,
            bib_title=bib_entry.title,
            fetched_title=oa_result.title,
            author_match=author_match,
            author_similarity=author_similarity,
            bib_authors=bib_authors,
            fetched_authors=oa_authors,
            year_match=year_match,
            bib_year=bib_year,
            fetched_year=oa_year,
            is_match=is_match,
            confidence=confidence,
            issues=issues,
            source="openalex"
        )
