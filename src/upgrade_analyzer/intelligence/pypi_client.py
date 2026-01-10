"""PyPI API client."""

import httpx

from upgrade_analyzer.cache import get_cache


class PyPIClient:
    """Client for interacting with PyPI JSON API."""
    
    def __init__(self, offline: bool = False) -> None:
        """Initialize PyPI client.
        
        Args:
            offline: If True, only use cached data
        """
        self.offline = offline
        self.cache = get_cache()
        self.client = httpx.Client(timeout=30.0) if not offline else None
        self.base_url = "https://pypi.org/pypi"
    
    def fetch_package_info(self, package_name: str) -> dict:
        """Fetch complete package information.
        
        Args:
            package_name: Name of the package
            
        Returns:
            Package information dictionary
        """
        cache_key = f"package_info:{package_name}"
        
        # Try cache first
        cached = self.cache.get(cache_key, cache_type="pypi", ttl_hours=24)
        if cached:
            return cached
        
        if self.offline:
            return {}
        
        try:
            url = f"{self.base_url}/{package_name}/json"
            response = self.client.get(url)  # type: ignore
            
            if response.status_code == 200:
                data = response.json()
                
                # Cache the result
                self.cache.set(cache_key, data, cache_type="pypi")
                return data
        
        except Exception:
            pass
        
        return {}
    
    def get_version_info(self, package_name: str, version: str) -> dict:
        """Get information about a specific version.
        
        Args:
            package_name: Name of the package
            version: Version string
            
        Returns:
            Version information dictionary
        """
        cache_key = f"version_info:{package_name}:{version}"
        
        # Try cache first
        cached = self.cache.get(cache_key, cache_type="pypi", ttl_hours=168)  # 1 week
        if cached:
            return cached
        
        if self.offline:
            return {}
        
        try:
            url = f"{self.base_url}/{package_name}/{version}/json"
            response = self.client.get(url)  # type: ignore
            
            if response.status_code == 200:
                data = response.json()
                
                # Cache the result
                self.cache.set(cache_key, data, cache_type="pypi")
                return data
        
        except Exception:
            pass
        
        return {}
    
    def get_project_urls(self, package_name: str) -> dict[str, str]:
        """Get project URLs (homepage, repository, etc.).
        
        Args:
            package_name: Name of the package
            
        Returns:
            Dictionary of project URLs
        """
        info = self.fetch_package_info(package_name)
        
        if not info:
            return {}
        
        urls = {}
        
        # Get from info section
        package_info = info.get("info", {})
        
        if "home_page" in package_info and package_info["home_page"]:
            urls["homepage"] = package_info["home_page"]
        
        if "project_urls" in package_info:
            project_urls = package_info["project_urls"]
            
            if isinstance(project_urls, dict):
                urls.update(project_urls)
        
        return urls
    
    def get_github_repo(self, package_name: str) -> tuple[str, str] | None:
        """Extract GitHub repository owner and name.
        
        Args:
            package_name: Name of the package
            
        Returns:
            Tuple of (owner, repo) or None
        """
        urls = self.get_project_urls(package_name)
        
        for url in urls.values():
            if "github.com" in url:
                # Parse GitHub URL
                parts = url.rstrip("/").split("/")
                
                if len(parts) >= 2:
                    repo = parts[-1]
                    owner = parts[-2]
                    
                    # Remove .git suffix if present
                    if repo.endswith(".git"):
                        repo = repo[:-4]
                    
                    return (owner, repo)
        
        return None
    
    def close(self) -> None:
        """Close HTTP client."""
        if self.client:
            self.client.close()
