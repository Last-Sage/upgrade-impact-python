"""Core analyzer orchestrator with security integration."""

import logging
from pathlib import Path

from upgrade_analyzer.config import get_config, load_ignore_file
from upgrade_analyzer.intelligence.api_differ import APIDiffer
from upgrade_analyzer.intelligence.changelog_fetcher import ChangelogFetcher
from upgrade_analyzer.intelligence.risk_scorer import RiskScorer
from upgrade_analyzer.models import (
    BreakingChange,
    Dependency,
    UpgradeReport,
)
from upgrade_analyzer.parsers.base import DependencyParser
from upgrade_analyzer.recommendations.advisor import UpgradeAdvisor
from upgrade_analyzer.resolver import DependencyResolver
from upgrade_analyzer.scanner.usage_mapper import UsageMapper

logger = logging.getLogger(__name__)


class UpgradeAnalyzer:
    """Main analyzer orchestrator."""
    
    def __init__(
        self,
        project_root: Path,
        dependency_file: Path,
        offline: bool = False,
        include_transitive: bool = False,
        include_security: bool = False,
    ) -> None:
        """Initialize analyzer.
        
        Args:
            project_root: Root directory of project
            dependency_file: Path to dependency file
            offline: If True, use only cached data
            include_transitive: If True, analyze transitive dependencies
            include_security: If True, include security scanning
        """
        self.project_root = Path(project_root)
        self.dependency_file = Path(dependency_file)
        self.offline = offline
        self.include_transitive = include_transitive
        self.include_security = include_security
        
        # Initialize components
        self.config = get_config()
        self.resolver = DependencyResolver(offline=offline)
        self.usage_mapper = UsageMapper(self.project_root)
        self.changelog_fetcher = ChangelogFetcher(offline=offline)
        self.api_differ = APIDiffer(offline=offline)
        self.risk_scorer = RiskScorer()
        self.advisor = UpgradeAdvisor(offline=offline)
        
        # Security scanner (lazy loaded)
        self._security_scanner = None
        
        # Load ignore file
        self.ignored_packages = load_ignore_file(self.project_root)
    
    def analyze(self) -> list[UpgradeReport]:
        """Run complete analysis.
        
        Returns:
            List of upgrade reports
        """
        logger.info(f"Starting analysis of {self.dependency_file}")
        
        # 1. Parse dependencies
        dependencies = self._parse_dependencies()
        logger.info(f"Parsed {len(dependencies)} direct dependencies")
        
        # 2. Add transitive dependencies if requested
        if self.include_transitive:
            transitive = self._get_transitive_dependencies(dependencies)
            logger.info(f"Found {len(transitive)} transitive dependencies")
            dependencies.extend(transitive)
        
        # 3. Filter ignored packages
        original_count = len(dependencies)
        dependencies = [
            dep for dep in dependencies
            if dep.name.lower() not in {p.lower() for p in self.ignored_packages}
        ]
        
        if original_count != len(dependencies):
            logger.info(f"Filtered {original_count - len(dependencies)} ignored packages")
        
        # 4. Determine upgrade targets
        dependencies = self._set_upgrade_targets(dependencies)
        
        # 5. Analyze each dependency
        reports: list[UpgradeReport] = []
        
        for dep in dependencies:
            if not dep.target_version:
                logger.debug(f"Skipping {dep.name}: no target version")
                continue
            
            if dep.current_version == dep.target_version:
                logger.debug(f"Skipping {dep.name}: already at target version")
                continue
            
            try:
                report = self._analyze_dependency(dep)
                reports.append(report)
            except Exception as e:
                logger.error(f"Error analyzing {dep.name}: {e}")
                continue
        
        logger.info(f"Completed analysis of {len(reports)} dependencies")
        return reports
    
    def _parse_dependencies(self) -> list[Dependency]:
        """Parse dependency file.
        
        Returns:
            List of dependencies
        """
        # Detect parser
        parser_class = DependencyParser.detect_parser(self.dependency_file)
        
        if not parser_class:
            raise ValueError(f"Unsupported dependency file: {self.dependency_file}")
        
        # Parse
        parser = parser_class(self.dependency_file)
        return parser.parse()
    
    def _get_transitive_dependencies(self, direct_deps: list[Dependency]) -> list[Dependency]:
        """Get transitive dependencies.
        
        Args:
            direct_deps: Direct dependencies
            
        Returns:
            List of transitive dependencies
        """
        transitive: list[Dependency] = []
        seen = {d.name.lower() for d in direct_deps}
        
        for dep in direct_deps:
            trans_deps = self.resolver.get_transitive_dependencies(
                dep.name,
                dep.current_version,
                depth=2,  # Limit depth
            )
            
            for trans_dep in trans_deps:
                if trans_dep.name.lower() not in seen:
                    seen.add(trans_dep.name.lower())
                    transitive.append(trans_dep)
        
        return transitive
    
    def _set_upgrade_targets(self, dependencies: list[Dependency]) -> list[Dependency]:
        """Set upgrade target versions for dependencies.
        
        Args:
            dependencies: List of dependencies
            
        Returns:
            Dependencies with target versions set
        """
        for dep in dependencies:
            if not dep.target_version:
                # Get latest version
                latest = self.resolver.get_latest_version(dep.name)
                dep.target_version = latest
        
        return dependencies
    
    def _analyze_dependency(self, dependency: Dependency) -> UpgradeReport:
        """Analyze a single dependency upgrade.
        
        Args:
            dependency: Dependency to analyze
            
        Returns:
            Upgrade report
        """
        logger.debug(f"Analyzing {dependency.name}: {dependency.current_version} -> {dependency.target_version}")
        
        # 1. Map usage in codebase
        usage_nodes = self.usage_mapper.map_package_usage(dependency.name)
        usage_summary = self.usage_mapper.get_usage_summary(dependency.name)
        
        logger.debug(f"Found {len(usage_nodes)} usage nodes for {dependency.name}")
        
        # 2. Fetch changelog
        changelog_entries = self.changelog_fetcher.fetch_changelog(
            dependency.name,
            from_version=dependency.current_version,
            to_version=dependency.target_version,
        )
        
        logger.debug(f"Fetched {len(changelog_entries)} changelog entries")
        
        # 3. Detect API changes
        api_changes = self.api_differ.diff_versions(
            dependency.name,
            dependency.current_version,
            dependency.target_version or "",
            usage_nodes,
        )
        
        logger.debug(f"Detected {len(api_changes)} API changes")
        
        # 4. Calculate risk score
        risk_score = self.risk_scorer.calculate_risk(
            dependency,
            usage_nodes,
            api_changes,
            changelog_entries,
        )
        
        # 5. Generate recommendation
        recommendation = self.advisor.suggest_upgrade_path(dependency, risk_score)
        
        # Add deprecation warnings
        deprecation_warnings = self.advisor.detect_deprecation_warnings(
            usage_nodes,
            api_changes,
        )
        recommendation.deprecation_warnings = deprecation_warnings
        
        # 6. Build breaking changes list
        breaking_changes = []
        
        for api_change in api_changes:
            if api_change.is_breaking:
                # Find affected usage
                affected = [
                    u for u in usage_nodes
                    if u.symbol_path == api_change.symbol_name
                ]
                
                breaking_changes.append(
                    BreakingChange(
                        dependency=dependency,
                        api_change=api_change,
                        affected_usage=affected,
                        recommendation=self._generate_fix_recommendation(api_change),
                    )
                )
        
        # 7. Create report
        return UpgradeReport(
            dependency=dependency,
            risk_score=risk_score,
            api_changes=api_changes,
            breaking_changes=breaking_changes,
            changelog_entries=changelog_entries,
            recommendation=recommendation,
            usage_summary=usage_summary,
        )
    
    @staticmethod
    def _generate_fix_recommendation(api_change) -> str:
        """Generate recommendation for fixing a breaking change.
        
        Args:
            api_change: API change
            
        Returns:
            Recommendation string
        """
        if api_change.change_type.value == "removed":
            return (
                f"Function '{api_change.symbol_name}' was removed. "
                f"Check documentation for alternative approaches."
            )
        
        elif api_change.change_type.value == "modified":
            return (
                f"Function '{api_change.symbol_name}' signature changed. "
                f"Review new signature: {api_change.new_signature}"
            )
        
        elif api_change.change_type.value == "deprecated":
            return (
                f"Function '{api_change.symbol_name}' is deprecated. "
                f"Consider migrating to the recommended alternative."
            )
        
        else:
            return "Review the changelog for migration instructions."
    
    def close(self) -> None:
        """Close all HTTP clients."""
        self.resolver.close()
        self.changelog_fetcher.close()
        self.api_differ.close()
        
        if self._security_scanner:
            self._security_scanner.close()
