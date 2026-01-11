"""Thread-safe disk-based caching system with file locking."""

import hashlib
import json
import logging
import os
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Generator

# Platform-specific imports for file locking
if sys.platform == 'win32':
    import msvcrt
    FCNTL_AVAILABLE = False
else:
    try:
        import fcntl
        FCNTL_AVAILABLE = True
    except ImportError:
        FCNTL_AVAILABLE = False

from upgrade_analyzer.config import get_config

logger = logging.getLogger(__name__)


class FileLock:
    """Cross-platform file locking for thread-safe cache access."""
    
    def __init__(self, lock_file: Path) -> None:
        """Initialize file lock.
        
        Args:
            lock_file: Path to lock file
        """
        self.lock_file = lock_file
        self._lock_fd: int | None = None
    
    def acquire(self, timeout: float = 10.0) -> bool:
        """Acquire the lock.
        
        Args:
            timeout: Maximum time to wait for lock
            
        Returns:
            True if lock acquired, False otherwise
        """
        self.lock_file.parent.mkdir(parents=True, exist_ok=True)
        
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                self._lock_fd = os.open(
                    str(self.lock_file),
                    os.O_CREAT | os.O_RDWR
                )
                
                # Try to acquire exclusive lock
                if sys.platform == 'win32':  # Windows
                    try:
                        msvcrt.locking(self._lock_fd, msvcrt.LK_NBLCK, 1)
                        return True
                    except OSError:
                        os.close(self._lock_fd)
                        self._lock_fd = None
                elif FCNTL_AVAILABLE:  # Unix with fcntl
                    try:
                        fcntl.flock(self._lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        return True
                    except BlockingIOError:
                        os.close(self._lock_fd)
                        self._lock_fd = None
                else:
                    # No locking available, just return True
                    return True
                
                time.sleep(0.1)
                
            except Exception as e:
                logger.debug(f"Failed to acquire lock: {e}")
                if self._lock_fd is not None:
                    try:
                        os.close(self._lock_fd)
                    except Exception:
                        pass
                    self._lock_fd = None
                time.sleep(0.1)
        
        logger.warning(f"Could not acquire lock after {timeout}s")
        return False
    
    def release(self) -> None:
        """Release the lock."""
        if self._lock_fd is not None:
            try:
                if sys.platform == 'win32':  # Windows
                    try:
                        msvcrt.locking(self._lock_fd, msvcrt.LK_UNLCK, 1)
                    except Exception:
                        pass
                elif FCNTL_AVAILABLE:  # Unix with fcntl
                    try:
                        fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
                    except Exception:
                        pass
                
                os.close(self._lock_fd)
            except Exception as e:
                logger.debug(f"Error releasing lock: {e}")
            finally:
                self._lock_fd = None
    
    def __enter__(self) -> "FileLock":
        self.acquire()
        return self
    
    def __exit__(self, *args: Any) -> None:
        self.release()


class Cache:
    """Thread-safe disk-based cache with TTL support."""
    
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
        self.locks_dir = self.cache_dir / ".locks"
        
        if self.enabled:
            self._ensure_directories()
    
    def _ensure_directories(self) -> None:
        """Create cache directories if they don't exist."""
        for directory in [self.pypi_dir, self.changelog_dir, self.api_diff_dir, self.locks_dir]:
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
    
    def _get_lock_file(self, key: str) -> Path:
        """Get lock file path for a key."""
        hashed = self._hash_key(key)
        return self.locks_dir / f"{hashed}.lock"
    
    @contextmanager
    def _lock_key(self, key: str) -> Generator[None, None, None]:
        """Context manager for locking a cache key."""
        lock = FileLock(self._get_lock_file(key))
        try:
            lock.acquire()
            yield
        finally:
            lock.release()
    
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
    
    def _get_directory(self, cache_type: str) -> Path | None:
        """Get cache directory for type."""
        return {
            "pypi": self.pypi_dir,
            "changelog": self.changelog_dir,
            "api_diff": self.api_diff_dir,
        }.get(cache_type)
    
    def get(
        self,
        key: str,
        cache_type: str = "pypi",
        ttl_hours: int = 24
    ) -> Any | None:
        """Get value from cache (thread-safe).
        
        Args:
            key: Cache key
            cache_type: Type of cache ("pypi", "changelog", "api_diff")
            ttl_hours: Time-to-live in hours
            
        Returns:
            Cached value or None if not found/expired
        """
        if not self.enabled:
            return None
        
        directory = self._get_directory(cache_type)
        if directory is None:
            logger.warning(f"Unknown cache type: {cache_type}")
            return None
        
        cache_file = self._get_cache_file(directory, key)
        
        # Check if file exists and is not expired
        if self._is_expired(cache_file, ttl_hours):
            return None
        
        with self._lock_key(key):
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("value")
            except json.JSONDecodeError as e:
                logger.warning(f"Corrupted cache file {cache_file}: {e}")
                try:
                    cache_file.unlink()
                except Exception:
                    pass
                return None
            except FileNotFoundError:
                return None
            except Exception as e:
                logger.error(f"Error reading cache file {cache_file}: {e}")
                return None
    
    def set(
        self,
        key: str,
        value: Any,
        cache_type: str = "pypi"
    ) -> bool:
        """Set value in cache (thread-safe).
        
        Args:
            key: Cache key
            value: Value to cache
            cache_type: Type of cache ("pypi", "changelog", "api_diff")
            
        Returns:
            True if cached successfully, False otherwise
        """
        if not self.enabled:
            return False
        
        directory = self._get_directory(cache_type)
        if directory is None:
            logger.warning(f"Unknown cache type: {cache_type}")
            return False
        
        cache_file = self._get_cache_file(directory, key)
        
        with self._lock_key(key):
            try:
                data = {
                    "key": key,
                    "value": value,
                    "cached_at": datetime.now().isoformat(),
                }
                
                # Write to temp file first, then rename (atomic on most systems)
                temp_file = cache_file.with_suffix(".tmp")
                with open(temp_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
                
                # Atomic rename
                temp_file.replace(cache_file)
                return True
                
            except TypeError as e:
                logger.error(f"Cannot serialize value for cache key {key}: {e}")
                return False
            except Exception as e:
                logger.error(f"Error writing cache file {cache_file}: {e}")
                return False
    
    def delete(self, key: str, cache_type: str = "pypi") -> bool:
        """Delete a cache entry.
        
        Args:
            key: Cache key
            cache_type: Type of cache
            
        Returns:
            True if deleted, False otherwise
        """
        if not self.enabled:
            return False
        
        directory = self._get_directory(cache_type)
        if directory is None:
            return False
        
        cache_file = self._get_cache_file(directory, key)
        
        with self._lock_key(key):
            try:
                if cache_file.exists():
                    cache_file.unlink()
                return True
            except Exception as e:
                logger.error(f"Error deleting cache file {cache_file}: {e}")
                return False
    
    def clear(self, cache_type: str | None = None) -> int:
        """Clear cache.
        
        Args:
            cache_type: Type of cache to clear (None = all)
            
        Returns:
            Number of files deleted
        """
        if not self.enabled:
            return 0
        
        if cache_type is None:
            directories = [self.pypi_dir, self.changelog_dir, self.api_diff_dir]
        else:
            directory = self._get_directory(cache_type)
            directories = [directory] if directory else []
        
        deleted_count = 0
        
        for directory in directories:
            if directory and directory.exists():
                for file in directory.glob("*.json"):
                    try:
                        file.unlink()
                        deleted_count += 1
                    except Exception as e:
                        logger.error(f"Error deleting cache file {file}: {e}")
        
        return deleted_count
    
    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics.
        
        Returns:
            Dictionary with cache stats
        """
        stats = {}
        
        for name, directory in [
            ("pypi", self.pypi_dir),
            ("changelog", self.changelog_dir),
            ("api_diff", self.api_diff_dir),
        ]:
            if directory.exists():
                files = list(directory.glob("*.json"))
                total_size = sum(f.stat().st_size for f in files)
                stats[name] = {
                    "files": len(files),
                    "size_bytes": total_size,
                    "size_mb": round(total_size / (1024 * 1024), 2),
                }
            else:
                stats[name] = {"files": 0, "size_bytes": 0, "size_mb": 0}
        
        return stats


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
