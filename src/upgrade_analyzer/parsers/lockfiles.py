"""Poetry lock file parser."""

import json
import logging
from pathlib import Path

import toml

from upgrade_analyzer.models import Dependency
from upgrade_analyzer.parsers.base import DependencyParser

logger = logging.getLogger(__name__)


class PoetryLockParser(DependencyParser):
    """Parse poetry.lock files."""
    
    def can_parse(self) -> bool:
        """Check if this parser can handle the file."""
        return self.file_path.name == "poetry.lock"
    
    def parse(self) -> list[Dependency]:
        """Parse poetry.lock file.
        
        Returns:
            List of dependencies
        """
        dependencies: list[Dependency] = []
        
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            # poetry.lock is TOML format
            data = toml.loads(content)
            
            packages = data.get("package", [])
            
            for package in packages:
                name = package.get("name", "")
                version = package.get("version", "")
                
                if not name:
                    continue
                
                # Check if it's optional/development dependency
                category = package.get("category", "main")
                
                dep = Dependency(
                    name=name,
                    current_version=version,
                    source_file=self.file_path,
                    is_transitive=category != "main",
                )
                
                dependencies.append(dep)
        
        except toml.TomlDecodeError as e:
            logger.error(f"Error parsing poetry.lock: {e}")
        except Exception as e:
            logger.error(f"Unexpected error parsing poetry.lock: {e}")
        
        return dependencies


class PipfileLockParser(DependencyParser):
    """Parse Pipfile.lock files."""
    
    def can_parse(self) -> bool:
        """Check if this parser can handle the file."""
        return self.file_path.name == "Pipfile.lock"
    
    def parse(self) -> list[Dependency]:
        """Parse Pipfile.lock file.
        
        Returns:
            List of dependencies
        """
        dependencies: list[Dependency] = []
        
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # Parse default dependencies
            default_deps = data.get("default", {})
            for name, info in default_deps.items():
                version = self._extract_version(info)
                
                dep = Dependency(
                    name=name,
                    current_version=version,
                    source_file=self.file_path,
                )
                
                dependencies.append(dep)
            
            # Parse dev dependencies
            develop_deps = data.get("develop", {})
            for name, info in develop_deps.items():
                version = self._extract_version(info)
                
                dep = Dependency(
                    name=name,
                    current_version=version,
                    source_file=self.file_path,
                )
                
                dependencies.append(dep)
        
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing Pipfile.lock: {e}")
        except Exception as e:
            logger.error(f"Unexpected error parsing Pipfile.lock: {e}")
        
        return dependencies
    
    def _extract_version(self, info: dict) -> str:
        """Extract version from package info.
        
        Args:
            info: Package info dictionary
            
        Returns:
            Version string
        """
        version = info.get("version", "")
        
        # Remove leading "==" if present
        if version.startswith("=="):
            version = version[2:]
        
        return version


class CondaEnvironmentParser(DependencyParser):
    """Parse conda environment.yml files."""
    
    def can_parse(self) -> bool:
        """Check if this parser can handle the file."""
        return self.file_path.name in {"environment.yml", "environment.yaml"}
    
    def parse(self) -> list[Dependency]:
        """Parse conda environment file.
        
        Returns:
            List of dependencies
        """
        dependencies: list[Dependency] = []
        
        try:
            import yaml
        except ImportError:
            logger.warning("PyYAML not installed - cannot parse conda environment files")
            return []
        
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            
            deps_list = data.get("dependencies", [])
            
            for dep in deps_list:
                if isinstance(dep, str):
                    # Parse conda package string
                    parsed = self._parse_conda_spec(dep)
                    if parsed:
                        dependencies.append(parsed)
                
                elif isinstance(dep, dict):
                    # Handle pip dependencies
                    pip_deps = dep.get("pip", [])
                    for pip_dep in pip_deps:
                        parsed = self._parse_pip_spec(pip_dep)
                        if parsed:
                            dependencies.append(parsed)
        
        except Exception as e:
            logger.error(f"Error parsing conda environment: {e}")
        
        return dependencies
    
    def _parse_conda_spec(self, spec: str) -> Dependency | None:
        """Parse conda package specification.
        
        Args:
            spec: Package specification (e.g., "numpy=1.24.0" or "numpy>=1.20")
            
        Returns:
            Dependency or None
        """
        try:
            # Handle different separators
            for sep in ["==", "=", ">=", "<=", ">", "<"]:
                if sep in spec:
                    parts = spec.split(sep, 1)
                    name = parts[0].strip()
                    version = parts[1].strip() if len(parts) > 1 else ""
                    
                    return Dependency(
                        name=name,
                        current_version=version,
                        source_file=self.file_path,
                    )
            
            # No version specified
            return Dependency(
                name=spec.strip(),
                current_version="*",
                source_file=self.file_path,
            )
        
        except Exception:
            return None
    
    def _parse_pip_spec(self, spec: str) -> Dependency | None:
        """Parse pip package specification.
        
        Args:
            spec: Package specification
            
        Returns:
            Dependency or None
        """
        try:
            for sep in ["==", ">=", "<=", "~=", "!=", ">", "<"]:
                if sep in spec:
                    parts = spec.split(sep, 1)
                    name = parts[0].strip()
                    version = parts[1].strip() if len(parts) > 1 else ""
                    
                    return Dependency(
                        name=name,
                        current_version=version,
                        source_file=self.file_path,
                    )
            
            return Dependency(
                name=spec.strip(),
                current_version="*",
                source_file=self.file_path,
            )
        
        except Exception:
            return None


class SetupPyParser(DependencyParser):
    """Parse setup.py files (limited support)."""
    
    def can_parse(self) -> bool:
        """Check if this parser can handle the file."""
        return self.file_path.name == "setup.py"
    
    def parse(self) -> list[Dependency]:
        """Parse setup.py file using regex (does not execute).
        
        Returns:
            List of dependencies
        """
        import re
        
        dependencies: list[Dependency] = []
        
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            # Find install_requires list
            install_requires_match = re.search(
                r"install_requires\s*=\s*\[(.*?)\]",
                content,
                re.DOTALL
            )
            
            if install_requires_match:
                deps_str = install_requires_match.group(1)
                
                # Extract quoted strings
                dep_strings = re.findall(r'["\']([^"\']+)["\']', deps_str)
                
                for dep_str in dep_strings:
                    parsed = self._parse_requirement(dep_str)
                    if parsed:
                        dependencies.append(parsed)
        
        except Exception as e:
            logger.error(f"Error parsing setup.py: {e}")
        
        return dependencies
    
    def _parse_requirement(self, req_str: str) -> Dependency | None:
        """Parse a requirement string.
        
        Args:
            req_str: Requirement string
            
        Returns:
            Dependency or None
        """
        try:
            req_str = req_str.strip()
            
            for sep in ["==", ">=", "<=", "~=", "!=", ">", "<"]:
                if sep in req_str:
                    parts = req_str.split(sep, 1)
                    name = parts[0].strip()
                    version = parts[1].strip()
                    
                    return Dependency(
                        name=name,
                        current_version=version,
                        source_file=self.file_path,
                    )
            
            return Dependency(
                name=req_str,
                current_version="*",
                source_file=self.file_path,
            )
        
        except Exception:
            return None
