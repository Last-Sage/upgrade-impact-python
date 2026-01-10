"""Test parsers."""

import pytest
from pathlib import Path

from upgrade_analyzer.parsers.requirements import RequirementsParser
from upgrade_analyzer.parsers.pyproject import PyprojectParser


def test_requirements_parser(tmp_path):
    """Test requirements.txt parser."""
    req_file = tmp_path / "requirements.txt"
    req_file.write_text("""
# Comment
requests==2.28.0
flask>=2.0.0
pytest~=7.0
numpy
""")
    
    parser = RequirementsParser(req_file)
    deps = parser.parse()
    
    assert len(deps) >= 2
    assert any(d.name == "requests" and d.current_version == "2.28.0" for d in deps)
    assert any(d.name == "flask" for d in deps)


def test_pyproject_parser(tmp_path):
    """Test pyproject.toml parser."""
    pyproject_file = tmp_path / "pyproject.toml"
    pyproject_file.write_text("""
[project]
dependencies = [
    "requests==2.28.0",
    "flask>=2.0.0",
]
""")
    
    parser = PyprojectParser(pyproject_file)
    deps = parser.parse()
    
    assert len(deps) == 2
    assert any(d.name == "requests" and d.current_version == "2.28.0" for d in deps)


def test_parser_detection(tmp_path):
    """Test automatic parser detection."""
    from upgrade_analyzer.parsers.base import DependencyParser
    
    req_file = tmp_path / "requirements.txt"
    parser_class = DependencyParser.detect_parser(req_file)
    
    assert parser_class == RequirementsParser
