"""Enterprise features: custom policies, monorepo support."""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import toml

from upgrade_analyzer.models import Dependency, Severity, UpgradeReport

logger = logging.getLogger(__name__)


@dataclass
class PolicyViolation:
    """A policy violation."""
    
    policy_name: str
    package: str
    message: str
    severity: Severity = Severity.HIGH
    auto_fix: str | None = None


@dataclass
class RiskPolicy:
    """Custom risk policy rule."""
    
    name: str
    description: str = ""
    
    # Matching criteria
    packages: list[str] = field(default_factory=list)  # Glob patterns
    package_regex: str | None = None
    
    # Risk thresholds
    max_semver_major: int | None = None  # Block major version jumps > N
    max_risk_score: float | None = None  # Block if risk score > N
    
    # Enforcement
    require_approval: bool = False
    block_upgrade: bool = False
    
    # Custom actions
    notify_channels: list[str] = field(default_factory=list)  # slack, teams, email
    require_ticket: bool = False  # Require Jira/Linear ticket


class PolicyEngine:
    """Evaluate custom risk policies."""
    
    def __init__(self, policies_file: Path | None = None) -> None:
        """Initialize policy engine.
        
        Args:
            policies_file: Path to policies TOML file
        """
        self.policies: list[RiskPolicy] = []
        
        if policies_file and policies_file.exists():
            self._load_policies(policies_file)
    
    def _load_policies(self, policies_file: Path) -> None:
        """Load policies from TOML file.
        
        Args:
            policies_file: Path to policies file
        """
        try:
            data = toml.load(policies_file)
            
            for policy_data in data.get("policies", []):
                policy = RiskPolicy(
                    name=policy_data.get("name", "Unnamed Policy"),
                    description=policy_data.get("description", ""),
                    packages=policy_data.get("packages", []),
                    package_regex=policy_data.get("package_regex"),
                    max_semver_major=policy_data.get("max_semver_major"),
                    max_risk_score=policy_data.get("max_risk_score"),
                    require_approval=policy_data.get("require_approval", False),
                    block_upgrade=policy_data.get("block_upgrade", False),
                    notify_channels=policy_data.get("notify_channels", []),
                    require_ticket=policy_data.get("require_ticket", False),
                )
                self.policies.append(policy)
            
            logger.info(f"Loaded {len(self.policies)} policies from {policies_file}")
            
        except Exception as e:
            logger.error(f"Error loading policies: {e}")
    
    def add_policy(self, policy: RiskPolicy) -> None:
        """Add a policy programmatically.
        
        Args:
            policy: Risk policy to add
        """
        self.policies.append(policy)
    
    def evaluate(self, report: UpgradeReport) -> list[PolicyViolation]:
        """Evaluate a report against all policies.
        
        Args:
            report: Upgrade report to evaluate
            
        Returns:
            List of policy violations
        """
        violations: list[PolicyViolation] = []
        
        for policy in self.policies:
            if self._policy_applies(policy, report.dependency):
                violation = self._check_policy(policy, report)
                if violation:
                    violations.append(violation)
        
        return violations
    
    def _policy_applies(self, policy: RiskPolicy, dependency: Dependency) -> bool:
        """Check if a policy applies to a dependency.
        
        Args:
            policy: Policy to check
            dependency: Dependency
            
        Returns:
            True if policy applies
        """
        package_name = dependency.name.lower()
        
        # Check package list (glob patterns)
        for pattern in policy.packages:
            import fnmatch
            if fnmatch.fnmatch(package_name, pattern.lower()):
                return True
        
        # Check regex
        if policy.package_regex:
            if re.match(policy.package_regex, package_name, re.IGNORECASE):
                return True
        
        # If no specific packages defined, apply to all
        return not policy.packages and not policy.package_regex
    
    def _check_policy(self, policy: RiskPolicy, report: UpgradeReport) -> PolicyViolation | None:
        """Check if a report violates a policy.
        
        Args:
            policy: Policy to check
            report: Upgrade report
            
        Returns:
            Violation or None
        """
        dep = report.dependency
        
        # Check max semver major
        if policy.max_semver_major is not None:
            from packaging.version import parse as parse_version
            
            try:
                current = parse_version(dep.current_version)
                target = parse_version(dep.target_version or "0")
                
                major_diff = target.major - current.major
                
                if major_diff > policy.max_semver_major:
                    return PolicyViolation(
                        policy_name=policy.name,
                        package=dep.name,
                        message=f"Major version jump ({major_diff}) exceeds policy limit ({policy.max_semver_major})",
                        severity=Severity.HIGH if policy.block_upgrade else Severity.MEDIUM,
                    )
            except Exception:
                pass
        
        # Check max risk score
        if policy.max_risk_score is not None:
            if report.risk_score.total_score > policy.max_risk_score:
                return PolicyViolation(
                    policy_name=policy.name,
                    package=dep.name,
                    message=f"Risk score ({report.risk_score.total_score:.0f}) exceeds policy limit ({policy.max_risk_score})",
                    severity=Severity.HIGH if policy.block_upgrade else Severity.MEDIUM,
                )
        
        # Check if approval required for any upgrade
        if policy.require_approval:
            return PolicyViolation(
                policy_name=policy.name,
                package=dep.name,
                message=f"Upgrade requires manual approval per policy",
                severity=Severity.MEDIUM,
            )
        
        return None


class MonorepoAnalyzer:
    """Analyze multiple projects in a monorepo."""
    
    def __init__(self, root_path: Path) -> None:
        """Initialize monorepo analyzer.
        
        Args:
            root_path: Root path of the monorepo
        """
        self.root_path = root_path
        self.projects: list[dict[str, Any]] = []
    
    def discover_projects(self) -> list[dict[str, Any]]:
        """Discover projects in the monorepo.
        
        Returns:
            List of project info dicts
        """
        self.projects = []
        
        # Look for common dependency file patterns
        dependency_files = [
            "pyproject.toml",
            "requirements.txt",
            "Pipfile",
            "setup.py",
        ]
        
        # Find all dependency files
        for dep_file in dependency_files:
            for path in self.root_path.rglob(dep_file):
                # Skip common non-project directories
                skip_dirs = {"node_modules", ".venv", "venv", "__pycache__", ".git", "dist", "build"}
                if any(part in skip_dirs for part in path.parts):
                    continue
                
                project_dir = path.parent
                project_name = project_dir.name
                
                # Check if we already have this project
                existing = next((p for p in self.projects if p["path"] == project_dir), None)
                
                if existing:
                    existing["dependency_files"].append(path)
                else:
                    self.projects.append({
                        "name": project_name,
                        "path": project_dir,
                        "dependency_files": [path],
                        "relative_path": str(path.parent.relative_to(self.root_path)),
                    })
        
        logger.info(f"Discovered {len(self.projects)} projects in monorepo")
        return self.projects
    
    def analyze_all(self, offline: bool = False) -> dict[str, list[UpgradeReport]]:
        """Analyze all projects.
        
        Args:
            offline: If True, use only cached data
            
        Returns:
            Dictionary mapping project name to upgrade reports
        """
        from upgrade_analyzer.analyzer import UpgradeAnalyzer
        
        results: dict[str, list[UpgradeReport]] = {}
        
        for project in self.projects:
            project_name = project["name"]
            project_path = project["path"]
            
            # Use first dependency file
            dep_file = project["dependency_files"][0]
            
            try:
                analyzer = UpgradeAnalyzer(
                    project_root=project_path,
                    dependency_file=dep_file,
                    offline=offline,
                )
                
                reports = analyzer.analyze()
                results[project_name] = reports
                
                analyzer.close()
                
                logger.info(f"Analyzed {project_name}: {len(reports)} dependencies")
                
            except Exception as e:
                logger.error(f"Error analyzing {project_name}: {e}")
                results[project_name] = []
        
        return results
    
    def find_shared_dependencies(self) -> dict[str, list[str]]:
        """Find dependencies used across multiple projects.
        
        Returns:
            Dictionary mapping package name to list of projects using it
        """
        from upgrade_analyzer.parsers.base import DependencyParser
        
        package_usage: dict[str, list[str]] = {}
        
        for project in self.projects:
            project_name = project["name"]
            
            for dep_file in project["dependency_files"]:
                parser_class = DependencyParser.detect_parser(dep_file)
                
                if parser_class:
                    try:
                        parser = parser_class(dep_file)
                        deps = parser.parse()
                        
                        for dep in deps:
                            pkg_name = dep.name.lower()
                            
                            if pkg_name not in package_usage:
                                package_usage[pkg_name] = []
                            
                            if project_name not in package_usage[pkg_name]:
                                package_usage[pkg_name].append(project_name)
                                
                    except Exception as e:
                        logger.debug(f"Error parsing {dep_file}: {e}")
        
        # Filter to only shared dependencies
        return {pkg: projects for pkg, projects in package_usage.items() if len(projects) > 1}
    
    def generate_report(self, results: dict[str, list[UpgradeReport]]) -> str:
        """Generate monorepo analysis report.
        
        Args:
            results: Analysis results per project
            
        Returns:
            Markdown report
        """
        lines = [
            "# Monorepo Upgrade Impact Analysis",
            "",
            f"**Projects analyzed:** {len(results)}",
            "",
        ]
        
        # Summary table
        lines.extend([
            "## Summary",
            "",
            "| Project | Total | Critical | High | Medium | Low |",
            "|---------|-------|----------|------|--------|-----|",
        ])
        
        total_critical = 0
        total_high = 0
        
        for project_name, reports in results.items():
            critical = sum(1 for r in reports if r.risk_score.severity == Severity.CRITICAL)
            high = sum(1 for r in reports if r.risk_score.severity == Severity.HIGH)
            medium = sum(1 for r in reports if r.risk_score.severity == Severity.MEDIUM)
            low = sum(1 for r in reports if r.risk_score.severity == Severity.LOW)
            
            total_critical += critical
            total_high += high
            
            lines.append(f"| {project_name} | {len(reports)} | {critical} | {high} | {medium} | {low} |")
        
        lines.extend([
            "",
            "---",
            "",
        ])
        
        # Shared dependencies section
        shared = self.find_shared_dependencies()
        
        if shared:
            lines.extend([
                "## Shared Dependencies",
                "",
                "| Package | Used By |",
                "|---------|---------|",
            ])
            
            for pkg, projects in sorted(shared.items(), key=lambda x: -len(x[1])):
                lines.append(f"| {pkg} | {', '.join(projects)} |")
            
            lines.append("")
        
        # High-risk items across all projects
        lines.extend([
            "## High-Risk Upgrades",
            "",
        ])
        
        for project_name, reports in results.items():
            high_risk = [r for r in reports if r.risk_score.severity in {Severity.CRITICAL, Severity.HIGH}]
            
            if high_risk:
                lines.append(f"### {project_name}")
                lines.append("")
                
                for report in high_risk:
                    emoji = "🔴" if report.risk_score.severity == Severity.CRITICAL else "🟠"
                    lines.append(
                        f"- {emoji} **{report.dependency.name}**: "
                        f"{report.dependency.current_version} → {report.dependency.target_version} "
                        f"(Score: {report.risk_score.total_score:.0f})"
                    )
                
                lines.append("")
        
        return "\n".join(lines)


def create_example_policies_file(output_path: Path) -> None:
    """Create an example policies file.
    
    Args:
        output_path: Path to save the file
    """
    content = '''# Custom Risk Policies for Upgrade Impact Analyzer
# Place this file as .upgrade-policies.toml in your project root

# Policy 1: Require approval for Django upgrades
[[policies]]
name = "Django Upgrade Review"
description = "All Django upgrades require team lead approval"
packages = ["django", "django-*"]
require_approval = true
notify_channels = ["slack"]

# Policy 2: Block major version jumps for critical packages
[[policies]]
name = "Critical Package Stability"
description = "Limit major version jumps for critical infrastructure"
packages = ["requests", "flask", "sqlalchemy", "celery"]
max_semver_major = 1
block_upgrade = false

# Policy 3: High risk score review
[[policies]]
name = "High Risk Review"
description = "Any upgrade with risk score > 70 needs review"
max_risk_score = 70
require_approval = true
require_ticket = true
'''
    output_path.write_text(content)
    logger.info(f"Created example policies file: {output_path}")
