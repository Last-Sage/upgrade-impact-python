"""Tests for lock file parsers."""

import json
from pathlib import Path

import pytest

from upgrade_analyzer.parsers.lockfiles import (
    PoetryLockParser,
    PipfileLockParser,
    SetupPyParser,
)


class TestPoetryLockParser:
    """Tests for poetry.lock parser."""
    
    def test_parse_poetry_lock(self, tmp_path: Path) -> None:
        """Test parsing poetry.lock file."""
        content = '''
[[package]]
name = "requests"
version = "2.31.0"
category = "main"

[[package]]
name = "pytest"
version = "8.0.0"
category = "dev"
'''
        file = tmp_path / "poetry.lock"
        file.write_text(content)
        
        parser = PoetryLockParser(file)
        deps = parser.parse()
        
        assert len(deps) == 2
        assert any(d.name == "requests" and d.current_version == "2.31.0" for d in deps)
        assert any(d.name == "pytest" and d.current_version == "8.0.0" for d in deps)
    
    def test_can_parse(self, tmp_path: Path) -> None:
        """Test can_parse method."""
        poetry_lock = tmp_path / "poetry.lock"
        poetry_lock.write_text("[[package]]")
        
        other_file = tmp_path / "other.txt"
        other_file.write_text("content")
        
        assert PoetryLockParser(poetry_lock).can_parse() is True
        assert PoetryLockParser(other_file).can_parse() is False


class TestPipfileLockParser:
    """Tests for Pipfile.lock parser."""
    
    def test_parse_pipfile_lock(self, tmp_path: Path) -> None:
        """Test parsing Pipfile.lock file."""
        content = {
            "default": {
                "requests": {"version": "==2.31.0"},
                "flask": {"version": "==3.0.0"},
            },
            "develop": {
                "pytest": {"version": "==8.0.0"},
            },
        }
        
        file = tmp_path / "Pipfile.lock"
        file.write_text(json.dumps(content))
        
        parser = PipfileLockParser(file)
        deps = parser.parse()
        
        assert len(deps) == 3
        assert any(d.name == "requests" and d.current_version == "2.31.0" for d in deps)
        assert any(d.name == "flask" and d.current_version == "3.0.0" for d in deps)
        assert any(d.name == "pytest" and d.current_version == "8.0.0" for d in deps)
    
    def test_extract_version_without_prefix(self, tmp_path: Path) -> None:
        """Test version extraction without == prefix."""
        content = {
            "default": {
                "package": {"version": "1.0.0"},
            },
            "develop": {},
        }
        
        file = tmp_path / "Pipfile.lock"
        file.write_text(json.dumps(content))
        
        parser = PipfileLockParser(file)
        deps = parser.parse()
        
        assert deps[0].current_version == "1.0.0"


class TestSetupPyParser:
    """Tests for setup.py parser."""
    
    def test_parse_setup_py(self, tmp_path: Path) -> None:
        """Test parsing setup.py file."""
        content = '''
from setuptools import setup

setup(
    name="myproject",
    install_requires=[
        "requests>=2.28.0",
        "flask==3.0.0",
        "numpy",
    ],
)
'''
        file = tmp_path / "setup.py"
        file.write_text(content)
        
        parser = SetupPyParser(file)
        deps = parser.parse()
        
        assert len(deps) >= 2
        assert any(d.name == "requests" for d in deps)
        assert any(d.name == "flask" for d in deps)
    
    def test_parse_empty_setup_py(self, tmp_path: Path) -> None:
        """Test parsing setup.py without install_requires."""
        content = '''
from setuptools import setup
setup(name="myproject")
'''
        file = tmp_path / "setup.py"
        file.write_text(content)
        
        parser = SetupPyParser(file)
        deps = parser.parse()
        
        assert deps == []
