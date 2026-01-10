"""Upgrade recommendation advisor."""

from upgrade_analyzer.models import (
    Dependency,
    RiskScore,
    Severity,
    UpgradeRecommendation,
    UsageNode,
)
from upgrade_analyzer.resolver import DependencyResolver


class UpgradeAdvisor:
    """Provides upgrade recommendations and advice."""
    
    def __init__(self, offline: bool = False) -> None:
        """Initialize advisor.
        
        Args:
            offline: If True, only use cached data
        """
        self.resolver = DependencyResolver(offline=offline)
    
    def suggest_upgrade_path(
        self,
        dependency: Dependency,
        risk_score: RiskScore
    ) -> UpgradeRecommendation:
        """Suggest best upgrade path for a dependency.
        
        Args:
            dependency: Dependency to upgrade
            risk_score: Calculated risk score
            
        Returns:
            Upgrade recommendation
        """
        # Determine upgrade strategy based on risk
        if risk_score.severity in {Severity.CRITICAL, Severity.HIGH}:
            # High risk - suggest incremental path
            path = self.resolver.suggest_upgrade_path(
                dependency,
                dependency.target_version
            )
            
            rationale = (
                f"High risk detected. Recommend incremental upgrade "
                f"to minimize compatibility issues."
            )
            
            effort = "High"
        
        elif risk_score.severity == Severity.MEDIUM:
            # Medium risk - suggest shorter path with milestones
            path = self.resolver.suggest_upgrade_path(
                dependency,
                dependency.target_version
            )
            
            # Keep only major milestones
            if len(path) > 3:
                path = [path[0], path[len(path)//2], path[-1]]
            
            rationale = (
                f"Medium risk. Recommend testing at milestone versions "
                f"to catch issues early."
            )
            
            effort = "Medium"
        
        else:
            # Low risk - direct upgrade
            path = [dependency.target_version] if dependency.target_version else []
            
            rationale = (
                f"Low risk detected. Direct upgrade recommended."
            )
            
            effort = "Low"
        
        return UpgradeRecommendation(
            dependency=dependency,
            recommended_path=path,
            rationale=rationale,
            estimated_effort=effort,
        )
    
    def generate_migration_tips(
        self,
        dependency: Dependency,
        risk_score: RiskScore
    ) -> list[str]:
        """Generate migration tips based on risk factors.
        
        Args:
            dependency: Dependency being upgraded
            risk_score: Risk score
            
        Returns:
            List of migration tips
        """
        tips: list[str] = []
        
        # Analyze risk factors
        for factor in risk_score.factors:
            if factor.name == "Usage Impact" and factor.score > 60:
                tips.append(
                    "⚠️  High usage impact detected. Review all import statements "
                    "and function calls to this package."
                )
            
            if factor.name == "SemVer Distance" and factor.score > 70:
                tips.append(
                    "📚 Major version change. Carefully review the migration guide "
                    "and changelog for breaking changes."
                )
            
            if factor.name == "Changelog Severity" and factor.score > 50:
                tips.append(
                    "📝 Significant changes documented in changelog. "
                    "Read release notes before upgrading."
                )
        
        # General tips based on severity
        if risk_score.severity == Severity.CRITICAL:
            tips.append(
                "🚨 CRITICAL: Create a dedicated branch and comprehensive test suite "
                "before attempting this upgrade."
            )
        
        elif risk_score.severity == Severity.HIGH:
            tips.append(
                "⚡ Test thoroughly in a staging environment before production."
            )
        
        # Always recommend these
        tips.extend([
            "✅ Run your full test suite after upgrading",
            "📦 Consider using a virtual environment for testing",
        ])
        
        return tips
    
    def detect_deprecation_warnings(
        self,
        usage_nodes: list[UsageNode],
        api_changes: list
    ) -> list[str]:
        """Detect if used symbols are deprecated.
        
        Args:
            usage_nodes: Symbols used in code
            api_changes: API changes detected
            
        Returns:
            List of deprecation warnings
        """
        warnings: list[str] = []
        
        # Build set of used symbols
        used_symbols = {node.symbol_path for node in usage_nodes}
        
        # Check for deprecations
        for change in api_changes:
            if change.change_type.value == "deprecated":
                if change.symbol_name in used_symbols:
                    warnings.append(
                        f"⚠️  {change.symbol_name} is deprecated. {change.description}"
                    )
        
        return warnings
    
    def should_block_ci(self, risk_score: RiskScore) -> bool:
        """Determine if CI should fail based on risk.
        
        Args:
            risk_score: Risk score
            
        Returns:
            True if CI should fail
        """
        from upgrade_analyzer.config import get_config
        
        config = get_config()
        
        fail_on_critical = config.get("ci.fail_on_critical", True)
        fail_on_high = config.get("ci.fail_on_high_risk", True)
        
        if risk_score.severity == Severity.CRITICAL and fail_on_critical:
            return True
        
        if risk_score.severity == Severity.HIGH and fail_on_high:
            return True
        
        return False
