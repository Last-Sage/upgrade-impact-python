"""SBOM generation in CycloneDX and SPDX formats."""

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from upgrade_analyzer.models import Dependency

logger = logging.getLogger(__name__)


class SBOMGenerator:
    """Generate Software Bill of Materials in standard formats."""
    
    def __init__(self, project_name: str = "project", project_version: str = "0.0.0") -> None:
        """Initialize SBOM generator.
        
        Args:
            project_name: Name of the project
            project_version: Version of the project
        """
        self.project_name = project_name
        self.project_version = project_version
    
    def generate_cyclonedx(
        self,
        dependencies: list[Dependency],
        output_file: Path | None = None,
    ) -> str:
        """Generate CycloneDX 1.5 SBOM.
        
        Args:
            dependencies: List of dependencies
            output_file: Optional path to save SBOM
            
        Returns:
            JSON string
        """
        sbom = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.5",
            "serialNumber": f"urn:uuid:{uuid.uuid4()}",
            "version": 1,
            "metadata": {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "tools": [
                    {
                        "vendor": "Last Sage",
                        "name": "upgrade-impact-analyzer",
                        "version": "1.0.0",
                    }
                ],
                "component": {
                    "type": "application",
                    "name": self.project_name,
                    "version": self.project_version,
                },
            },
            "components": [],
            "dependencies": [],
        }
        
        # Add components
        for dep in dependencies:
            component = {
                "type": "library",
                "name": dep.name,
                "version": dep.current_version,
                "purl": f"pkg:pypi/{dep.name}@{dep.current_version}",
                "bom-ref": f"pkg:pypi/{dep.name}@{dep.current_version}",
            }
            
            if dep.extras:
                component["properties"] = [
                    {"name": "extras", "value": ",".join(dep.extras)}
                ]
            
            sbom["components"].append(component)
            
            # Add dependency relationship
            sbom["dependencies"].append({
                "ref": f"pkg:pypi/{dep.name}@{dep.current_version}",
                "dependsOn": [],  # Would need transitive info
            })
        
        json_str = json.dumps(sbom, indent=2)
        
        if output_file:
            output_file.write_text(json_str, encoding="utf-8")
            logger.info(f"CycloneDX SBOM saved to {output_file}")
        
        return json_str
    
    def generate_spdx(
        self,
        dependencies: list[Dependency],
        output_file: Path | None = None,
    ) -> str:
        """Generate SPDX 2.3 SBOM.
        
        Args:
            dependencies: List of dependencies
            output_file: Optional path to save SBOM
            
        Returns:
            JSON string
        """
        doc_id = f"SPDXRef-DOCUMENT-{uuid.uuid4().hex[:8]}"
        
        sbom = {
            "spdxVersion": "SPDX-2.3",
            "dataLicense": "CC0-1.0",
            "SPDXID": doc_id,
            "name": f"{self.project_name}-sbom",
            "documentNamespace": f"https://spdx.org/spdxdocs/{self.project_name}-{uuid.uuid4()}",
            "creationInfo": {
                "created": datetime.now(timezone.utc).isoformat(),
                "creators": [
                    "Tool: upgrade-impact-analyzer-1.0.0",
                ],
            },
            "packages": [],
            "relationships": [],
        }
        
        # Add root package
        root_spdxid = f"SPDXRef-Package-{self.project_name}"
        sbom["packages"].append({
            "SPDXID": root_spdxid,
            "name": self.project_name,
            "versionInfo": self.project_version,
            "downloadLocation": "NOASSERTION",
            "filesAnalyzed": False,
        })
        
        # Add dependencies as packages
        for dep in dependencies:
            spdxid = f"SPDXRef-Package-{dep.name.replace('-', '').replace('_', '')}"
            
            package = {
                "SPDXID": spdxid,
                "name": dep.name,
                "versionInfo": dep.current_version,
                "downloadLocation": f"https://pypi.org/project/{dep.name}/{dep.current_version}/",
                "filesAnalyzed": False,
                "externalRefs": [
                    {
                        "referenceCategory": "PACKAGE-MANAGER",
                        "referenceType": "purl",
                        "referenceLocator": f"pkg:pypi/{dep.name}@{dep.current_version}",
                    }
                ],
            }
            
            sbom["packages"].append(package)
            
            # Add relationship
            sbom["relationships"].append({
                "spdxElementId": root_spdxid,
                "relationshipType": "DEPENDS_ON",
                "relatedSpdxElement": spdxid,
            })
        
        json_str = json.dumps(sbom, indent=2)
        
        if output_file:
            output_file.write_text(json_str, encoding="utf-8")
            logger.info(f"SPDX SBOM saved to {output_file}")
        
        return json_str


class LicenseAuditor:
    """Audit dependency licenses for compliance."""
    
    # License compatibility matrix
    COPYLEFT_LICENSES = {
        "GPL-2.0", "GPL-3.0", "AGPL-3.0", "LGPL-2.1", "LGPL-3.0",
        "GPL-2.0-only", "GPL-3.0-only", "AGPL-3.0-only",
    }
    
    PERMISSIVE_LICENSES = {
        "MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC",
        "Unlicense", "CC0-1.0", "0BSD",
    }
    
    PROBLEMATIC_FOR_COMMERCIAL = {"AGPL-3.0", "AGPL-3.0-only"}
    
    def __init__(self, offline: bool = False) -> None:
        """Initialize license auditor.
        
        Args:
            offline: If True, use only cached data
        """
        self.offline = offline
        self.client = None if offline else __import__("httpx").Client(timeout=30.0)
    
    def audit_licenses(
        self,
        dependencies: list[Dependency],
        allowed_licenses: set[str] | None = None,
        denied_licenses: set[str] | None = None,
    ) -> dict[str, Any]:
        """Audit licenses of dependencies.
        
        Args:
            dependencies: Dependencies to audit
            allowed_licenses: Set of allowed license identifiers
            denied_licenses: Set of denied license identifiers
            
        Returns:
            Audit report
        """
        report = {
            "total": len(dependencies),
            "packages": [],
            "violations": [],
            "warnings": [],
            "summary": {
                "permissive": 0,
                "copyleft": 0,
                "unknown": 0,
                "violations": 0,
            },
        }
        
        for dep in dependencies:
            license_info = self._get_license(dep.name)
            
            pkg_report = {
                "name": dep.name,
                "version": dep.current_version,
                "license": license_info.get("license", "UNKNOWN"),
                "license_url": license_info.get("url"),
            }
            
            license_id = pkg_report["license"].upper()
            
            # Check if permitted
            if denied_licenses and license_id in denied_licenses:
                report["violations"].append({
                    "package": dep.name,
                    "license": pkg_report["license"],
                    "reason": "License explicitly denied",
                })
                report["summary"]["violations"] += 1
            
            elif allowed_licenses and license_id not in allowed_licenses:
                if license_id != "UNKNOWN":
                    report["warnings"].append({
                        "package": dep.name,
                        "license": pkg_report["license"],
                        "reason": "License not in allowed list",
                    })
            
            # Check for copyleft
            if license_id in self.COPYLEFT_LICENSES:
                report["summary"]["copyleft"] += 1
                
                if license_id in self.PROBLEMATIC_FOR_COMMERCIAL:
                    report["warnings"].append({
                        "package": dep.name,
                        "license": pkg_report["license"],
                        "reason": "AGPL license may require source disclosure",
                    })
            
            elif license_id in self.PERMISSIVE_LICENSES:
                report["summary"]["permissive"] += 1
            
            else:
                report["summary"]["unknown"] += 1
            
            report["packages"].append(pkg_report)
        
        return report
    
    def _get_license(self, package_name: str) -> dict[str, str]:
        """Get license info from PyPI.
        
        Args:
            package_name: Package name
            
        Returns:
            License info dict
        """
        if not self.client:
            return {"license": "UNKNOWN"}
        
        try:
            response = self.client.get(f"https://pypi.org/pypi/{package_name}/json")
            
            if response.status_code == 200:
                data = response.json()
                info = data.get("info", {})
                
                # Try license field
                license_str = info.get("license", "")
                
                # Try classifiers
                if not license_str or license_str.lower() == "unknown":
                    for classifier in info.get("classifiers", []):
                        if classifier.startswith("License :: OSI Approved :: "):
                            license_str = classifier.split("::")[-1].strip()
                            break
                
                return {
                    "license": license_str or "UNKNOWN",
                    "url": info.get("project_urls", {}).get("License"),
                }
                
        except Exception as e:
            logger.debug(f"Error fetching license for {package_name}: {e}")
        
        return {"license": "UNKNOWN"}
    
    def generate_report(
        self,
        audit_result: dict[str, Any],
        output_file: Path | None = None,
    ) -> str:
        """Generate license audit report.
        
        Args:
            audit_result: Result from audit_licenses
            output_file: Optional output path
            
        Returns:
            Markdown report
        """
        lines = [
            "# License Audit Report",
            "",
            f"**Total Packages:** {audit_result['total']}",
            f"**Permissive:** {audit_result['summary']['permissive']}",
            f"**Copyleft:** {audit_result['summary']['copyleft']}",
            f"**Unknown:** {audit_result['summary']['unknown']}",
            f"**Violations:** {audit_result['summary']['violations']}",
            "",
        ]
        
        if audit_result["violations"]:
            lines.append("## ❌ Violations")
            lines.append("")
            for v in audit_result["violations"]:
                lines.append(f"- **{v['package']}**: {v['license']} - {v['reason']}")
            lines.append("")
        
        if audit_result["warnings"]:
            lines.append("## ⚠️ Warnings")
            lines.append("")
            for w in audit_result["warnings"]:
                lines.append(f"- **{w['package']}**: {w['license']} - {w['reason']}")
            lines.append("")
        
        lines.append("## All Licenses")
        lines.append("")
        lines.append("| Package | Version | License |")
        lines.append("|---------|---------|---------|")
        
        for pkg in audit_result["packages"]:
            lines.append(f"| {pkg['name']} | {pkg['version']} | {pkg['license']} |")
        
        report = "\n".join(lines)
        
        if output_file:
            output_file.write_text(report, encoding="utf-8")
        
        return report
    
    def close(self) -> None:
        """Close HTTP client."""
        if self.client:
            self.client.close()
