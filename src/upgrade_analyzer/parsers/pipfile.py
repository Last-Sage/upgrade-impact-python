"""Parser for Pipfile files."""

from pathlib import Path

import toml

from upgrade_analyzer.models import Dependency
from upgrade_analyzer.parsers.base import DependencyParser


class PipfileParser(DependencyParser):
    """Parser for Pipfile format."""
    
    def parse(self) -> list[Dependency]:
        """Parse Pipfile.
        
        Returns:
            List of dependencies
        """
        dependencies: list[Dependency] = []
        
        try:
            data = toml.load(self.file_path)
        except Exception:
            return dependencies
        
        # Parse [packages] section
        if "packages" in data:
            deps = self._parse_packages(data["packages"])
            dependencies.extend(deps)
        
        return dependencies
    
    def _parse_packages(
        self,
        packages: dict[str, str | dict]
    ) -> list[Dependency]:
        """Parse packages section.
        
        Args:
            packages: Dictionary of packages
            
        Returns:
            List of Dependency objects
        """
        dependencies: list[Dependency] = []
        
        for name, spec in packages.items():
            version = None
            
            # Handle string format: "==1.0.0" or "*"
            if isinstance(spec, str):
                if spec == "*":
                    # Wildcard - we'll need to fetch latest from PyPI
                    continue
                else:
                    version = spec.lstrip("=<>~!")
            
            # Handle dict format: {version = "==1.0.0"}
            elif isinstance(spec, dict):
                if "version" in spec:
                    version = spec["version"].lstrip("=<>~!")
            
            if version:
                dependencies.append(
                    Dependency(
                        name=name,
                        current_version=version,
                        source_file=self.file_path,
                    )
                )
        
        return dependencies
    
    def get_dependency_tree(self) -> dict[str, list[str]]:
        """Get dependency tree.
        
        Note: Pipfile doesn't contain transitive dependency info.
        
        Returns:
            Dictionary with direct dependencies only
        """
        dependencies = self.parse()
        
        return {dep.name: [] for dep in dependencies}
