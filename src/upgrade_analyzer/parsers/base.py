"""Base class for dependency parsers."""

from abc import ABC, abstractmethod
import logging
from pathlib import Path

from upgrade_analyzer.models import Dependency

logger = logging.getLogger(__name__)


class DependencyParser(ABC):
    """Abstract base class for dependency file parsers."""
    
    def __init__(self, file_path: Path) -> None:
        """Initialize parser.
        
        Args:
            file_path: Path to dependency file
        """
        self.file_path = file_path
        
        if not self.file_path.exists():
            raise FileNotFoundError(f"Dependency file not found: {file_path}")
    
    @abstractmethod
    def parse(self) -> list[Dependency]:
        """Parse dependency file and extract dependencies.
        
        Returns:
            List of dependencies
        """
        pass
    
    def get_dependency_tree(self) -> dict[str, list[str]]:
        """Get dependency tree including transitive dependencies.
        
        Returns:
            Dictionary mapping package names to their dependencies
        """
        # Default implementation returns empty tree
        return {}
    
    def can_parse(self) -> bool:
        """Check if this parser can handle the file.
        
        Returns:
            True if parser can handle file
        """
        return True
    
    @staticmethod
    def detect_parser(file_path: Path) -> type["DependencyParser"] | None:
        """Detect appropriate parser for a file.
        
        Args:
            file_path: Path to dependency file
            
        Returns:
            Parser class or None if no suitable parser found
        """
        from upgrade_analyzer.parsers.pipfile import PipfileParser
        from upgrade_analyzer.parsers.pyproject import PyprojectParser
        from upgrade_analyzer.parsers.requirements import RequirementsParser
        from upgrade_analyzer.parsers.lockfiles import (
            PoetryLockParser,
            PipfileLockParser,
            CondaEnvironmentParser,
            SetupPyParser,
        )
        
        filename = file_path.name.lower()
        
        # Check for requirements files
        if filename == "requirements.txt" or filename.endswith("-requirements.txt"):
            return RequirementsParser
        
        # Check for pyproject.toml
        elif filename == "pyproject.toml":
            return PyprojectParser
        
        # Check for Pipfile
        elif filename == "pipfile":
            return PipfileParser
        
        # Check for poetry.lock
        elif filename == "poetry.lock":
            return PoetryLockParser
        
        # Check for Pipfile.lock
        elif filename == "pipfile.lock":
            return PipfileLockParser
        
        # Check for conda environment files
        elif filename in {"environment.yml", "environment.yaml"}:
            return CondaEnvironmentParser
        
        # Check for setup.py
        elif filename == "setup.py":
            return SetupPyParser
        
        # Check for requirements-*.txt pattern
        elif filename.startswith("requirements") and filename.endswith(".txt"):
            return RequirementsParser
        
        logger.warning(f"No parser found for file: {filename}")
        return None
    
    @staticmethod
    def auto_detect_in_directory(directory: Path) -> list[Path]:
        """Auto-detect dependency files in a directory.
        
        Args:
            directory: Directory to search
            
        Returns:
            List of detected dependency file paths
        """
        files = []
        
        # Priority order for detection
        priority_files = [
            "pyproject.toml",
            "requirements.txt",
            "Pipfile",
            "poetry.lock",
            "Pipfile.lock",
            "setup.py",
            "environment.yml",
        ]
        
        for filename in priority_files:
            file_path = directory / filename
            if file_path.exists():
                files.append(file_path)
        
        # Also check for requirements-*.txt files
        for path in directory.glob("requirements*.txt"):
            if path not in files:
                files.append(path)
        
        return files
