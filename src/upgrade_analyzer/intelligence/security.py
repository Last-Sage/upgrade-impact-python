"""Security integration with pip-audit and CVE databases."""

import json
import logging
import subprocess
from dataclasses import dataclass, field

import httpx

from upgrade_analyzer.cache import get_cache
from upgrade_analyzer.models import Dependency, Severity

logger = logging.getLogger(__name__)


@dataclass
class Vulnerability:
    """Represents a security vulnerability."""
    
    id: str  # CVE ID or GHSA ID
    package: str
    vulnerable_versions: str
    fixed_version: str | None
    severity: str  # low, moderate, high, critical
    summary: str
    url: str = ""
    
    @property
    def as_severity(self) -> Severity:
        """Convert to internal Severity enum."""
        mapping = {
            "critical": Severity.CRITICAL,
            "high": Severity.HIGH,
            "moderate": Severity.MEDIUM,
            "medium": Severity.MEDIUM,
            "low": Severity.LOW,
        }
        return mapping.get(self.severity.lower(), Severity.MEDIUM)


@dataclass
class SecurityReport:
    """Security analysis report for a package."""
    
    package: str
    current_version: str
    target_version: str | None
    vulnerabilities: list[Vulnerability] = field(default_factory=list)
    is_vulnerable: bool = False
    upgrade_fixes_vulns: bool = False
    new_vulns_in_target: list[Vulnerability] = field(default_factory=list)


class SecurityScanner:
    """Scans for security vulnerabilities using multiple sources."""
    
    OSV_API_URL = "https://api.osv.dev/v1/query"
    
    def __init__(self, offline: bool = False) -> None:
        """Initialize security scanner.
        
        Args:
            offline: If True, only use cached data
        """
        self.offline = offline
        self.cache = get_cache()
        self.client = httpx.Client(timeout=30.0) if not offline else None
        self._pip_audit_available: bool | None = None
    
    def _check_pip_audit(self) -> bool:
        """Check if pip-audit is available."""
        if self._pip_audit_available is not None:
            return self._pip_audit_available
        
        try:
            result = subprocess.run(
                ["pip-audit", "--version"],
                capture_output=True,
                timeout=5,
            )
            self._pip_audit_available = result.returncode == 0
        except (subprocess.SubprocessError, FileNotFoundError):
            self._pip_audit_available = False
        
        return self._pip_audit_available
    
    def scan_package(
        self,
        dependency: Dependency,
        check_target: bool = True
    ) -> SecurityReport:
        """Scan a package for vulnerabilities.
        
        Args:
            dependency: Dependency to scan
            check_target: Also check target version
            
        Returns:
            Security report
        """
        report = SecurityReport(
            package=dependency.name,
            current_version=dependency.current_version,
            target_version=dependency.target_version,
        )
        
        # Scan current version
        current_vulns = self._scan_version(dependency.name, dependency.current_version)
        
        if current_vulns:
            report.vulnerabilities = current_vulns
            report.is_vulnerable = True
        
        # Scan target version
        if check_target and dependency.target_version:
            target_vulns = self._scan_version(dependency.name, dependency.target_version)
            
            # Check if upgrade fixes vulns
            current_ids = {v.id for v in current_vulns}
            target_ids = {v.id for v in target_vulns}
            
            fixed = current_ids - target_ids
            new = target_ids - current_ids
            
            report.upgrade_fixes_vulns = len(fixed) > 0
            report.new_vulns_in_target = [v for v in target_vulns if v.id in new]
        
        return report
    
    def _scan_version(self, package: str, version: str) -> list[Vulnerability]:
        """Scan a specific package version.
        
        Args:
            package: Package name
            version: Version string
            
        Returns:
            List of vulnerabilities
        """
        cache_key = f"security:{package}:{version}"
        
        # Try cache first (TTL: 24 hours)
        cached = self.cache.get(cache_key, cache_type="security", ttl_hours=24)
        if cached:
            return [Vulnerability(**v) for v in cached]
        
        vulnerabilities: list[Vulnerability] = []
        
        # Try pip-audit first (most reliable for Python)
        if self._check_pip_audit():
            pip_vulns = self._scan_with_pip_audit(package, version)
            vulnerabilities.extend(pip_vulns)
        
        # Also check OSV database
        if not self.offline:
            osv_vulns = self._scan_with_osv(package, version)
            
            # Merge without duplicates
            seen_ids = {v.id for v in vulnerabilities}
            for v in osv_vulns:
                if v.id not in seen_ids:
                    vulnerabilities.append(v)
        
        # Cache results
        if vulnerabilities:
            cache_data = [
                {
                    "id": v.id,
                    "package": v.package,
                    "vulnerable_versions": v.vulnerable_versions,
                    "fixed_version": v.fixed_version,
                    "severity": v.severity,
                    "summary": v.summary,
                    "url": v.url,
                }
                for v in vulnerabilities
            ]
            self.cache.set(cache_key, cache_data, cache_type="security")
        
        return vulnerabilities
    
    def _scan_with_pip_audit(self, package: str, version: str) -> list[Vulnerability]:
        """Scan using pip-audit.
        
        Args:
            package: Package name
            version: Version string
            
        Returns:
            List of vulnerabilities
        """
        try:
            # Create temporary requirements
            import tempfile
            
            with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
                f.write(f"{package}=={version}\n")
                temp_file = f.name
            
            result = subprocess.run(
                ["pip-audit", "-r", temp_file, "--format", "json", "--progress-spinner", "off"],
                capture_output=True,
                text=True,
                timeout=60,
            )
            
            # Clean up
            import os
            os.unlink(temp_file)
            
            if result.returncode == 0:
                return []  # No vulnerabilities
            
            # Parse JSON output
            try:
                data = json.loads(result.stdout)
                vulnerabilities = []
                
                for dep in data.get("dependencies", []):
                    for vuln in dep.get("vulns", []):
                        vulnerabilities.append(
                            Vulnerability(
                                id=vuln.get("id", ""),
                                package=package,
                                vulnerable_versions=vuln.get("affected_versions", ""),
                                fixed_version=vuln.get("fixed_versions", [""])[0] if vuln.get("fixed_versions") else None,
                                severity=vuln.get("severity", "unknown"),
                                summary=vuln.get("description", ""),
                                url=vuln.get("url", ""),
                            )
                        )
                
                return vulnerabilities
                
            except json.JSONDecodeError:
                return []
        
        except subprocess.TimeoutExpired:
            logger.warning("pip-audit timed out")
            return []
        except Exception as e:
            logger.error(f"Error running pip-audit: {e}")
            return []
    
    def _scan_with_osv(self, package: str, version: str) -> list[Vulnerability]:
        """Scan using OSV.dev API.
        
        Args:
            package: Package name
            version: Version string
            
        Returns:
            List of vulnerabilities
        """
        if not self.client:
            return []
        
        try:
            response = self.client.post(
                self.OSV_API_URL,
                json={
                    "package": {
                        "ecosystem": "PyPI",
                        "name": package,
                    },
                    "version": version,
                },
            )
            
            if response.status_code != 200:
                return []
            
            data = response.json()
            vulnerabilities = []
            
            for vuln in data.get("vulns", []):
                # Extract CVE ID if available
                vuln_id = vuln.get("id", "")
                for alias in vuln.get("aliases", []):
                    if alias.startswith("CVE-"):
                        vuln_id = alias
                        break
                
                # Determine severity
                severity = "unknown"
                for db in vuln.get("database_specific", {}).get("severity", []):
                    if db.get("type") == "CVSS_V3":
                        score = float(db.get("score", 0))
                        if score >= 9.0:
                            severity = "critical"
                        elif score >= 7.0:
                            severity = "high"
                        elif score >= 4.0:
                            severity = "moderate"
                        else:
                            severity = "low"
                        break
                
                vulnerabilities.append(
                    Vulnerability(
                        id=vuln_id,
                        package=package,
                        vulnerable_versions="",  # OSV uses ranges, complex to parse
                        fixed_version=None,
                        severity=severity,
                        summary=vuln.get("summary", ""),
                        url=f"https://osv.dev/vulnerability/{vuln.get('id', '')}",
                    )
                )
            
            return vulnerabilities
        
        except Exception as e:
            logger.error(f"Error querying OSV: {e}")
            return []
    
    def close(self) -> None:
        """Close HTTP client."""
        if self.client:
            self.client.close()


def integrate_security_with_risk(
    security_report: SecurityReport,
    current_risk_score: float
) -> tuple[float, str]:
    """Integrate security findings with risk score.
    
    Args:
        security_report: Security scan results
        current_risk_score: Current calculated risk score
        
    Returns:
        Tuple of (adjusted_score, reason)
    """
    adjustment = 0.0
    reasons = []
    
    if security_report.is_vulnerable:
        vuln_count = len(security_report.vulnerabilities)
        critical_count = sum(
            1 for v in security_report.vulnerabilities
            if v.severity.lower() == "critical"
        )
        high_count = sum(
            1 for v in security_report.vulnerabilities
            if v.severity.lower() == "high"
        )
        
        # Increase urgency for vulnerable packages
        if critical_count > 0:
            adjustment -= 20  # Lower risk = more urgent to upgrade
            reasons.append(f"{critical_count} CRITICAL vulnerabilities in current version")
        elif high_count > 0:
            adjustment -= 10
            reasons.append(f"{high_count} HIGH vulnerabilities in current version")
        elif vuln_count > 0:
            adjustment -= 5
            reasons.append(f"{vuln_count} vulnerabilities in current version")
        
        if security_report.upgrade_fixes_vulns:
            adjustment -= 10
            reasons.append("Upgrade fixes existing vulnerabilities")
    
    if security_report.new_vulns_in_target:
        # Increase risk if target version has new vulnerabilities
        adjustment += 30
        reasons.append(f"Target version has {len(security_report.new_vulns_in_target)} new vulnerabilities")
    
    adjusted_score = max(0, min(100, current_risk_score + adjustment))
    reason = "; ".join(reasons) if reasons else "No security concerns"
    
    return adjusted_score, reason
