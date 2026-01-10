"""Changelog fetcher from multiple sources with rate limiting and authentication."""

import logging
import os
import re
import time
from pathlib import Path

import httpx

from upgrade_analyzer.cache import get_cache
from upgrade_analyzer.intelligence.pypi_client import PyPIClient
from upgrade_analyzer.models import ChangelogEntry

logger = logging.getLogger(__name__)

# Rate limit tracking
_last_github_request: float = 0
_github_request_count: int = 0
_github_rate_limit_reset: float = 0


class ChangelogFetcher:
    """Fetches changelogs from various sources with rate limiting."""
    
    def __init__(self, offline: bool = False) -> None:
        """Initialize changelog fetcher.
        
        Args:
            offline: If True, only use cached data
        """
        self.offline = offline
        self.cache = get_cache()
        
        # Configure GitHub authentication if available
        self.github_token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "upgrade-impact-analyzer",
        }
        if self.github_token:
            headers["Authorization"] = f"token {self.github_token}"
            logger.info("Using GitHub token for API requests")
        
        self.client = httpx.Client(
            timeout=30.0,
            follow_redirects=True,
            headers=headers,
        ) if not offline else None
        
        self.pypi_client = PyPIClient(offline=offline)
    
    def _check_rate_limit(self) -> bool:
        """Check if we should wait before making a GitHub API request.
        
        Returns:
            True if we can proceed, False if rate limited
        """
        global _last_github_request, _github_request_count, _github_rate_limit_reset
        
        now = time.time()
        
        # If we hit rate limit, check if it's reset
        if _github_rate_limit_reset > now:
            wait_time = _github_rate_limit_reset - now
            logger.warning(f"GitHub rate limit reached. Reset in {wait_time:.0f}s")
            
            # Only wait if it's a short time
            if wait_time < 60:
                time.sleep(wait_time + 1)
                _github_request_count = 0
            else:
                return False
        
        # Limit to 30 requests per minute for unauthenticated
        max_requests = 5000 if self.github_token else 30
        
        if _github_request_count >= max_requests:
            if now - _last_github_request < 60:
                logger.warning("Rate limiting GitHub requests")
                return False
            _github_request_count = 0
        
        _github_request_count += 1
        _last_github_request = now
        
        return True
    
    def _handle_rate_limit_response(self, response: httpx.Response) -> None:
        """Handle rate limit headers from GitHub response.
        
        Args:
            response: HTTP response
        """
        global _github_rate_limit_reset
        
        remaining = response.headers.get("X-RateLimit-Remaining")
        reset_time = response.headers.get("X-RateLimit-Reset")
        
        if remaining == "0" and reset_time:
            _github_rate_limit_reset = float(reset_time)
            logger.warning(f"GitHub rate limit exhausted. Reset at {reset_time}")
    
    def fetch_changelog(
        self,
        package_name: str,
        from_version: str | None = None,
        to_version: str | None = None
    ) -> list[ChangelogEntry]:
        """Fetch changelog entries for a package.
        
        Args:
            package_name: Name of the package
            from_version: Starting version (optional)
            to_version: Target version (optional)
            
        Returns:
            List of changelog entries
        """
        cache_key = f"changelog:{package_name}:{from_version}:{to_version}"
        
        # Try cache first
        cached = self.cache.get(cache_key, cache_type="changelog", ttl_hours=168)  # 1 week
        if cached:
            return self._deserialize_entries(cached)
        
        if self.offline:
            return []
        
        # Try multiple sources
        entries: list[ChangelogEntry] = []
        
        # 1. Try GitHub releases
        github_entries = self._fetch_from_github_releases(package_name, from_version, to_version)
        if github_entries:
            entries.extend(github_entries)
        
        # 2. Try GitHub CHANGELOG.md
        if not entries:
            changelog_entries = self._fetch_from_github_changelog(package_name)
            if changelog_entries:
                entries.extend(changelog_entries)
        
        # 3. Try PyPI release notes
        if not entries:
            pypi_entries = self._fetch_from_pypi_notes(package_name, to_version)
            if pypi_entries:
                entries.extend(pypi_entries)
        
        # Filter entries by version range if specified
        if entries and (from_version or to_version):
            entries = self._filter_by_version_range(entries, from_version, to_version)
        
        # Cache results
        if entries:
            cache_data = self._serialize_entries(entries)
            self.cache.set(cache_key, cache_data, cache_type="changelog")
        
        return entries
    
    def _serialize_entries(self, entries: list[ChangelogEntry]) -> list[dict]:
        """Serialize entries for caching."""
        return [
            {
                "version": e.version,
                "release_date": e.release_date,
                "content": e.content,
            }
            for e in entries
        ]
    
    def _deserialize_entries(self, cached: list[dict]) -> list[ChangelogEntry]:
        """Deserialize entries from cache."""
        return [
            ChangelogEntry(
                version=entry.get("version", ""),
                release_date=entry.get("release_date"),
                content=entry.get("content", ""),
            )
            for entry in cached
        ]
    
    def _filter_by_version_range(
        self,
        entries: list[ChangelogEntry],
        from_version: str | None,
        to_version: str | None
    ) -> list[ChangelogEntry]:
        """Filter entries to only include those in version range.
        
        Args:
            entries: All changelog entries
            from_version: Lower bound (exclusive)
            to_version: Upper bound (inclusive)
            
        Returns:
            Filtered entries
        """
        from packaging.version import parse as parse_version, InvalidVersion
        
        filtered = []
        
        try:
            from_v = parse_version(from_version) if from_version else None
            to_v = parse_version(to_version) if to_version else None
        except InvalidVersion:
            return entries
        
        for entry in entries:
            try:
                entry_v = parse_version(entry.version)
                
                # Include if within range
                if from_v and entry_v <= from_v:
                    continue
                if to_v and entry_v > to_v:
                    continue
                
                filtered.append(entry)
                
            except InvalidVersion:
                # Include entries with unparseable versions
                filtered.append(entry)
        
        return filtered
    
    def _fetch_from_github_releases(
        self,
        package_name: str,
        from_version: str | None,
        to_version: str | None
    ) -> list[ChangelogEntry]:
        """Fetch changelog from GitHub Releases API.
        
        Args:
            package_name: Package name
            from_version: Starting version
            to_version: Target version
            
        Returns:
            List of changelog entries
        """
        # Check rate limit
        if not self._check_rate_limit():
            logger.warning(f"Skipping GitHub releases for {package_name} due to rate limit")
            return []
        
        # Get GitHub repo info
        repo_info = self.pypi_client.get_github_repo(package_name)
        
        if not repo_info:
            return []
        
        owner, repo = repo_info
        
        try:
            # Fetch releases from GitHub API
            url = f"https://api.github.com/repos/{owner}/{repo}/releases"
            response = self.client.get(url, params={"per_page": 30})
            
            # Handle rate limit
            self._handle_rate_limit_response(response)
            
            if response.status_code == 403:
                logger.warning("GitHub API rate limit exceeded")
                return []
            
            if response.status_code != 200:
                logger.debug(f"GitHub releases fetch failed: {response.status_code}")
                return []
            
            releases = response.json()
            entries = []
            
            for release in releases:
                version = release.get("tag_name", "").lstrip("v")
                
                if not version:
                    continue
                
                entry = ChangelogEntry(
                    version=version,
                    release_date=release.get("published_at"),
                    content=release.get("body", ""),
                )
                
                entries.append(entry)
            
            return entries
        
        except httpx.RequestError as e:
            logger.error(f"Network error fetching GitHub releases: {e}")
            return []
        except Exception as e:
            logger.error(f"Error fetching GitHub releases for {package_name}: {e}")
            return []
    
    def _fetch_from_github_changelog(self, package_name: str) -> list[ChangelogEntry]:
        """Fetch changelog from CHANGELOG.md file.
        
        Args:
            package_name: Package name
            
        Returns:
            List of changelog entries
        """
        # Check rate limit
        if not self._check_rate_limit():
            return []
        
        # Get GitHub repo info
        repo_info = self.pypi_client.get_github_repo(package_name)
        
        if not repo_info:
            return []
        
        owner, repo = repo_info
        
        # Try common changelog file names
        filenames = ["CHANGELOG.md", "CHANGES.md", "HISTORY.md", "NEWS.md", "CHANGELOG.rst"]
        
        for filename in filenames:
            for branch in ["main", "master", "develop"]:
                try:
                    url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{filename}"
                    response = self.client.get(url)
                    
                    if response.status_code == 200:
                        logger.debug(f"Found changelog at {url}")
                        return self._parse_changelog_markdown(response.text)
                
                except httpx.RequestError:
                    continue
                except Exception as e:
                    logger.debug(f"Error fetching {filename}: {e}")
                    continue
        
        return []
    
    def _parse_changelog_markdown(self, markdown: str) -> list[ChangelogEntry]:
        """Parse changelog entries from markdown text.
        
        Args:
            markdown: Markdown content
            
        Returns:
            List of changelog entries
        """
        entries = []
        
        # Split by version headers (## [1.0.0] or ## 1.0.0 or # v1.0.0)
        version_pattern = r"^##?\s+\[?v?(\d+\.\d+(?:\.\d+)?(?:[a-zA-Z0-9.+-]*)?)\]?"
        
        lines = markdown.split("\n")
        current_version = None
        current_date = None
        current_content = []
        
        for line in lines:
            match = re.match(version_pattern, line, re.MULTILINE)
            
            if match:
                # Save previous entry
                if current_version and current_content:
                    entries.append(
                        ChangelogEntry(
                            version=current_version,
                            release_date=current_date,
                            content="\n".join(current_content).strip(),
                        )
                    )
                
                # Start new entry
                current_version = match.group(1)
                current_content = []
                
                # Try to extract date from header
                date_match = re.search(r"\d{4}-\d{2}-\d{2}", line)
                current_date = date_match.group(0) if date_match else None
            else:
                if current_version:
                    current_content.append(line)
        
        # Save last entry
        if current_version and current_content:
            entries.append(
                ChangelogEntry(
                    version=current_version,
                    release_date=current_date,
                    content="\n".join(current_content).strip(),
                )
            )
        
        return entries
    
    def _fetch_from_pypi_notes(
        self,
        package_name: str,
        version: str | None
    ) -> list[ChangelogEntry]:
        """Fetch release notes from PyPI.
        
        Args:
            package_name: Package name
            version: Version to fetch
            
        Returns:
            List of changelog entries
        """
        if not version:
            return []
        
        try:
            version_info = self.pypi_client.get_version_info(package_name, version)
            
            if not version_info:
                return []
            
            # Check for description/release notes
            description = version_info.get("info", {}).get("description", "")
            
            if description:
                # Try to extract just the release notes section
                notes = self._extract_release_notes(description)
                
                return [
                    ChangelogEntry(
                        version=version,
                        content=notes[:2000],  # Limit size
                    )
                ]
        
        except Exception as e:
            logger.debug(f"Error fetching PyPI notes for {package_name}: {e}")
        
        return []
    
    def _extract_release_notes(self, description: str) -> str:
        """Extract release notes section from package description.
        
        Args:
            description: Full package description
            
        Returns:
            Release notes section or truncated description
        """
        # Try to find common release notes headers
        patterns = [
            r"(?:^|\n)(#+\s*(?:Release Notes|Changelog|What's New|Changes).*?)(?=\n#|\Z)",
            r"(?:^|\n)(Release Notes\n[-=]+.*?)(?=\n[A-Z][a-zA-Z\s]+\n[-=]+|\Z)",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, description, re.IGNORECASE | re.DOTALL)
            if match:
                return match.group(1).strip()
        
        # Otherwise return first 500 chars
        return description[:500]
    
    def close(self) -> None:
        """Close HTTP client."""
        if self.client:
            self.client.close()
        
        self.pypi_client.close()
