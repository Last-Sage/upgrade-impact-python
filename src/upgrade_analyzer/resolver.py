"""Dependency resolution and version management with transitive support."""

import logging
from packaging.version import Version, parse as parse_version, InvalidVersion

import httpx

from upgrade_analyzer.cache import get_cache
from upgrade_analyzer.models import Dependency

logger = logging.getLogger(__name__)


class DependencyResolver:
    """Resolves dependency versions using PyPI API."""
    
    def __init__(self, offline: bool = False) -> None:
        """Initialize resolver.
        
        Args:
            offline: If True, only use cached data
        """
        self.offline = offline
        self.cache = get_cache()
        self.client = httpx.Client(timeout=30.0) if not offline else None
    
    def get_latest_version(self, package_name: str) -> str | None:
        """Get latest version of a package from PyPI.
        
        Args:
            package_name: Name of the package
            
        Returns:
            Latest version string or None if not found
        """
        cache_key = f"latest:{package_name}"
        
        # Try cache first
        cached = self.cache.get(cache_key, cache_type="pypi", ttl_hours=24)
        if cached:
            return cached
        
        if self.offline:
            return None
        
        try:
            url = f"https://pypi.org/pypi/{package_name}/json"
            response = self.client.get(url)
            
            if response.status_code == 200:
                data = response.json()
                latest = data.get("info", {}).get("version")
                
                if latest:
                    # Cache the result
                    self.cache.set(cache_key, latest, cache_type="pypi")
                    return latest
        
        except httpx.RequestError as e:
            logger.error(f"Network error fetching {package_name}: {e}")
        except Exception as e:
            logger.error(f"Error fetching latest version for {package_name}: {e}")
        
        return None
    
    def get_version_history(self, package_name: str) -> list[str]:
        """Get all available versions of a package.
        
        Args:
            package_name: Name of the package
            
        Returns:
            List of version strings sorted from oldest to newest
        """
        cache_key = f"versions:{package_name}"
        
        # Try cache first
        cached = self.cache.get(cache_key, cache_type="pypi", ttl_hours=24)
        if cached:
            return cached
        
        if self.offline:
            return []
        
        try:
            url = f"https://pypi.org/pypi/{package_name}/json"
            response = self.client.get(url)
            
            if response.status_code == 200:
                data = response.json()
                releases = data.get("releases", {})
                
                # Filter out pre-releases and sort by version
                versions = []
                for version_str in releases.keys():
                    try:
                        version = parse_version(version_str)
                        # Only include stable releases
                        if not version.is_prerelease:
                            versions.append(version)
                    except InvalidVersion:
                        continue
                
                # Sort versions
                versions.sort()
                version_strings = [str(v) for v in versions]
                
                # Cache the result
                self.cache.set(cache_key, version_strings, cache_type="pypi")
                return version_strings
        
        except httpx.RequestError as e:
            logger.error(f"Network error fetching versions for {package_name}: {e}")
        except Exception as e:
            logger.error(f"Error fetching version history for {package_name}: {e}")
        
        return []
    
    def get_package_metadata(self, package_name: str) -> dict:
        """Get package metadata from PyPI.
        
        Args:
            package_name: Name of the package
            
        Returns:
            Dictionary of package metadata
        """
        cache_key = f"metadata:{package_name}"
        
        # Try cache first
        cached = self.cache.get(cache_key, cache_type="pypi", ttl_hours=24)
        if cached:
            return cached
        
        if self.offline:
            return {}
        
        try:
            url = f"https://pypi.org/pypi/{package_name}/json"
            response = self.client.get(url)
            
            if response.status_code == 200:
                data = response.json()
                metadata = {
                    "name": data.get("info", {}).get("name", package_name),
                    "version": data.get("info", {}).get("version"),
                    "summary": data.get("info", {}).get("summary"),
                    "home_page": data.get("info", {}).get("home_page"),
                    "project_urls": data.get("info", {}).get("project_urls", {}),
                    "requires_python": data.get("info", {}).get("requires_python"),
                    "requires_dist": data.get("info", {}).get("requires_dist", []),
                }
                
                # Cache the result
                self.cache.set(cache_key, metadata, cache_type="pypi")
                return metadata
        
        except httpx.RequestError as e:
            logger.error(f"Network error fetching metadata for {package_name}: {e}")
        except Exception as e:
            logger.error(f"Error fetching metadata for {package_name}: {e}")
        
        return {}
    
    def get_transitive_dependencies(
        self,
        package_name: str,
        version: str | None = None,
        depth: int = 3,
        seen: set[str] | None = None
    ) -> list[Dependency]:
        """Get transitive dependencies of a package.
        
        Args:
            package_name: Name of the package
            version: Specific version (None = latest)
            depth: Maximum recursion depth
            seen: Set of already-processed packages (for cycle detection)
            
        Returns:
            List of transitive dependencies
        """
        if seen is None:
            seen = set()
        
        if package_name.lower() in seen or depth <= 0:
            return []
        
        seen.add(package_name.lower())
        dependencies: list[Dependency] = []
        
        try:
            # Fetch metadata for specific version
            if version:
                cache_key = f"version_metadata:{package_name}:{version}"
                cached = self.cache.get(cache_key, cache_type="pypi", ttl_hours=168)
                
                if cached:
                    requires_dist = cached.get("requires_dist", [])
                elif not self.offline and self.client:
                    url = f"https://pypi.org/pypi/{package_name}/{version}/json"
                    response = self.client.get(url)
                    
                    if response.status_code == 200:
                        data = response.json()
                        requires_dist = data.get("info", {}).get("requires_dist", []) or []
                        
                        # Cache the result
                        self.cache.set(cache_key, {"requires_dist": requires_dist}, cache_type="pypi")
                    else:
                        requires_dist = []
                else:
                    requires_dist = []
            else:
                metadata = self.get_package_metadata(package_name)
                requires_dist = metadata.get("requires_dist", []) or []
            
            # Parse dependencies
            for req_str in requires_dist:
                parsed = self._parse_requirement(req_str)
                if parsed:
                    dep_name, dep_version, extras, is_optional = parsed
                    
                    # Skip optional/extra dependencies
                    if is_optional:
                        continue
                    
                    dep = Dependency(
                        name=dep_name,
                        current_version=dep_version or "*",
                        is_transitive=True,
                        extras=extras,
                    )
                    dependencies.append(dep)
                    
                    # Recursively get transitive deps
                    if depth > 1:
                        sub_deps = self.get_transitive_dependencies(
                            dep_name,
                            dep_version,
                            depth - 1,
                            seen
                        )
                        dependencies.extend(sub_deps)
        
        except Exception as e:
            logger.error(f"Error getting transitive deps for {package_name}: {e}")
        
        return dependencies
    
    def _parse_requirement(self, req_str: str) -> tuple[str, str | None, list[str], bool] | None:
        """Parse a requirement string.
        
        Args:
            req_str: Requirement string (e.g., "requests>=2.0; python_version>='3.6'")
            
        Returns:
            Tuple of (name, version, extras, is_optional) or None
        """
        try:
            # Remove environment markers
            req_str = req_str.split(";")[0].strip()
            
            # Check if it's optional (extra requirement)
            is_optional = "extra ==" in req_str.lower() or "extra==" in req_str.lower()
            
            # Extract extras
            extras = []
            if "[" in req_str and "]" in req_str:
                extras_start = req_str.index("[")
                extras_end = req_str.index("]")
                extras_str = req_str[extras_start+1:extras_end]
                extras = [e.strip() for e in extras_str.split(",")]
                req_str = req_str[:extras_start] + req_str[extras_end+1:]
            
            # Parse name and version
            for op in [">=", "<=", "==", "~=", "!=", ">", "<"]:
                if op in req_str:
                    parts = req_str.split(op, 1)
                    name = parts[0].strip()
                    version = parts[1].strip() if len(parts) > 1 else None
                    return (name, version, extras, is_optional)
            
            # No version specifier
            return (req_str.strip(), None, extras, is_optional)
            
        except Exception:
            return None
    
    def suggest_upgrade_path(
        self,
        dependency: Dependency,
        target_version: str | None = None
    ) -> list[str]:
        """Suggest incremental upgrade path.
        
        Args:
            dependency: Current dependency
            target_version: Target version (None = latest)
            
        Returns:
            List of versions to upgrade through
        """
        if target_version is None:
            target_version = self.get_latest_version(dependency.name)
        
        if not target_version:
            return []
        
        # Get all versions
        all_versions = self.get_version_history(dependency.name)
        
        if not all_versions:
            return [target_version]
        
        try:
            current = parse_version(dependency.current_version)
            target = parse_version(target_version)
            
            # If target is older than current, just return target
            if target <= current:
                return []
            
            # Find intermediate versions
            intermediate = []
            
            for version_str in all_versions:
                version = parse_version(version_str)
                
                if current < version <= target:
                    intermediate.append(version)
            
            # Sort and convert to strings
            intermediate.sort()
            path = [str(v) for v in intermediate]
            
            # If path is too long, suggest major version milestones only
            if len(path) > 5:
                path = self._select_milestones(path, current, target)
            
            return path
        
        except InvalidVersion as e:
            logger.warning(f"Invalid version format: {e}")
            return [target_version]
        except Exception as e:
            logger.error(f"Error suggesting upgrade path: {e}")
            return [target_version]
    
    def _select_milestones(
        self,
        versions: list[str],
        current: Version,
        target: Version
    ) -> list[str]:
        """Select major version milestones from a long upgrade path.
        
        Args:
            versions: All intermediate versions
            current: Current version
            target: Target version
            
        Returns:
            List of milestone versions
        """
        milestones = []
        
        # Always include target
        target_str = str(target)
        
        # Find major version boundaries
        seen_major = {current.major}
        
        for version_str in versions:
            try:
                version = parse_version(version_str)
                
                # Track major version changes
                if version.major not in seen_major:
                    milestones.append(version_str)
                    seen_major.add(version.major)
            except InvalidVersion:
                continue
        
        # Add target if not already included
        if target_str not in milestones:
            milestones.append(target_str)
        
        return milestones
    
    def compare_versions(self, version1: str, version2: str) -> int:
        """Compare two version strings.
        
        Args:
            version1: First version
            version2: Second version
            
        Returns:
            -1 if version1 < version2, 0 if equal, 1 if version1 > version2
        """
        try:
            v1 = parse_version(version1)
            v2 = parse_version(version2)
            
            if v1 < v2:
                return -1
            elif v1 > v2:
                return 1
            else:
                return 0
        except InvalidVersion:
            return 0
    
    def calculate_version_distance(self, version1: str, version2: str) -> dict[str, int]:
        """Calculate semantic distance between versions.
        
        Args:
            version1: First version
            version2: Second version
            
        Returns:
            Dictionary with major, minor, patch differences
        """
        try:
            v1 = parse_version(version1)
            v2 = parse_version(version2)
            
            # Use packaging's parsed version components
            v1_release = v1.release if hasattr(v1, 'release') else (0, 0, 0)
            v2_release = v2.release if hasattr(v2, 'release') else (0, 0, 0)
            
            v1_major = v1_release[0] if len(v1_release) > 0 else 0
            v1_minor = v1_release[1] if len(v1_release) > 1 else 0
            v1_patch = v1_release[2] if len(v1_release) > 2 else 0
            
            v2_major = v2_release[0] if len(v2_release) > 0 else 0
            v2_minor = v2_release[1] if len(v2_release) > 1 else 0
            v2_patch = v2_release[2] if len(v2_release) > 2 else 0
            
            return {
                "major": abs(v2_major - v1_major),
                "minor": abs(v2_minor - v1_minor),
                "patch": abs(v2_patch - v1_patch),
            }
        
        except InvalidVersion as e:
            logger.warning(f"Invalid version for distance calculation: {e}")
            return {"major": 0, "minor": 0, "patch": 0}
        except Exception as e:
            logger.error(f"Error calculating version distance: {e}")
            return {"major": 0, "minor": 0, "patch": 0}
    
    def close(self) -> None:
        """Close HTTP client."""
        if self.client:
            self.client.close()
