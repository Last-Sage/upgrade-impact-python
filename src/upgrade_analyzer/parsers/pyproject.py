"""Parser for pyproject.toml files (Poetry/Hatch/PEP621)."""

from pathlib import Path

import toml
from packaging.requirements import Requirement

from upgrade_analyzer.models import Dependency
from upgrade_analyzer.parsers.base import DependencyParser


class PyprojectParser(DependencyParser):
    """Parser for pyproject.toml format."""
    
    def parse(self) -> list[Dependency]:
        """Parse pyproject.toml file.
        
        Returns:
            List of dependencies
        """
        dependencies: list[Dependency] = []
        
        try:
            data = toml.load(self.file_path)
        except Exception:
            return dependencies
        
        # Try PEP 621 format first ([project.dependencies])
        if "project" in data and "dependencies" in data["project"]:
            deps = self._parse_pep621_dependencies(data["project"]["dependencies"])
            dependencies.extend(deps)
        
        # Try Poetry format ([tool.poetry.dependencies])
        elif "tool" in data and "poetry" in data["tool"]:
            if "dependencies" in data["tool"]["poetry"]:
                deps = self._parse_poetry_dependencies(
                    data["tool"]["poetry"]["dependencies"]
                )
                dependencies.extend(deps)
        
        return dependencies
    
    def _parse_pep621_dependencies(self, deps: list[str]) -> list[Dependency]:
        """Parse PEP 621 dependencies.
        
        Args:
            deps: List of dependency strings
            
        Returns:
            List of Dependency objects
        """
        dependencies: list[Dependency] = []
        
        for dep_str in deps:
            try:
                req = Requirement(dep_str)
                
                # Extract version
                version = None
                for spec in req.specifier:
                    if spec.operator == "==":
                        version = spec.version
                        break
                    elif spec.operator in {">=", "~=", ">"}:
                        version = spec.version
                
                if version:
                    dependencies.append(
                        Dependency(
                            name=req.name,
                            current_version=version,
                            source_file=self.file_path,
                            extras=list(req.extras) if req.extras else [],
                        )
                    )
            except Exception:
                continue
        
        return dependencies
    
    def _parse_poetry_dependencies(
        self,
        deps: dict[str, str | dict]
    ) -> list[Dependency]:
        """Parse Poetry-style dependencies.
        
        Args:
            deps: Dictionary of dependencies
            
        Returns:
            List of Dependency objects
        """
        dependencies: list[Dependency] = []
        
        for name, spec in deps.items():
            # Skip Python itself
            if name.lower() == "python":
                continue
            
            version = None
            extras: list[str] = []
            
            # Handle string format: "^1.0.0" or ">=1.0.0"
            if isinstance(spec, str):
                version = self._normalize_poetry_version(spec)
            
            # Handle dict format: {version = "^1.0.0", extras = ["security"]}
            elif isinstance(spec, dict):
                if "version" in spec:
                    version = self._normalize_poetry_version(spec["version"])
                
                if "extras" in spec:
                    extras = spec["extras"] if isinstance(spec["extras"], list) else []
            
            if version:
                dependencies.append(
                    Dependency(
                        name=name,
                        current_version=version,
                        source_file=self.file_path,
                        extras=extras,
                    )
                )
        
        return dependencies
    
    @staticmethod
    def _normalize_poetry_version(version_str: str) -> str:
        """Normalize Poetry version string (e.g., ^1.0.0 -> 1.0.0).
        
        Args:
            version_str: Poetry version string
            
        Returns:
            Normalized version
        """
        # Remove Poetry-specific operators
        version = version_str.lstrip("^~<>=!")
        return version.strip()
    
    def get_dependency_tree(self) -> dict[str, list[str]]:
        """Get dependency tree.
        
        Note: pyproject.toml doesn't typically contain transitive dependency info.
        
        Returns:
            Dictionary with direct dependencies only
        """
        dependencies = self.parse()
        
        # Return only direct dependencies
        return {dep.name: [] for dep in dependencies}
