"""API surface diffing using griffe with proper version loading."""

import tempfile
import zipfile
from pathlib import Path
from typing import Any
import logging

try:
    import griffe
    GRIFFE_AVAILABLE = True
except ImportError:
    GRIFFE_AVAILABLE = False

import httpx

from upgrade_analyzer.cache import get_cache
from upgrade_analyzer.models import APIChange, ChangeType, UsageNode

logger = logging.getLogger(__name__)


class APIDiffer:
    """Compares API surfaces between package versions using griffe."""
    
    def __init__(self, offline: bool = False) -> None:
        """Initialize API differ.
        
        Args:
            offline: If True, only use cached data
        """
        self.offline = offline
        self.cache = get_cache()
        self.client = httpx.Client(timeout=60.0) if not offline else None
        
        if not GRIFFE_AVAILABLE:
            self.enabled = False
            logger.warning("griffe not available - API diffing disabled")
        else:
            self.enabled = True
    
    def diff_versions(
        self,
        package_name: str,
        old_version: str,
        new_version: str,
        used_symbols: list[UsageNode]
    ) -> list[APIChange]:
        """Compare API surface between two versions.
        
        Args:
            package_name: Name of the package
            old_version: Current version
            new_version: Target version
            used_symbols: Symbols actually used in code
            
        Returns:
            List of API changes affecting used symbols
        """
        if not self.enabled:
            return []
        
        cache_key = f"api_diff:{package_name}:{old_version}:{new_version}"
        
        # Try cache first (never expires for API diffs)
        cached = self.cache.get(cache_key, cache_type="api_diff", ttl_hours=0)
        if cached:
            return self._deserialize_changes(cached)
        
        if self.offline:
            return []
        
        try:
            # Download and load both versions
            old_api = self._download_and_load_package(package_name, old_version)
            new_api = self._download_and_load_package(package_name, new_version)
            
            if not old_api or not new_api:
                logger.warning(f"Could not load API for {package_name} versions {old_version}/{new_version}")
                return []
            
            # Find changes in used symbols only
            changes = self._detect_changes(old_api, new_api, used_symbols)
            
            # Cache results
            if changes:
                cache_data = self._serialize_changes(changes)
                self.cache.set(cache_key, cache_data, cache_type="api_diff")
            
            return changes
        
        except Exception as e:
            logger.error(f"Error diffing API for {package_name}: {e}")
            return []
    
    def _deserialize_changes(self, cached: list[dict]) -> list[APIChange]:
        """Deserialize cached API changes.
        
        Args:
            cached: List of cached change dictionaries
            
        Returns:
            List of APIChange objects
        """
        changes = []
        for change in cached:
            try:
                # Convert string back to ChangeType enum
                change_type = ChangeType(change.get("change_type", "modified"))
                changes.append(
                    APIChange(
                        symbol_name=change.get("symbol_name", ""),
                        change_type=change_type,
                        old_signature=change.get("old_signature"),
                        new_signature=change.get("new_signature"),
                        description=change.get("description", ""),
                    )
                )
            except (ValueError, KeyError) as e:
                logger.warning(f"Error deserializing cached change: {e}")
                continue
        return changes
    
    def _serialize_changes(self, changes: list[APIChange]) -> list[dict]:
        """Serialize API changes for caching.
        
        Args:
            changes: List of APIChange objects
            
        Returns:
            List of dictionaries
        """
        return [
            {
                "symbol_name": c.symbol_name,
                "change_type": c.change_type.value,  # Store as string
                "old_signature": c.old_signature,
                "new_signature": c.new_signature,
                "description": c.description,
            }
            for c in changes
        ]
    
    def _download_and_load_package(self, package_name: str, version: str) -> Any:
        """Download package wheel/sdist and load with griffe.
        
        Args:
            package_name: Package name
            version: Version string
            
        Returns:
            Griffe object or None
        """
        if not GRIFFE_AVAILABLE or not self.client:
            return None
        
        try:
            # Get package info from PyPI
            url = f"https://pypi.org/pypi/{package_name}/{version}/json"
            response = self.client.get(url)
            
            if response.status_code != 200:
                logger.warning(f"Could not fetch {package_name}=={version} from PyPI")
                return None
            
            data = response.json()
            urls = data.get("urls", [])
            
            # Prefer wheel, fallback to sdist
            download_url = None
            for url_info in urls:
                if url_info.get("packagetype") == "bdist_wheel":
                    download_url = url_info.get("url")
                    break
            
            if not download_url:
                for url_info in urls:
                    if url_info.get("packagetype") == "sdist":
                        download_url = url_info.get("url")
                        break
            
            if not download_url:
                logger.warning(f"No downloadable distribution for {package_name}=={version}")
                return None
            
            # Download the package
            response = self.client.get(download_url)
            if response.status_code != 200:
                return None
            
            # Extract and load with griffe
            with tempfile.TemporaryDirectory() as tmpdir:
                tmppath = Path(tmpdir)
                
                # Save and extract
                if download_url.endswith(".whl"):
                    wheel_path = tmppath / "package.whl"
                    wheel_path.write_bytes(response.content)
                    
                    # Extract wheel
                    with zipfile.ZipFile(wheel_path, "r") as zf:
                        zf.extractall(tmppath / "extracted")
                    
                    # Find package directory
                    package_dir = self._find_package_dir(tmppath / "extracted", package_name)
                    
                elif download_url.endswith(".tar.gz"):
                    import tarfile
                    tar_path = tmppath / "package.tar.gz"
                    tar_path.write_bytes(response.content)
                    
                    with tarfile.open(tar_path, "r:gz") as tf:
                        tf.extractall(tmppath / "extracted")
                    
                    package_dir = self._find_package_dir(tmppath / "extracted", package_name)
                else:
                    return None
                
                if package_dir and package_dir.exists():
                    # Load with griffe
                    return griffe.load(
                        package_name,
                        search_paths=[str(package_dir.parent)],
                        resolve_aliases=True,
                    )
            
            return None
            
        except Exception as e:
            logger.error(f"Error downloading {package_name}=={version}: {e}")
            return None
    
    def _find_package_dir(self, base_path: Path, package_name: str) -> Path | None:
        """Find the package directory in extracted archive.
        
        Args:
            base_path: Base extraction path
            package_name: Package name to find
            
        Returns:
            Path to package directory or None
        """
        # Normalize package name (replace - with _)
        normalized_name = package_name.replace("-", "_").lower()
        
        # Search for package directory
        for path in base_path.rglob("*"):
            if path.is_dir():
                dir_name = path.name.lower().replace("-", "_")
                if dir_name == normalized_name:
                    return path
        
        # Also check for top-level directories
        for path in base_path.iterdir():
            if path.is_dir():
                # Check subdirectories
                for subpath in path.iterdir():
                    if subpath.is_dir():
                        dir_name = subpath.name.lower().replace("-", "_")
                        if dir_name == normalized_name:
                            return subpath
        
        return None
    
    def _detect_changes(
        self,
        old_api: Any,
        new_api: Any,
        used_symbols: list[UsageNode]
    ) -> list[APIChange]:
        """Detect changes between API versions.
        
        Args:
            old_api: Old API object
            new_api: New API object
            used_symbols: Symbols used in code
            
        Returns:
            List of API changes
        """
        changes: list[APIChange] = []
        
        # Extract symbols we care about
        symbol_paths = {node.symbol_path for node in used_symbols}
        
        for symbol_path in symbol_paths:
            # Check if symbol exists in both versions
            old_symbol = self._get_symbol(old_api, symbol_path)
            new_symbol = self._get_symbol(new_api, symbol_path)
            
            if old_symbol and not new_symbol:
                # Symbol was removed
                changes.append(
                    APIChange(
                        symbol_name=symbol_path,
                        change_type=ChangeType.REMOVED,
                        old_signature=self._get_signature(old_symbol),
                        description=f"Symbol '{symbol_path}' was removed",
                    )
                )
            
            elif old_symbol and new_symbol:
                # Symbol exists in both - check for signature changes
                old_sig = self._get_signature(old_symbol)
                new_sig = self._get_signature(new_symbol)
                
                if old_sig != new_sig:
                    changes.append(
                        APIChange(
                            symbol_name=symbol_path,
                            change_type=ChangeType.MODIFIED,
                            old_signature=old_sig,
                            new_signature=new_sig,
                            description=f"Signature changed for '{symbol_path}'",
                        )
                    )
                
                # Check for deprecation
                if self._is_deprecated(new_symbol):
                    changes.append(
                        APIChange(
                            symbol_name=symbol_path,
                            change_type=ChangeType.DEPRECATED,
                            new_signature=new_sig,
                            description=f"'{symbol_path}' is now deprecated",
                        )
                    )
        
        return changes
    
    def _get_symbol(self, api: Any, symbol_path: str) -> Any:
        """Get symbol from API object by path.
        
        Args:
            api: API object
            symbol_path: Dot-separated symbol path
            
        Returns:
            Symbol object or None
        """
        if not GRIFFE_AVAILABLE or not api:
            return None
        
        try:
            parts = symbol_path.split(".")
            obj = api
            
            for part in parts[1:]:  # Skip package name
                if hasattr(obj, "members") and part in obj.members:
                    obj = obj.members[part]
                else:
                    return None
            
            return obj
        
        except Exception as e:
            logger.debug(f"Could not find symbol {symbol_path}: {e}")
            return None
    
    def _get_signature(self, symbol: Any) -> str:
        """Get signature of a symbol.
        
        Args:
            symbol: Symbol object
            
        Returns:
            Signature string
        """
        if not symbol:
            return ""
        
        try:
            # Try to get function/method signature
            if hasattr(symbol, "parameters"):
                params = ", ".join(str(p) for p in symbol.parameters)
                return f"({params})"
            
            return str(symbol)
        
        except Exception:
            return ""
    
    def _is_deprecated(self, symbol: Any) -> bool:
        """Check if symbol is deprecated.
        
        Args:
            symbol: Symbol object
            
        Returns:
            True if deprecated
        """
        if not symbol:
            return False
        
        try:
            # Check docstring for deprecation warnings
            if hasattr(symbol, "docstring") and symbol.docstring:
                docstring = str(symbol.docstring).lower()
                
                if "deprecated" in docstring or ".. deprecated::" in docstring:
                    return True
            
            # Check decorators
            if hasattr(symbol, "decorators"):
                for decorator in symbol.decorators:
                    if "deprecated" in str(decorator).lower():
                        return True
        
        except Exception:
            pass
        
        return False
    
    def close(self) -> None:
        """Close HTTP client."""
        if self.client:
            self.client.close()
