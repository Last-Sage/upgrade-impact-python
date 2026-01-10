"""Disk-based caching system for API responses and changelogs."""

import hashlib
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from upgrade_analyzer.config import get_config


class Cache:
    """Disk-based cache with TTL support."""
    
    def __init__(self, cache_dir: Path | None = None) -> None:
        """Initialize cache.
        
        Args:
            cache_dir: Directory to store cache files
        """
        config = get_config()
        self.cache_dir = cache_dir or config.cache_dir
        self.enabled = config.cache_enabled
        
        # Create cache directories
        self.pypi_dir = self.cache_dir / "pypi"
        self.changelog_dir = self.cache_dir / "changelogs"
        self.api_diff_dir = self.cache_dir / "api_diffs"
        
        if self.enabled:
            self._ensure_directories()
    
    def _ensure_directories(self) -> None:
        """Create cache directories if they don't exist."""
        for directory in [self.pypi_dir, self.changelog_dir, self.api_diff_dir]:
            directory.mkdir(parents=True, exist_ok=True)
    
    @staticmethod
    def _hash_key(key: str) -> str:
        """Create hash of key for filename.
        
        Args:
            key: Cache key
            
        Returns:
            Hashed key
        """
        return hashlib.sha256(key.encode()).hexdigest()
    
    def _get_cache_file(self, directory: Path, key: str) -> Path:
        """Get cache file path for a key.
        
        Args:
            directory: Cache subdirectory
            key: Cache key
            
        Returns:
            Path to cache file
        """
        hashed = self._hash_key(key)
        return directory / f"{hashed}.json"
    
    def _is_expired(self, cache_file: Path, ttl_hours: int) -> bool:
        """Check if cache file has expired.
        
        Args:
            cache_file: Path to cache file
            ttl_hours: Time-to-live in hours (0 = never expires)
            
        Returns:
            True if expired, False otherwise
        """
        if ttl_hours == 0:  # Never expires
            return False
        
        if not cache_file.exists():
            return True
        
        modified_time = datetime.fromtimestamp(cache_file.stat().st_mtime)
        expiry_time = modified_time + timedelta(hours=ttl_hours)
        
        return datetime.now() > expiry_time
    
    def get(
        self,
        key: str,
        cache_type: str = "pypi",
        ttl_hours: int = 24
    ) -> Any | None:
        """Get value from cache.
        
        Args:
            key: Cache key
            cache_type: Type of cache ("pypi", "changelog", "api_diff")
            ttl_hours: Time-to-live in hours
            
        Returns:
            Cached value or None if not found/expired
        """
        if not self.enabled:
            return None
        
        # Select cache directory
        if cache_type == "pypi":
            directory = self.pypi_dir
        elif cache_type == "changelog":
            directory = self.changelog_dir
        elif cache_type == "api_diff":
            directory = self.api_diff_dir
        else:
            return None
        
        cache_file = self._get_cache_file(directory, key)
        
        # Check if file exists and is not expired
        if self._is_expired(cache_file, ttl_hours):
            return None
        
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("value")
        except Exception:
            return None
    
    def set(
        self,
        key: str,
        value: Any,
        cache_type: str = "pypi"
    ) -> None:
        """Set value in cache.
        
        Args:
            key: Cache key
            value: Value to cache
            cache_type: Type of cache ("pypi", "changelog", "api_diff")
        """
        if not self.enabled:
            return
        
        # Select cache directory
        if cache_type == "pypi":
            directory = self.pypi_dir
        elif cache_type == "changelog":
            directory = self.changelog_dir
        elif cache_type == "api_diff":
            directory = self.api_diff_dir
        else:
            return
        
        cache_file = self._get_cache_file(directory, key)
        
        try:
            data = {
                "key": key,
                "value": value,
                "cached_at": datetime.now().isoformat(),
            }
            
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass  # Silently fail on cache write errors
    
    def clear(self, cache_type: str | None = None) -> None:
        """Clear cache.
        
        Args:
            cache_type: Type of cache to clear (None = all)
        """
        if not self.enabled:
            return
        
        directories = []
        
        if cache_type is None:
            directories = [self.pypi_dir, self.changelog_dir, self.api_diff_dir]
        elif cache_type == "pypi":
            directories = [self.pypi_dir]
        elif cache_type == "changelog":
            directories = [self.changelog_dir]
        elif cache_type == "api_diff":
            directories = [self.api_diff_dir]
        
        for directory in directories:
            if directory.exists():
                for file in directory.glob("*.json"):
                    try:
                        file.unlink()
                    except Exception:
                        pass


# Global cache instance
_cache: Cache | None = None


def get_cache() -> Cache:
    """Get or create global cache instance.
    
    Returns:
        Cache instance
    """
    global _cache
    
    if _cache is None:
        _cache = Cache()
    
    return _cache
