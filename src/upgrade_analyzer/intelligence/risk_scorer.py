"""Risk scoring algorithm."""

from upgrade_analyzer.config import get_config
from upgrade_analyzer.intelligence.changelog_nlp import ChangelogAnalyzer
from upgrade_analyzer.models import (
    APIChange,
    ChangelogEntry,
    ChangeType,
    Dependency,
    RiskFactor,
    RiskScore,
    Severity,
    UsageNode,
)
from upgrade_analyzer.resolver import DependencyResolver


class RiskScorer:
    """Calculates risk scores for dependency upgrades."""
    
    def __init__(self) -> None:
        """Initialize risk scorer."""
        self.config = get_config()
        self.changelog_analyzer = ChangelogAnalyzer()
        self.resolver = DependencyResolver()
    
    def calculate_risk(
        self,
        dependency: Dependency,
        usage_nodes: list[UsageNode],
        api_changes: list[APIChange],
        changelog_entries: list[ChangelogEntry]
    ) -> RiskScore:
        """Calculate overall risk score for an upgrade.
        
        Args:
            dependency: Dependency being upgraded
            usage_nodes: How the package is used in code
            api_changes: API changes detected
            changelog_entries: Changelog entries
            
        Returns:
            RiskScore object
        """
        factors: list[RiskFactor] = []
        
        # 1. SemVer-based risk (30% weight)
        semver_score = self._calculate_semver_risk(dependency)
        factors.append(
            RiskFactor(
                name="SemVer Distance",
                score=semver_score,
                weight=self.config.semver_weight,
                description=f"Version jump from {dependency.current_version} to {dependency.target_version}",
            )
        )
        
        # 2. Usage impact (50% weight)
        usage_score = self._calculate_usage_impact(usage_nodes, api_changes)
        factors.append(
            RiskFactor(
                name="Usage Impact",
                score=usage_score,
                weight=self.config.usage_weight,
                description=f"{len(api_changes)} API changes affecting {len(usage_nodes)} usage points",
            )
        )
        
        # 3. Changelog severity (20% weight)
        changelog_score = self._calculate_changelog_severity(changelog_entries)
        factors.append(
            RiskFactor(
                name="Changelog Severity",
                score=changelog_score,
                weight=self.config.changelog_weight,
                description=f"Based on {len(changelog_entries)} changelog entries",
            )
        )
        
        # Calculate weighted total
        total_score = sum(f.score * f.weight for f in factors)
        
        # Determine severity
        severity = RiskScore.from_score(total_score)
        
        return RiskScore(
            total_score=total_score,
            severity=severity,
            factors=factors,
        )
    
    def _calculate_semver_risk(self, dependency: Dependency) -> float:
        """Calculate risk based on semantic version distance.
        
        Args:
            dependency: Dependency with current and target versions
            
        Returns:
            Risk score (0-100)
        """
        if not dependency.target_version:
            return 0.0
        
        distance = self.resolver.calculate_version_distance(
            dependency.current_version,
            dependency.target_version
        )
        
        # Calculate score based on version component changes
        major_delta = distance["major"]
        minor_delta = distance["minor"]
        patch_delta = distance["patch"]
        
        # Major version change = high risk
        if major_delta > 0:
            # Scale: 1 major = 80, 2+ majors = 100
            return min(80 + (major_delta - 1) * 20, 100)
        
        # Minor version change = medium risk
        elif minor_delta > 0:
            # Scale: 1-2 minors = 40-50, 3+ = 60
            return min(40 + minor_delta * 5, 60)
        
        # Patch only = low risk
        else:
            # Scale: 1-5 patches = 10-20
            return min(10 + patch_delta * 2, 20)
    
    def _calculate_usage_impact(
        self,
        usage_nodes: list[UsageNode],
        api_changes: list[APIChange]
    ) -> float:
        """Calculate risk based on actual code usage.
        
        Args:
            usage_nodes: Usage points in code
            api_changes: API changes detected
            
        Returns:
            Risk score (0-100)
        """
        if not api_changes:
            # No API changes affecting used symbols
            return 0.0
        
        # Build set of used symbols
        used_symbols = {node.symbol_path for node in usage_nodes}
        
        # Analyze each API change
        breaking_changes = 0
        moderate_changes = 0
        deprecations = 0
        
        for change in api_changes:
            if change.symbol_name in used_symbols:
                if change.change_type == ChangeType.REMOVED:
                    breaking_changes += 1
                elif change.change_type == ChangeType.MODIFIED:
                    moderate_changes += 1
                elif change.change_type == ChangeType.DEPRECATED:
                    deprecations += 1
        
        # Calculate score
        if breaking_changes > 0:
            # Any removed symbol = critical
            return 100.0
        
        elif moderate_changes > 0:
            # Modified signatures = high risk
            return min(70 + moderate_changes * 10, 90)
        
        elif deprecations > 0:
            # Deprecations = medium risk
            return min(40 + deprecations * 10, 60)
        
        else:
            # Changes exist but don't affect used symbols
            return 10.0
    
    def _calculate_changelog_severity(
        self,
        changelog_entries: list[ChangelogEntry]
    ) -> float:
        """Calculate risk based on changelog content.
        
        Args:
            changelog_entries: Changelog entries to analyze
            
        Returns:
            Risk score (0-100)
        """
        if not changelog_entries:
            return 0.0
        
        # Analyze all entries
        analyzed_entries = self.changelog_analyzer.analyze_multiple_entries(
            changelog_entries
        )
        
        # Calculate average severity score
        scores = [
            self.changelog_analyzer.calculate_changelog_severity_score(entry)
            for entry in analyzed_entries
        ]
        
        if scores:
            return sum(scores) / len(scores)
        
        return 0.0
