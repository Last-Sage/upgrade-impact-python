"""Dependency conflict detection for upgrade safety analysis."""

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.version import Version, parse

from upgrade_analyzer.http_client import SyncHTTPClient
from upgrade_analyzer.cache import get_cache
from upgrade_analyzer.models import Dependency

logger = logging.getLogger(__name__)


@dataclass
class ConflictInfo:
    """Information about a dependency conflict."""
    
    package: str
    required_by: str
    required_version: str  # The constraint (e.g., ">=2.0,<3.0")
    conflicting_package: str
    conflicting_version: str  # The version that would be installed
    reason: str
    severity: str = "high"  # "high", "medium", "low"
    resolution: str = ""


@dataclass
class CompatibilityReport:
    """Report of compatibility analysis."""
    
    package: str
    from_version: str
    to_version: str
    is_compatible: bool
    conflicts: list[ConflictInfo] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    resolved_versions: dict[str, str] = field(default_factory=dict)


class ConflictDetector:
    """Detects dependency conflicts when upgrading packages."""
    
    def __init__(self, offline: bool = False) -> None:
        """Initialize conflict detector.
        
        Args:
            offline: If True, only use cached data
        """
        self.offline = offline
        self.client = SyncHTTPClient()
        self.cache = get_cache()
        self._package_deps_cache: dict[str, dict[str, list[str]]] = {}
    
    def detect_conflicts(
        self,
        package: str,
        from_version: str,
        to_version: str,
        installed_deps: list[Dependency],
    ) -> CompatibilityReport:
        """Detect conflicts when upgrading a package.
        
        Args:
            package: Package being upgraded
            from_version: Current version
            to_version: Target version
            installed_deps: Currently installed dependencies
            
        Returns:
            CompatibilityReport with conflict details
        """
        report = CompatibilityReport(
            package=package,
            from_version=from_version,
            to_version=to_version,
            is_compatible=True,
        )
        
        # Get dependencies of the target version
        target_deps = self._get_package_dependencies(package, to_version)
        
        if target_deps is None:
            report.warnings.append(f"Could not fetch dependencies for {package}=={to_version}")
            return report
        
        # Build installed packages map
        installed_map = {dep.name.lower(): dep.current_version for dep in installed_deps}
        installed_map[package.lower()] = to_version  # Include the upgrade target
        
        # Check each dependency of the upgraded package
        for dep_name, dep_specifier in target_deps.items():
            dep_name_lower = dep_name.lower()
            
            # Check if installed version satisfies new requirements
            if dep_name_lower in installed_map:
                installed_version = installed_map[dep_name_lower]
                
                try:
                    spec = SpecifierSet(dep_specifier)
                    if installed_version and not spec.contains(parse(installed_version)):
                        conflict = ConflictInfo(
                            package=dep_name,
                            required_by=package,
                            required_version=dep_specifier,
                            conflicting_package=dep_name,
                            conflicting_version=installed_version,
                            reason=f"{package}=={to_version} requires {dep_name}{dep_specifier}, "
                                   f"but {installed_version} is installed",
                            severity="high",
                            resolution=f"Upgrade {dep_name} to satisfy {dep_specifier}",
                        )
                        report.conflicts.append(conflict)
                        report.is_compatible = False
                except Exception as e:
                    logger.debug(f"Error checking specifier {dep_specifier}: {e}")
        
        # Check reverse dependencies - packages that depend on the one being upgraded
        for dep in installed_deps:
            if dep.name.lower() == package.lower():
                continue
            
            dep_requires = self._get_package_dependencies(dep.name, dep.current_version)
            if not dep_requires:
                continue
            
            package_lower = package.lower()
            if package_lower in {k.lower() for k in dep_requires.keys()}:
                # This package depends on the one we're upgrading
                required_spec = next(
                    (v for k, v in dep_requires.items() if k.lower() == package_lower),
                    ""
                )
                
                try:
                    spec = SpecifierSet(required_spec)
                    if not spec.contains(parse(to_version)):
                        conflict = ConflictInfo(
                            package=package,
                            required_by=dep.name,
                            required_version=required_spec,
                            conflicting_package=package,
                            conflicting_version=to_version,
                            reason=f"{dep.name}=={dep.current_version} requires {package}{required_spec}, "
                                   f"but upgrading to {to_version}",
                            severity="high",
                            resolution=f"Upgrade {dep.name} first, or find compatible versions",
                        )
                        report.conflicts.append(conflict)
                        report.is_compatible = False
                except Exception as e:
                    logger.debug(f"Error checking reverse dependency: {e}")
        
        return report
    
    def detect_all_conflicts(
        self,
        upgrades: list[tuple[str, str, str]],  # [(package, from_version, to_version), ...]
        installed_deps: list[Dependency],
    ) -> list[CompatibilityReport]:
        """Detect conflicts for multiple upgrades.
        
        Args:
            upgrades: List of (package, from_version, to_version) tuples
            installed_deps: Currently installed dependencies
            
        Returns:
            List of CompatibilityReports
        """
        reports = []
        
        for package, from_version, to_version in upgrades:
            report = self.detect_conflicts(package, from_version, to_version, installed_deps)
            reports.append(report)
        
        # Check for conflicts between simultaneous upgrades
        cross_conflicts = self._check_cross_upgrade_conflicts(upgrades)
        for conflict in cross_conflicts:
            # Find or create report for the conflicting package
            for report in reports:
                if report.package.lower() == conflict.package.lower():
                    report.conflicts.append(conflict)
                    report.is_compatible = False
                    break
        
        return reports
    
    def _check_cross_upgrade_conflicts(
        self,
        upgrades: list[tuple[str, str, str]],
    ) -> list[ConflictInfo]:
        """Check for conflicts between multiple simultaneous upgrades."""
        conflicts = []
        
        # Build map of what each upgrade requires
        upgrade_requirements: dict[str, dict[str, str]] = {}
        
        for package, from_version, to_version in upgrades:
            deps = self._get_package_dependencies(package, to_version)
            if deps:
                upgrade_requirements[package] = deps
        
        # Check if any upgrade's deps conflict with another upgrade
        for pkg1, deps1 in upgrade_requirements.items():
            for pkg2, deps2 in upgrade_requirements.items():
                if pkg1 == pkg2:
                    continue
                
                # Check if pkg1's deps require something incompatible with pkg2
                pkg2_lower = pkg2.lower()
                if pkg2_lower in {k.lower() for k in deps1.keys()}:
                    required_spec = next(
                        (v for k, v in deps1.items() if k.lower() == pkg2_lower),
                        ""
                    )
                    
                    # Find the version pkg2 is upgrading to
                    pkg2_target = next(
                        (v[2] for v in upgrades if v[0].lower() == pkg2_lower),
                        None
                    )
                    
                    if pkg2_target and required_spec:
                        try:
                            spec = SpecifierSet(required_spec)
                            if not spec.contains(parse(pkg2_target)):
                                conflicts.append(ConflictInfo(
                                    package=pkg2,
                                    required_by=pkg1,
                                    required_version=required_spec,
                                    conflicting_package=pkg2,
                                    conflicting_version=pkg2_target,
                                    reason=f"Upgrading {pkg1} requires {pkg2}{required_spec}, "
                                           f"which conflicts with upgrading {pkg2} to {pkg2_target}",
                                    severity="high",
                                    resolution="Upgrade packages sequentially or find compatible versions",
                                ))
                        except Exception as e:
                            logger.debug(f"Error checking cross-upgrade conflict: {e}")
        
        return conflicts
    
    def _get_package_dependencies(
        self,
        package: str,
        version: str,
    ) -> dict[str, str] | None:
        """Get dependencies for a package version.
        
        Args:
            package: Package name
            version: Version string
            
        Returns:
            Dictionary mapping dependency names to version specifiers
        """
        cache_key = f"{package}:{version}:deps"
        
        # Check memory cache
        if cache_key in self._package_deps_cache:
            return self._package_deps_cache.get(cache_key)
        
        # Check disk cache
        cached = self.cache.get(cache_key, cache_type="pypi", ttl_hours=168)  # 1 week
        if cached is not None:
            self._package_deps_cache[cache_key] = cached
            return cached
        
        if self.offline:
            return None
        
        # Fetch from PyPI
        try:
            url = f"https://pypi.org/pypi/{package}/{version}/json"
            response = self.client.get(url)
            
            if response.status_code != 200:
                logger.warning(f"Failed to fetch {package}=={version} from PyPI: {response.status_code}")
                return None
            
            data = response.json()
            requires_dist = data.get("info", {}).get("requires_dist") or []
            
            deps: dict[str, str] = {}
            for req_str in requires_dist:
                try:
                    req = Requirement(req_str)
                    
                    # Skip extras and environment markers for now
                    if req.marker:
                        # Only include non-extra markers
                        marker_str = str(req.marker)
                        if "extra" in marker_str:
                            continue
                    
                    deps[req.name] = str(req.specifier) if req.specifier else ""
                except Exception as e:
                    logger.debug(f"Error parsing requirement {req_str}: {e}")
            
            # Cache result
            self.cache.set(cache_key, deps, cache_type="pypi")
            self._package_deps_cache[cache_key] = deps
            
            return deps
            
        except Exception as e:
            logger.error(f"Error fetching dependencies for {package}=={version}: {e}")
            return None
    
    def suggest_compatible_versions(
        self,
        package: str,
        constraints: list[str],
    ) -> list[str]:
        """Suggest versions that satisfy all constraints.
        
        Args:
            package: Package name
            constraints: List of version specifiers
            
        Returns:
            List of compatible versions (newest first)
        """
        try:
            # Combine all constraints
            combined_spec = SpecifierSet(",".join(constraints))
            
            # Fetch available versions
            url = f"https://pypi.org/pypi/{package}/json"
            response = self.client.get(url)
            
            if response.status_code != 200:
                return []
            
            data = response.json()
            releases = data.get("releases", {})
            
            # Filter versions that satisfy constraints
            compatible = []
            for version_str in releases.keys():
                try:
                    version = parse(version_str)
                    if version.is_prerelease or version.is_devrelease:
                        continue
                    if combined_spec.contains(version):
                        compatible.append(version_str)
                except Exception:
                    continue
            
            # Sort by version (newest first)
            compatible.sort(key=lambda v: parse(v), reverse=True)
            
            return compatible[:10]  # Return top 10
            
        except Exception as e:
            logger.error(f"Error finding compatible versions for {package}: {e}")
            return []
    
    def generate_conflict_report(
        self,
        reports: list[CompatibilityReport],
    ) -> str:
        """Generate markdown report of conflicts.
        
        Args:
            reports: List of compatibility reports
            
        Returns:
            Markdown formatted report
        """
        lines = ["# Dependency Conflict Analysis\n"]
        
        total_conflicts = sum(len(r.conflicts) for r in reports)
        incompatible = [r for r in reports if not r.is_compatible]
        
        if not total_conflicts:
            lines.append("✅ **No conflicts detected!** All upgrades are compatible.\n")
            return "\n".join(lines)
        
        lines.append(f"⚠️ **{total_conflicts} conflicts detected** in {len(incompatible)} packages\n")
        
        for report in reports:
            if not report.conflicts:
                continue
            
            lines.append(f"\n## {report.package} ({report.from_version} → {report.to_version})\n")
            
            for conflict in report.conflicts:
                severity_icon = {"high": "🔴", "medium": "🟠", "low": "🟡"}.get(conflict.severity, "❓")
                
                lines.append(f"### {severity_icon} {conflict.package}\n")
                lines.append(f"- **Required by**: {conflict.required_by}")
                lines.append(f"- **Requirement**: `{conflict.required_version}`")
                lines.append(f"- **Conflict**: `{conflict.conflicting_version}`")
                lines.append(f"- **Reason**: {conflict.reason}")
                
                if conflict.resolution:
                    lines.append(f"- **Resolution**: {conflict.resolution}")
                
                lines.append("")
        
        return "\n".join(lines)
    
    def close(self) -> None:
        """Close HTTP client."""
        self.client.close()
