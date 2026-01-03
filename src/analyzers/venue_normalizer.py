"""
Venue name normalizer for bibliography entries.
Detects inconsistent venue naming and suggests normalization.
"""
from dataclasses import dataclass
from typing import List, Dict, Set, Optional, Tuple
from collections import defaultdict
import re

from ..parsers.bib_parser import BibEntry
from ..fetchers.dblp_fetcher import DBLPFetcher
from ..utils.normalizer import TextNormalizer
from ..utils.logger import get_logger


@dataclass
class VenueVariant:
    """A venue name variant with its occurrences."""
    name: str
    entry_keys: List[str]
    count: int


@dataclass
class VenueNormalizationResult:
    """Result of venue normalization check."""
    canonical_name: str
    variants: List[VenueVariant]
    suggested_name: str
    
    @property
    def has_inconsistency(self) -> bool:
        """Check if there are multiple variants."""
        return len(self.variants) > 1


class VenueNormalizer:
    """
    Detects inconsistent venue names in bibliography.
    
    For example:
    - "ICML" vs "International Conference on Machine Learning"
    - "NeurIPS" vs "NIPS" vs "Neural Information Processing Systems"
    """
    
    # Extended venue aliases (from DBLP + common variations)
    VENUE_ALIASES: Dict[str, List[str]] = {
        'ICML': [
            'International Conference on Machine Learning',
            'Proc. ICML',
            'Proceedings of ICML',
            'ICML',
        ],
        'NeurIPS': [
            'Neural Information Processing Systems',
            'NeurIPS',
            'NIPS',
            'Advances in Neural Information Processing Systems',
            'Proc. NeurIPS',
        ],
        'ICLR': [
            'International Conference on Learning Representations',
            'ICLR',
        ],
        'ACL': [
            'Association for Computational Linguistics',
            'Proc. ACL',
            'Proceedings of the ACL',
            'Annual Meeting of the Association for Computational Linguistics',
            'ACL',
        ],
        'EMNLP': [
            'Empirical Methods in Natural Language Processing',
            'EMNLP',
            'Proc. EMNLP',
        ],
        'NAACL': [
            'North American Chapter of the Association for Computational Linguistics',
            'NAACL',
            'NAACL-HLT',
        ],
        'CVPR': [
            'Computer Vision and Pattern Recognition',
            'IEEE/CVF Conference on Computer Vision and Pattern Recognition',
            'CVPR',
            'Proc. CVPR',
        ],
        'ICCV': [
            'International Conference on Computer Vision',
            'IEEE/CVF International Conference on Computer Vision',
            'ICCV',
        ],
        'ECCV': [
            'European Conference on Computer Vision',
            'ECCV',
        ],
        'AAAI': [
            'AAAI Conference on Artificial Intelligence',
            'AAAI',
            'Proc. AAAI',
        ],
        'IJCAI': [
            'International Joint Conference on Artificial Intelligence',
            'IJCAI',
        ],
        'KDD': [
            'Knowledge Discovery and Data Mining',
            'KDD',
            'ACM SIGKDD',
        ],
        'WWW': [
            'The Web Conference',
            'World Wide Web',
            'WWW',
            'TheWebConf',
        ],
        'SIGIR': [
            'Special Interest Group on Information Retrieval',
            'SIGIR',
            'ACM SIGIR',
        ],
        'COLT': [
            'Conference on Learning Theory',
            'COLT',
        ],
        'AISTATS': [
            'Artificial Intelligence and Statistics',
            'AISTATS',
        ],
        'UAI': [
            'Uncertainty in Artificial Intelligence',
            'UAI',
        ],
        'JMLR': [
            'Journal of Machine Learning Research',
            'JMLR',
            'J. Mach. Learn. Res.',
        ],
        'TACL': [
            'Transactions of the Association for Computational Linguistics',
            'TACL',
            'Trans. Assoc. Comput. Linguist.',
        ],
        'TPAMI': [
            'IEEE Transactions on Pattern Analysis and Machine Intelligence',
            'TPAMI',
            'IEEE Trans. Pattern Anal. Mach. Intell.',
        ],
        'IJCV': [
            'International Journal of Computer Vision',
            'IJCV',
            'Int. J. Comput. Vis.',
        ],
        'arXiv': [
            'arXiv',
            'arXiv preprint',
            'CoRR',
            'arXiv.org',
        ],
    }
    
    def __init__(self, use_dblp: bool = False):
        """
        Initialize normalizer.
        
        Args:
            use_dblp: Whether to use DBLP for additional venue lookup
        """
        self.dblp = DBLPFetcher() if use_dblp else None
        self.logger = get_logger()
        self._build_lookup()
    
    def _build_lookup(self) -> None:
        """Build reverse lookup from alias to canonical name."""
        self._alias_lookup: Dict[str, str] = {}
        for canonical, aliases in self.VENUE_ALIASES.items():
            for alias in aliases:
                normalized = TextNormalizer.normalize_for_comparison(alias)
                self._alias_lookup[normalized] = canonical
    
    def get_canonical_name(self, venue: str) -> Optional[str]:
        """
        Get canonical venue name from any variant.
        
        Args:
            venue: Venue name
            
        Returns:
            Canonical name or None if not recognized
        """
        normalized = TextNormalizer.normalize_for_comparison(venue)
        
        # Direct lookup
        if normalized in self._alias_lookup:
            return self._alias_lookup[normalized]
        
        # Fuzzy match
        for alias_norm, canonical in self._alias_lookup.items():
            # Check if one contains the other
            if alias_norm in normalized or normalized in alias_norm:
                return canonical
            
            # Check similarity
            sim = TextNormalizer.similarity_ratio(alias_norm, normalized)
            if sim > 0.8:
                return canonical
        
        return None
    
    def _strip_venue_metadata(self, venue: str) -> str:
        """
        Strip year, location, dates from venue name for comparison.
        
        This helps identify true naming inconsistencies (ICML vs International Conference)
        vs mere year/location differences (ACL 2019 vs ACL 2024).
        """
        # Remove year patterns (2019, 2024, etc.)
        result = re.sub(r'\b(19|20)\d{2}\b', '', venue)
        
        # Remove month/date patterns
        result = re.sub(r'\b(January|February|March|April|May|June|July|August|September|October|November|December)\b', '', result, flags=re.IGNORECASE)
        result = re.sub(r'\b\d{1,2}(st|nd|rd|th)?\s*[-–]\s*\d{1,2}(st|nd|rd|th)?\b', '', result)
        
        # Remove location patterns (common cities/countries)
        locations = [
            'Bangkok', 'Thailand', 'Florence', 'Italy', 'Vienna', 'Austria',
            'Singapore', 'Kigali', 'Rwanda', 'Vancouver', 'Canada', 'New Orleans',
            'USA', 'Seattle', 'San Francisco', 'California', 'New York', 'London',
            'UK', 'Paris', 'France', 'Berlin', 'Germany', 'Tokyo', 'Japan',
            'Sydney', 'Australia', 'Hong Kong', 'Beijing', 'China', 'Seoul', 'Korea',
            'virtual meeting', 'virtual', 'online', 'hybrid'
        ]
        for loc in locations:
            result = re.sub(rf'\b{re.escape(loc)}\b', '', result, flags=re.IGNORECASE)
        
        # Remove ordinal indicators (57th, 62nd, etc.)
        result = re.sub(r'\b\d+(st|nd|rd|th)\b', '', result, flags=re.IGNORECASE)
        
        # Remove "Volume 1: Long Papers" type suffixes
        result = re.sub(r'\(Volume\s*\d+[^)]*\)', '', result)
        result = re.sub(r'Volume\s*\d+:\s*\w+\s*Papers', '', result)
        
        # Remove extra commas and whitespace
        result = re.sub(r'\s*,\s*,', ',', result)
        result = re.sub(r'\s+', ' ', result)
        result = result.strip(' ,')
        
        return result
    
    def _get_venue_signature(self, venue: str) -> str:
        """
        Get a simplified signature for venue comparison.
        
        Returns a normalized version that ignores year/location.
        """
        stripped = self._strip_venue_metadata(venue)
        normalized = TextNormalizer.normalize_for_comparison(stripped)
        return normalized
    
    def find_inconsistencies(self, entries: List[BibEntry]) -> List[VenueNormalizationResult]:
        """
        Find venue name inconsistencies in bibliography.
        
        Only flags TRUE inconsistencies where abbreviation and full name are mixed:
        - "ICML" in one entry AND "International Conference on Machine Learning" in another
        
        Does NOT flag:
        - Different years (ACL 2019 vs ACL 2024)
        - Different tracks (Findings of ACL vs Proceedings of ACL)
        
        Args:
            entries: List of BibEntry objects
            
        Returns:
            List of VenueNormalizationResult for venues with inconsistencies
        """
        # Group entries by canonical venue name
        venue_groups: Dict[str, List[Tuple[str, str, str]]] = defaultdict(list)  # canonical -> [(key, venue, type)]
        
        for entry in entries:
            venue = self._get_venue(entry)
            if not venue:
                continue
            
            canonical = self.get_canonical_name(venue)
            if canonical:
                # Determine if this is an abbreviation or full name usage
                venue_type = self._classify_venue_usage(venue, canonical)
                venue_groups[canonical].append((entry.key, venue, venue_type))
        
        # Find groups where both abbreviation AND full name are used
        results = []
        for canonical, entries_info in venue_groups.items():
            usage_types = set(e[2] for e in entries_info)
            
            # Only flag if there's a mix of abbreviation and full name
            if 'abbreviation' in usage_types and 'full_name' in usage_types:
                # Group by usage type
                abbrev_entries = [(k, v) for k, v, t in entries_info if t == 'abbreviation']
                full_entries = [(k, v) for k, v, t in entries_info if t == 'full_name']
                
                variant_list = []
                if abbrev_entries:
                    variant_list.append(VenueVariant(
                        name=abbrev_entries[0][1],  # Use first as representative
                        entry_keys=[k for k, v in abbrev_entries],
                        count=len(abbrev_entries)
                    ))
                if full_entries:
                    variant_list.append(VenueVariant(
                        name=full_entries[0][1],
                        entry_keys=[k for k, v in full_entries],
                        count=len(full_entries)
                    ))
                
                # Sort by count
                variant_list.sort(key=lambda v: v.count, reverse=True)
                
                results.append(VenueNormalizationResult(
                    canonical_name=canonical,
                    variants=variant_list,
                    suggested_name=variant_list[0].name
                ))
        
        return results
    
    def _classify_venue_usage(self, venue: str, canonical: str) -> str:
        """
        Classify if a venue name is using abbreviation or full name.
        
        Returns: 'abbreviation', 'full_name', or 'mixed'
        """
        venue_lower = venue.lower()
        canonical_lower = canonical.lower()
        
        # Check if venue is just the abbreviation (possibly with year/location)
        # e.g., "ICML 2024" or just "ICML"
        if canonical_lower in venue_lower and len(venue) < 50:
            # Short name that contains the abbreviation is likely abbreviation usage
            return 'abbreviation'
        
        # Check for full conference name patterns
        full_name_keywords = [
            'conference', 'proceedings', 'meeting', 'symposium', 'workshop',
            'journal', 'transactions', 'advances in', 'findings of'
        ]
        
        if any(kw in venue_lower for kw in full_name_keywords):
            return 'full_name'
        
        # Default to full_name for long venue names
        if len(venue) > 50:
            return 'full_name'
        
        return 'abbreviation'
    
    def _get_venue(self, entry: BibEntry) -> Optional[str]:
        """Extract venue from entry."""
        # Check booktitle (for conference papers)
        if entry.booktitle:
            return entry.booktitle
        
        # Check journal
        if entry.journal:
            return entry.journal
        
        # Check raw entry for other fields
        for field in ['howpublished', 'series']:
            if field in entry.raw_entry:
                return entry.raw_entry[field]
        
        return None
