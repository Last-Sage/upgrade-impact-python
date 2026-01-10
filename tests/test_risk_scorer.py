"""Comprehensive tests for risk scoring algorithm validation."""

import pytest
from pathlib import Path

from upgrade_analyzer.intelligence.risk_scorer import RiskScorer
from upgrade_analyzer.models import (
    APIChange,
    ChangelogEntry,
    ChangeType,
    Dependency,
    Severity,
    UsageNode,
)


class TestSemVerRiskScoring:
    """Validate SemVer risk scoring produces correct, predictable scores."""
    
    def test_major_version_jump_gives_high_score(self):
        """Major version bump (1->2) should score 80+."""
        scorer = RiskScorer()
        
        dep = Dependency(
            name="requests",
            current_version="2.28.0",
            target_version="3.0.0",
        )
        
        score = scorer._calculate_semver_risk(dep)
        
        # Major version = 80 base (see line 117)
        assert score == 80.0, f"Expected 80.0 for 1 major jump, got {score}"
    
    def test_two_major_versions_gives_100(self):
        """Two major version jumps should max out at 100."""
        scorer = RiskScorer()
        
        dep = Dependency(
            name="requests",
            current_version="1.0.0",
            target_version="3.0.0",
        )
        
        score = scorer._calculate_semver_risk(dep)
        
        # 2 major = 80 + (2-1)*20 = 100
        assert score == 100.0, f"Expected 100.0 for 2 major jumps, got {score}"
    
    def test_minor_version_jump_gives_medium_score(self):
        """Minor version bump (1.0->1.1) should score 40-60."""
        scorer = RiskScorer()
        
        dep = Dependency(
            name="requests",
            current_version="2.28.0",
            target_version="2.29.0",
        )
        
        score = scorer._calculate_semver_risk(dep)
        
        # 1 minor = 40 + 1*5 = 45
        assert score == 45.0, f"Expected 45.0 for 1 minor jump, got {score}"
    
    def test_three_minor_versions_caps_at_60(self):
        """Multiple minor jumps should cap at 60."""
        scorer = RiskScorer()
        
        dep = Dependency(
            name="requests",
            current_version="2.25.0",
            target_version="2.30.0",
        )
        
        score = scorer._calculate_semver_risk(dep)
        
        # 5 minor = min(40 + 5*5, 60) = min(65, 60) = 60
        assert score == 60.0, f"Expected 60.0 (capped), got {score}"
    
    def test_patch_version_gives_low_score(self):
        """Patch version bump should score 10-20."""
        scorer = RiskScorer()
        
        dep = Dependency(
            name="requests",
            current_version="2.28.0",
            target_version="2.28.1",
        )
        
        score = scorer._calculate_semver_risk(dep)
        
        # 1 patch = 10 + 1*2 = 12
        assert score == 12.0, f"Expected 12.0 for 1 patch, got {score}"
    
    def test_five_patches_caps_at_20(self):
        """Multiple patches should cap at 20."""
        scorer = RiskScorer()
        
        dep = Dependency(
            name="requests",
            current_version="2.28.0",
            target_version="2.28.10",
        )
        
        score = scorer._calculate_semver_risk(dep)
        
        # 10 patches = min(10 + 10*2, 20) = 20
        assert score == 20.0, f"Expected 20.0 (capped), got {score}"
    
    def test_no_target_version_gives_zero(self):
        """Missing target version should return 0."""
        scorer = RiskScorer()
        
        dep = Dependency(
            name="requests",
            current_version="2.28.0",
            target_version=None,
        )
        
        score = scorer._calculate_semver_risk(dep)
        assert score == 0.0


class TestUsageImpactScoring:
    """Validate usage impact scoring is deterministic."""
    
    def test_removed_symbol_in_use_gives_100(self):
        """Removed symbol that IS used = critical (100)."""
        scorer = RiskScorer()
        
        usage_nodes = [
            UsageNode(
                package_name="requests",
                symbol_path="requests.get",
                file_path=Path("app.py"),
                line_numbers=[10, 20, 30],
                call_count=3,
            )
        ]
        
        api_changes = [
            APIChange(
                symbol_name="requests.get",  # Matches usage
                change_type=ChangeType.REMOVED,
                description="Function removed",
            )
        ]
        
        score = scorer._calculate_usage_impact(usage_nodes, api_changes)
        assert score == 100.0, f"Removed used symbol should be 100, got {score}"
    
    def test_removed_symbol_not_in_use_gives_10(self):
        """Removed symbol NOT used = low risk (10)."""
        scorer = RiskScorer()
        
        usage_nodes = [
            UsageNode(
                package_name="requests",
                symbol_path="requests.get",  # We use 'get'
                file_path=Path("app.py"),
                line_numbers=[10],
            )
        ]
        
        api_changes = [
            APIChange(
                symbol_name="requests.post",  # 'post' is removed, not 'get'
                change_type=ChangeType.REMOVED,
                description="Function removed",
            )
        ]
        
        score = scorer._calculate_usage_impact(usage_nodes, api_changes)
        # Changes exist but don't affect used symbols = 10
        assert score == 10.0, f"Removed unused symbol should be 10, got {score}"
    
    def test_modified_symbol_in_use_gives_high_score(self):
        """Modified signature that IS used = high (70+)."""
        scorer = RiskScorer()
        
        usage_nodes = [
            UsageNode(
                package_name="requests",
                symbol_path="requests.get",
                file_path=Path("app.py"),
                line_numbers=[10],
            )
        ]
        
        api_changes = [
            APIChange(
                symbol_name="requests.get",
                change_type=ChangeType.MODIFIED,
                old_signature="(url, **kwargs)",
                new_signature="(url, *, timeout=30, **kwargs)",
                description="Added required timeout",
            )
        ]
        
        score = scorer._calculate_usage_impact(usage_nodes, api_changes)
        # 1 moderate = min(70 + 1*10, 90) = 80
        assert score == 80.0, f"Modified used symbol should be 80, got {score}"
    
    def test_deprecated_symbol_in_use_gives_medium_score(self):
        """Deprecated symbol that IS used = medium (40-60)."""
        scorer = RiskScorer()
        
        usage_nodes = [
            UsageNode(
                package_name="requests",
                symbol_path="requests.get",
                file_path=Path("app.py"),
                line_numbers=[10],
            )
        ]
        
        api_changes = [
            APIChange(
                symbol_name="requests.get",
                change_type=ChangeType.DEPRECATED,
                description="Use requests.request instead",
            )
        ]
        
        score = scorer._calculate_usage_impact(usage_nodes, api_changes)
        # 1 deprecation = min(40 + 1*10, 60) = 50
        assert score == 50.0, f"Deprecated used symbol should be 50, got {score}"
    
    def test_no_api_changes_gives_zero(self):
        """No API changes = 0 score."""
        scorer = RiskScorer()
        
        usage_nodes = [
            UsageNode(
                package_name="requests",
                symbol_path="requests.get",
                file_path=Path("app.py"),
                line_numbers=[10],
            )
        ]
        
        score = scorer._calculate_usage_impact(usage_nodes, [])
        assert score == 0.0


class TestOverallRiskCalculation:
    """Test the combined weighted score calculation."""
    
    def test_weights_sum_correctly(self):
        """Verify weighted calculation: 30% semver + 50% usage + 20% changelog."""
        scorer = RiskScorer()
        
        # Create a major version jump with removed symbol
        dep = Dependency(
            name="requests",
            current_version="2.0.0",
            target_version="3.0.0",
        )
        
        usage_nodes = [
            UsageNode(
                package_name="requests",
                symbol_path="requests.get",
                file_path=Path("app.py"),
                line_numbers=[10],
            )
        ]
        
        api_changes = [
            APIChange(
                symbol_name="requests.get",
                change_type=ChangeType.REMOVED,
                description="Removed",
            )
        ]
        
        # No changelog
        result = scorer.calculate_risk(dep, usage_nodes, api_changes, [])
        
        # Expected: 0.3 * 80 (semver) + 0.5 * 100 (usage) + 0.2 * 0 (changelog)
        # = 24 + 50 + 0 = 74
        expected = 0.3 * 80 + 0.5 * 100 + 0.2 * 0
        
        assert abs(result.total_score - expected) < 1.0, f"Expected ~{expected}, got {result.total_score}"
    
    def test_severity_thresholds(self):
        """Verify severity mapping: 80+=Critical, 60+=High, 30+=Medium, <30=Low."""
        scorer = RiskScorer()
        
        # Test critical (90)
        dep = Dependency(name="pkg", current_version="1.0.0", target_version="3.0.0")
        usage = [UsageNode(package_name="pkg", symbol_path="pkg.fn", file_path=Path("a.py"), line_numbers=[1])]
        changes = [APIChange(symbol_name="pkg.fn", change_type=ChangeType.REMOVED, description="x")]
        
        result = scorer.calculate_risk(dep, usage, changes, [])
        
        # 0.3*100 + 0.5*100 + 0.2*0 = 80
        assert result.severity == Severity.CRITICAL, f"Score {result.total_score} should be CRITICAL"
    
    def test_low_risk_scenario(self):
        """Patch update with no breaking changes = low risk."""
        scorer = RiskScorer()
        
        dep = Dependency(
            name="requests",
            current_version="2.28.0",
            target_version="2.28.1",
        )
        
        usage_nodes = [
            UsageNode(
                package_name="requests",
                symbol_path="requests.get",
                file_path=Path("app.py"),
                line_numbers=[10],
            )
        ]
        
        # No API changes
        result = scorer.calculate_risk(dep, usage_nodes, [], [])
        
        # 0.3 * 12 (patch) + 0.5 * 0 (no changes) + 0.2 * 0 = 3.6
        assert result.severity == Severity.LOW, f"Patch with no changes should be LOW, got {result.severity}"
        assert result.total_score < 30, f"Score should be <30, got {result.total_score}"


class TestScoringDeterminism:
    """Verify scoring is deterministic - same inputs always produce same outputs."""
    
    def test_same_input_produces_same_output(self):
        """Running the same analysis multiple times should give identical scores."""
        scorer = RiskScorer()
        
        dep = Dependency(
            name="flask",
            current_version="2.0.0",
            target_version="2.3.0",
        )
        
        usage_nodes = [
            UsageNode(
                package_name="flask",
                symbol_path="flask.Flask.route",
                file_path=Path("app.py"),
                line_numbers=[10, 20],
            )
        ]
        
        api_changes = [
            APIChange(
                symbol_name="flask.Flask.route",
                change_type=ChangeType.MODIFIED,
                description="Changed signature",
            )
        ]
        
        # Run 5 times
        scores = [
            scorer.calculate_risk(dep, usage_nodes, api_changes, []).total_score
            for _ in range(5)
        ]
        
        # All scores must be identical
        assert len(set(scores)) == 1, f"Scores should be deterministic, got: {scores}"
