"""
DBLP API fetcher.
Provides publication search for computer science papers.
"""
import time
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict, Any

import requests

from ..utils.logger import get_logger
from ..utils.cache import get_cache


@dataclass
class DBLPResult:
    """Publication metadata from DBLP."""
    key: str  # DBLP key (e.g., 'journals/corr/abs-2301-00001')
    title: str
    authors: List[str]
    year: str
    venue: str
    venue_type: str  # 'journal', 'conference', 'arxiv', etc.
    doi: Optional[str]
    url: str
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for caching."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DBLPResult':
        """Create from cached dictionary."""
        return cls(**data)


class DBLPFetcher:
    """
    Fetches publication metadata from DBLP API.
    
    API Docs: https://dblp.org/faq/How+to+use+the+dblp+search+API.html
    Rate limit: Be polite (1-2 requests/second recommended)
    """
    
    API_BASE = "https://dblp.org/search/publ/api"
    RATE_LIMIT_DELAY = 1.5  # Conservative for DBLP
    
    # Known venue abbreviation mappings
    VENUE_ALIASES: Dict[str, List[str]] = {
        'ICML': ['International Conference on Machine Learning', 'Proc. ICML'],
        'NeurIPS': ['Neural Information Processing Systems', 'NeurIPS', 'NIPS', 'Advances in Neural Information Processing Systems'],
        'ICLR': ['International Conference on Learning Representations'],
        'ACL': ['Association for Computational Linguistics', 'Proc. ACL'],
        'EMNLP': ['Empirical Methods in Natural Language Processing'],
        'NAACL': ['North American Chapter of the Association for Computational Linguistics'],
        'CVPR': ['Computer Vision and Pattern Recognition', 'IEEE/CVF Conference on Computer Vision'],
        'ICCV': ['International Conference on Computer Vision'],
        'ECCV': ['European Conference on Computer Vision'],
        'AAAI': ['AAAI Conference on Artificial Intelligence'],
        'IJCAI': ['International Joint Conference on Artificial Intelligence'],
        'KDD': ['Knowledge Discovery and Data Mining'],
        'WWW': ['The Web Conference', 'World Wide Web'],
        'SIGIR': ['Special Interest Group on Information Retrieval'],
        'COLT': ['Conference on Learning Theory'],
        'AISTATS': ['Artificial Intelligence and Statistics'],
        'UAI': ['Uncertainty in Artificial Intelligence'],
        'JMLR': ['Journal of Machine Learning Research'],
        'TACL': ['Transactions of the Association for Computational Linguistics'],
        'TPAMI': ['IEEE Transactions on Pattern Analysis and Machine Intelligence'],
    }
    
    def __init__(self):
        """Initialize fetcher."""
        self._last_request_time = 0.0
        self.logger = get_logger()
        self.cache = get_cache()
    
    def _rate_limit(self) -> None:
        """Ensure rate limiting between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.RATE_LIMIT_DELAY:
            time.sleep(self.RATE_LIMIT_DELAY - elapsed)
        self._last_request_time = time.time()
    
    def search_by_title(self, title: str, limit: int = 5) -> List[DBLPResult]:
        """
        Search for publications by title.
        
        Args:
            title: Paper title
            limit: Maximum results
            
        Returns:
            List of matching publications
        """
        # Check cache
        cache_key = f"search:{title}"
        cached = self.cache.get("dblp", cache_key)
        if cached:
            return [DBLPResult.from_dict(r) for r in cached]
        
        self._rate_limit()
        
        params = {
            'q': title,
            'h': limit,
            'format': 'json'
        }
        
        try:
            response = requests.get(
                self.API_BASE,
                params=params,
                headers={'User-Agent': 'BibGuard/2.0'},
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            
        except requests.RequestException as e:
            self.logger.error(f"DBLP search failed for '{title[:50]}': {e}")
            return []
        
        results = []
        hits = data.get('result', {}).get('hits', {}).get('hit', [])
        
        for hit in hits:
            result = self._parse_hit(hit)
            if result:
                results.append(result)
        
        # Cache results
        if results:
            self.cache.set("dblp", cache_key, [r.to_dict() for r in results])
        
        return results
    
    def get_canonical_venue(self, venue: str) -> Optional[str]:
        """
        Get canonical venue name from alias.
        
        Args:
            venue: Venue name or abbreviation
            
        Returns:
            Canonical venue name or None if not known
        """
        venue_upper = venue.upper().strip()
        
        # Check if it's a known abbreviation
        if venue_upper in self.VENUE_ALIASES:
            return venue_upper
        
        # Check if it matches any alias
        for canonical, aliases in self.VENUE_ALIASES.items():
            for alias in aliases:
                if alias.upper() in venue_upper or venue_upper in alias.upper():
                    return canonical
        
        return None
    
    def find_venue_variants(self, entries_venues: List[str]) -> Dict[str, List[str]]:
        """
        Find venue name variants in a list of venues.
        
        Args:
            entries_venues: List of venue names from bib entries
            
        Returns:
            Dict mapping canonical name to list of variants found
        """
        variants: Dict[str, List[str]] = {}
        
        for venue in entries_venues:
            canonical = self.get_canonical_venue(venue)
            if canonical:
                if canonical not in variants:
                    variants[canonical] = []
                if venue not in variants[canonical]:
                    variants[canonical].append(venue)
        
        # Only return groups with multiple variants
        return {k: v for k, v in variants.items() if len(v) > 1}
    
    def _parse_hit(self, hit: Dict[str, Any]) -> Optional[DBLPResult]:
        """Parse API hit into result object."""
        try:
            info = hit.get('info', {})
            
            key = info.get('key', '')
            if not key:
                return None
            
            # Extract title
            title = info.get('title', '')
            if isinstance(title, dict):
                title = title.get('text', '')
            
            # Extract authors
            authors_data = info.get('authors', {}).get('author', [])
            if isinstance(authors_data, dict):
                authors_data = [authors_data]
            
            authors = []
            for author in authors_data:
                if isinstance(author, dict):
                    authors.append(author.get('text', ''))
                else:
                    authors.append(str(author))
            
            # Extract venue
            venue = info.get('venue', '')
            if isinstance(venue, list):
                venue = venue[0] if venue else ''
            
            # Determine venue type from key
            venue_type = 'unknown'
            if '/journals/' in key:
                venue_type = 'journal'
            elif '/conf/' in key:
                venue_type = 'conference'
            elif '/corr/' in key:
                venue_type = 'arxiv'
            elif '/books/' in key:
                venue_type = 'book'
            
            return DBLPResult(
                key=key,
                title=title,
                authors=authors,
                year=info.get('year', ''),
                venue=venue,
                venue_type=venue_type,
                doi=info.get('doi'),
                url=info.get('url', '')
            )
            
        except Exception as e:
            self.logger.warning(f"Failed to parse DBLP response: {e}")
            return None
