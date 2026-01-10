"""Dependency file parsers."""

from upgrade_analyzer.parsers.base import DependencyParser
from upgrade_analyzer.parsers.pipfile import PipfileParser
from upgrade_analyzer.parsers.pyproject import PyprojectParser
from upgrade_analyzer.parsers.requirements import RequirementsParser
from upgrade_analyzer.parsers.lockfiles import (
    PoetryLockParser,
    PipfileLockParser,
    CondaEnvironmentParser,
    SetupPyParser,
)

__all__ = [
    "DependencyParser",
    "PipfileParser",
    "PyprojectParser",
    "RequirementsParser",
    "PoetryLockParser",
    "PipfileLockParser",
    "CondaEnvironmentParser",
    "SetupPyParser",
]
