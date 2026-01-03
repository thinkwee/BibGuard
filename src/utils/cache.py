"""
File-based caching system for API results.
"""
import json
import hashlib
import time
from pathlib import Path
from typing import Any, Optional
from dataclasses import dataclass

from .logger import get_logger


@dataclass
class CacheEntry:
    """A cached item with metadata."""
    data: Any
    timestamp: float
    ttl: int  # Time to live in seconds


class Cache:
    """
    File-based JSON cache with TTL support.
    
    Cache structure:
        .cache/
        ├── arxiv/
        │   └── <hash>.json
        ├── crossref/
        │   └── <hash>.json
        └── dblp/
            └── <hash>.json
    """
    
    DEFAULT_TTL = 7 * 24 * 60 * 60  # 7 days in seconds
    
    def __init__(self, cache_dir: Optional[Path] = None, ttl: int = DEFAULT_TTL):
        """
        Initialize cache.
        
        Args:
            cache_dir: Cache directory (default: ./.cache/ in current directory)
            ttl: Time to live in seconds (default: 7 days)
        """
        self.cache_dir = cache_dir or Path(".cache")
        self.ttl = ttl
        self.logger = get_logger()
        self._ensure_dirs()
    
    def _ensure_dirs(self) -> None:
        """Create cache directories if they don't exist."""
        subdirs = ["arxiv", "semantic_scholar", "crossref", "dblp", "scholar", "url"]
        for subdir in subdirs:
            (self.cache_dir / subdir).mkdir(parents=True, exist_ok=True)
    
    def _hash_key(self, key: str) -> str:
        """Generate hash for cache key."""
        return hashlib.sha256(key.encode('utf-8')).hexdigest()[:16]
    
    def _get_path(self, source: str, key: str) -> Path:
        """Get file path for a cache entry."""
        return self.cache_dir / source / f"{self._hash_key(key)}.json"
    
    def get(self, source: str, key: str) -> Optional[Any]:
        """
        Get value from cache.
        
        Args:
            source: Cache source (e.g., 'arxiv', 'semantic_scholar')
            key: Cache key (e.g., paper title or ID)
            
        Returns:
            Cached data or None if not found/expired
        """
        path = self._get_path(source, key)
        
        if not path.exists():
            return None
        
        try:
            with open(path, 'r', encoding='utf-8') as f:
                entry = json.load(f)
            
            # Check if expired
            if time.time() - entry['timestamp'] > entry['ttl']:
                self.logger.debug(f"Cache expired for {source}:{key[:30]}")
                path.unlink()  # Remove expired entry
                return None
            
            self.logger.debug(f"Cache hit for {source}:{key[:30]}")
            return entry['data']
            
        except (json.JSONDecodeError, KeyError, OSError) as e:
            self.logger.warning(f"Cache read error for {source}:{key[:30]}: {e}")
            return None
    
    def set(self, source: str, key: str, data: Any, ttl: Optional[int] = None) -> bool:
        """
        Store value in cache.
        
        Args:
            source: Cache source
            key: Cache key
            data: Data to cache (must be JSON-serializable)
            ttl: Optional custom TTL (uses default if not specified)
            
        Returns:
            True if successful, False otherwise
        """
        path = self._get_path(source, key)
        
        entry = {
            'data': data,
            'timestamp': time.time(),
            'ttl': ttl or self.ttl
        }
        
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(entry, f, ensure_ascii=False, indent=2)
            self.logger.debug(f"Cached {source}:{key[:30]}")
            return True
            
        except (OSError, TypeError) as e:
            self.logger.warning(f"Cache write error for {source}:{key[:30]}: {e}")
            return False
    
    def clear(self, source: Optional[str] = None) -> int:
        """
        Clear cache entries.
        
        Args:
            source: Clear only this source, or all if None
            
        Returns:
            Number of entries cleared
        """
        count = 0
        
        if source:
            source_dir = self.cache_dir / source
            if source_dir.exists():
                for path in source_dir.glob("*.json"):
                    path.unlink()
                    count += 1
        else:
            for source_dir in self.cache_dir.iterdir():
                if source_dir.is_dir():
                    for path in source_dir.glob("*.json"):
                        path.unlink()
                        count += 1
        
        self.logger.info(f"Cleared {count} cache entries")
        return count
    
    def cleanup_expired(self) -> int:
        """
        Remove all expired cache entries.
        
        Returns:
            Number of entries removed
        """
        count = 0
        current_time = time.time()
        
        for source_dir in self.cache_dir.iterdir():
            if not source_dir.is_dir():
                continue
            
            for path in source_dir.glob("*.json"):
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        entry = json.load(f)
                    
                    if current_time - entry['timestamp'] > entry['ttl']:
                        path.unlink()
                        count += 1
                        
                except (json.JSONDecodeError, KeyError, OSError):
                    # Remove corrupted entries
                    path.unlink()
                    count += 1
        
        self.logger.info(f"Cleaned up {count} expired cache entries")
        return count


# Global cache instance
_cache: Optional[Cache] = None


def get_cache() -> Cache:
    """Get the global cache instance."""
    global _cache
    if _cache is None:
        _cache = Cache()
    return _cache
