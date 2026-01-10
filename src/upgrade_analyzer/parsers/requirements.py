"""Parser for requirements.txt files."""

import re
from pathlib import Path

from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet

from upgrade_analyzer.models import Dependency
from upgrade_analyzer.parsers.base import DependencyParser


class RequirementsParser(DependencyParser):
    """Parser for requirements.txt format."""
    
    def parse(self) -> list[Dependency]:
        """Parse requirements.txt file.
        
        Returns:
            List of dependencies
        """
        dependencies: list[Dependency] = []
        
        with open(self.file_path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                
                # Skip empty lines and comments
                if not line or line.startswith("#"):
                    continue
                
                # Skip -r/-e flags and URLs
                if line.startswith("-r") or line.startswith("-e") or line.startswith("git+"):
                    continue
                
                try:
                    dep = self._parse_requirement(line)
                    if dep:
                        dependencies.append(dep)
                except Exception:
                    # Skip invalid lines
                    continue
        
        return dependencies
    
    def _parse_requirement(self, line: str) -> Dependency | None:
        """Parse a single requirement line.
        
        Args:
            line: Requirement line
            
        Returns:
            Dependency or None if invalid
        """
        try:
            # Use packaging library to parse requirement
            req = Requirement(line)
            
            # Extract version from specifier
            current_version = self._extract_version(req.specifier)
            
            if current_version:
                return Dependency(
                    name=req.name,
                    current_version=current_version,
                    source_file=self.file_path,
                    extras=list(req.extras) if req.extras else [],
                )
        except Exception:
            # Try manual parsing as fallback
            return self._manual_parse(line)
        
        return None
    
    def _extract_version(self, specifier: SpecifierSet) -> str | None:
        """Extract concrete version from specifier set.
        
        Args:
            specifier: Version specifier set
            
        Returns:
            Version string or None
        """
        # Look for exact version (==)
        for spec in specifier:
            if spec.operator == "==":
                return spec.version
        
        # If no exact version, try to extract from other operators
        for spec in specifier:
            if spec.operator in {">=", "~=", ">"}:
                return spec.version
        
        return None
    
    def _manual_parse(self, line: str) -> Dependency | None:
        """Manually parse requirement line as fallback.
        
        Args:
            line: Requirement line
            
        Returns:
            Dependency or None
        """
        # Simple regex for package==version or package>=version
        pattern = r"^([a-zA-Z0-9_-]+)\s*([=<>~!]+)\s*([0-9.]+.*?)(?:\s|$)"
        match = re.match(pattern, line)
        
        if match:
            name, operator, version = match.groups()
            
            # Clean version string
            version = version.strip().rstrip(";").strip()
            
            return Dependency(
                name=name,
                current_version=version,
                source_file=self.file_path,
            )
        
        return None
    
    def get_dependency_tree(self) -> dict[str, list[str]]:
        """Get dependency tree.
        
        Note: requirements.txt doesn't contain transitive dependency info.
        This would need to be resolved via pip or PyPI.
        
        Returns:
            Dictionary with direct dependencies only
        """
        dependencies = self.parse()
        
        # Return only direct dependencies (no transitive info in requirements.txt)
        return {dep.name: [] for dep in dependencies}
