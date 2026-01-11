"""Tests for thread-safe cache with file locking."""

import json
import tempfile
from pathlib import Path

import pytest

from upgrade_analyzer.cache import Cache, FileLock


class TestFileLock:
    """Test file locking mechanism."""
    
    def test_lock_acquire_release(self, tmp_path: Path):
        """Test basic lock acquire and release."""
        lock_file = tmp_path / "test.lock"
        lock = FileLock(lock_file)
        
        assert lock.acquire(timeout=1.0)
        lock.release()
    
    def test_lock_context_manager(self, tmp_path: Path):
        """Test lock as context manager."""
        lock_file = tmp_path / "test.lock"
        
        with FileLock(lock_file) as lock:
            assert lock._lock_fd is not None
        
        assert lock._lock_fd is None
    
    def test_lock_creates_parent_dirs(self, tmp_path: Path):
        """Test lock creates parent directories."""
        lock_file = tmp_path / "nested" / "dir" / "test.lock"
        lock = FileLock(lock_file)
        
        assert lock.acquire(timeout=1.0)
        assert lock_file.parent.exists()
        lock.release()


class TestCache:
    """Test cache operations."""
    
    def test_cache_set_and_get(self, tmp_path: Path):
        """Test basic set and get."""
        cache = Cache(cache_dir=tmp_path)
        
        cache.set("test_key", {"data": "value"}, cache_type="pypi")
        result = cache.get("test_key", cache_type="pypi", ttl_hours=24)
        
        assert result == {"data": "value"}
    
    def test_cache_get_nonexistent(self, tmp_path: Path):
        """Test get returns None for missing key."""
        cache = Cache(cache_dir=tmp_path)
        
        result = cache.get("nonexistent", cache_type="pypi")
        assert result is None
    
    def test_cache_ttl_expiry(self, tmp_path: Path):
        """Test TTL expiry."""
        cache = Cache(cache_dir=tmp_path)
        
        cache.set("test_key", "value", cache_type="pypi")
        
        # Modify the file to be old
        cache_file = cache._get_cache_file(cache.pypi_dir, "test_key")
        import os
        import time
        old_time = time.time() - (25 * 3600)  # 25 hours ago
        os.utime(cache_file, (old_time, old_time))
        
        # Should return None due to expiry
        result = cache.get("test_key", cache_type="pypi", ttl_hours=24)
        assert result is None
    
    def test_cache_ttl_zero_never_expires(self, tmp_path: Path):
        """Test TTL=0 means never expires."""
        cache = Cache(cache_dir=tmp_path)
        
        cache.set("test_key", "value", cache_type="pypi")
        
        # Even with old timestamp, should not expire
        cache_file = cache._get_cache_file(cache.pypi_dir, "test_key")
        import os
        import time
        old_time = time.time() - (1000 * 3600)  # Very old
        os.utime(cache_file, (old_time, old_time))
        
        result = cache.get("test_key", cache_type="pypi", ttl_hours=0)
        assert result == "value"
    
    def test_cache_different_types(self, tmp_path: Path):
        """Test caching different types."""
        cache = Cache(cache_dir=tmp_path)
        
        cache.set("pkg1", {"version": "1.0"}, cache_type="pypi")
        cache.set("pkg1", "changelog", cache_type="changelog")
        cache.set("pkg1", ["changes"], cache_type="api_diff")
        
        assert cache.get("pkg1", cache_type="pypi") == {"version": "1.0"}
        assert cache.get("pkg1", cache_type="changelog") == "changelog"
        assert cache.get("pkg1", cache_type="api_diff") == ["changes"]
    
    def test_cache_delete(self, tmp_path: Path):
        """Test cache deletion."""
        cache = Cache(cache_dir=tmp_path)
        
        cache.set("test_key", "value", cache_type="pypi")
        assert cache.get("test_key", cache_type="pypi") == "value"
        
        cache.delete("test_key", cache_type="pypi")
        assert cache.get("test_key", cache_type="pypi") is None
    
    def test_cache_clear(self, tmp_path: Path):
        """Test cache clear."""
        cache = Cache(cache_dir=tmp_path)
        
        cache.set("key1", "value1", cache_type="pypi")
        cache.set("key2", "value2", cache_type="pypi")
        
        deleted = cache.clear(cache_type="pypi")
        assert deleted == 2
        
        assert cache.get("key1", cache_type="pypi") is None
        assert cache.get("key2", cache_type="pypi") is None
    
    def test_cache_stats(self, tmp_path: Path):
        """Test cache statistics."""
        cache = Cache(cache_dir=tmp_path)
        
        cache.set("key1", "a" * 1000, cache_type="pypi")
        
        stats = cache.get_stats()
        
        assert "pypi" in stats
        assert stats["pypi"]["files"] == 1
        assert stats["pypi"]["size_bytes"] > 0
    
    def test_cache_unknown_type(self, tmp_path: Path):
        """Test unknown cache type handling."""
        cache = Cache(cache_dir=tmp_path)
        
        result = cache.set("key", "value", cache_type="unknown")
        assert result is False
        
        result = cache.get("key", cache_type="unknown")
        assert result is None
    
    def test_cache_handles_corrupted_json(self, tmp_path: Path):
        """Test handling of corrupted cache files."""
        cache = Cache(cache_dir=tmp_path)
        
        # Write corrupted JSON
        cache_file = cache._get_cache_file(cache.pypi_dir, "corrupted")
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text("not valid json {{{", encoding="utf-8")
        
        # Should return None and log warning
        result = cache.get("corrupted", cache_type="pypi")
        assert result is None
