"""File discovery for Python projects."""

import fnmatch
from pathlib import Path

from upgrade_analyzer.config import get_config


class FileDiscovery:
    """Discovers Python files in a project."""
    
    def __init__(
        self,
        project_root: Path,
        exclude_patterns: list[str] | None = None
    ) -> None:
        """Initialize file discovery.
        
        Args:
            project_root: Root directory of the project
            exclude_patterns: Glob patterns to exclude
        """
        self.project_root = Path(project_root)
        
        if exclude_patterns is None:
            config = get_config()
            exclude_patterns = config.exclude_patterns
        
        self.exclude_patterns = exclude_patterns
    
    def find_python_files(self) -> list[Path]:
        """Find all Python files in the project.
        
        Returns:
            List of Python file paths
        """
        python_files: list[Path] = []
        
        # Recursively find .py files
        for py_file in self.project_root.rglob("*.py"):
            # Check if file should be excluded
            if not self._should_exclude(py_file):
                python_files.append(py_file)
        
        return python_files
    
    def _should_exclude(self, file_path: Path) -> bool:
        """Check if file should be excluded based on patterns.
        
        Args:
            file_path: Path to file
            
        Returns:
            True if file should be excluded
        """
        # Get relative path for pattern matching
        try:
            relative = file_path.relative_to(self.project_root)
            relative_str = str(relative).replace("\\", "/")
        except ValueError:
            return False
        
        # Check against exclude patterns
        for pattern in self.exclude_patterns:
            # Convert pattern to work with fnmatch
            pattern_normalized = pattern.replace("**", "*")
            
            if fnmatch.fnmatch(relative_str, pattern_normalized):
                return True
            
            # Also check each parent directory
            for parent in relative.parents:
                parent_str = str(parent).replace("\\", "/")
                if fnmatch.fnmatch(parent_str, pattern_normalized):
                    return True
        
        return False
