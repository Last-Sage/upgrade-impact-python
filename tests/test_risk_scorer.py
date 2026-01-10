"""Test risk scoring."""

import pytest

from upgrade_analyzer.intelligence.risk_scorer import RiskScorer
from upgrade_analyzer.models import (
    APIChange,
    ChangelogEntry,
    ChangeType,
    Dependency,
    UsageNode,
)
from pathlib import Path


def test_semver_risk_major_version():
    """Test SemVer risk calculation for major version change."""
    scorer = RiskScorer()
    
    dep = Dependency(
        name="requests",
        current_version="2.28.0",
        target_version="3.0.0",
    )
    
    score = scorer._calculate_semver_risk(dep)
    
    # Major version change should have high score
    assert score >= 70


def test_semver_risk_patch_version():
    """Test SemVer risk calculation for patch version change."""
    scorer = RiskScorer()
    
    dep = Dependency(
        name="requests",
        current_version="2.28.0",
        target_version="2.28.1",
    )
    
    score = scorer._calculate_semver_risk(dep)
    
    # Patch version change should have low score
    assert score <= 20


def test_usage_impact_with_breaking_change():
    """Test usage impact with breaking API change."""
    scorer = RiskScorer()
    
    usage_nodes = [
        UsageNode(
            package_name="requests",
            symbol_path="requests.get",
            file_path=Path("test.py"),
            line_numbers=[10],
            call_count=5,
        )
    ]
    
    api_changes = [
        APIChange(
            symbol_name="requests.get",
            change_type=ChangeType.REMOVED,
            description="Function removed",
        )
    ]
    
    score = scorer._calculate_usage_impact(usage_nodes, api_changes)
    
    # Removed function should have max score
    assert score == 100.0


def test_usage_impact_no_changes():
    """Test usage impact with no API changes."""
    scorer = RiskScorer()
    
    usage_nodes = [
        UsageNode(
            package_name="requests",
            symbol_path="requests.get",
            file_path=Path("test.py"),
            line_numbers=[10],
        )
    ]
    
    score = scorer._calculate_usage_impact(usage_nodes, [])
    
    # No changes = zero score
    assert score == 0.0
