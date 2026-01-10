"""JSON and SARIF output formatters."""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from upgrade_analyzer.models import Severity, UpgradeReport

logger = logging.getLogger(__name__)


class JSONReporter:
    """Generates JSON format reports."""
    
    def generate_report(self, reports: list[UpgradeReport], output_file: Path | None = None) -> str:
        """Generate JSON report.
        
        Args:
            reports: List of upgrade reports
            output_file: Optional path to save report
            
        Returns:
            JSON string
        """
        data = {
            "version": "1.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "summary": self._generate_summary(reports),
            "dependencies": [
                self._serialize_report(report)
                for report in reports
            ],
        }
        
        json_str = json.dumps(data, indent=2, default=str)
        
        if output_file:
            output_file.write_text(json_str, encoding="utf-8")
        
        return json_str
    
    def _generate_summary(self, reports: list[UpgradeReport]) -> dict[str, Any]:
        """Generate summary statistics."""
        return {
            "total_dependencies": len(reports),
            "critical_risk": sum(1 for r in reports if r.risk_score.severity == Severity.CRITICAL),
            "high_risk": sum(1 for r in reports if r.risk_score.severity == Severity.HIGH),
            "medium_risk": sum(1 for r in reports if r.risk_score.severity == Severity.MEDIUM),
            "low_risk": sum(1 for r in reports if r.risk_score.severity == Severity.LOW),
            "total_breaking_changes": sum(len(r.breaking_changes) for r in reports),
        }
    
    def _serialize_report(self, report: UpgradeReport) -> dict[str, Any]:
        """Serialize a single report to dict."""
        return {
            "package": report.dependency.name,
            "current_version": report.dependency.current_version,
            "target_version": report.dependency.target_version,
            "risk_score": {
                "total": report.risk_score.total_score,
                "severity": report.risk_score.severity.value,
                "factors": [
                    {
                        "name": f.name,
                        "score": f.score,
                        "weight": f.weight,
                        "description": f.description,
                    }
                    for f in report.risk_score.factors
                ],
            },
            "breaking_changes": [
                {
                    "symbol": bc.api_change.symbol_name,
                    "type": bc.api_change.change_type.value,
                    "description": bc.api_change.description,
                    "affected_files": [str(u.file_path) for u in bc.affected_usage],
                    "recommendation": bc.recommendation,
                }
                for bc in report.breaking_changes
            ],
            "api_changes": [
                {
                    "symbol": ac.symbol_name,
                    "type": ac.change_type.value,
                    "old_signature": ac.old_signature,
                    "new_signature": ac.new_signature,
                    "is_breaking": ac.is_breaking,
                }
                for ac in report.api_changes
            ],
            "recommendation": {
                "path": report.recommendation.recommended_path,
                "rationale": report.recommendation.rationale,
                "effort": report.recommendation.estimated_effort,
            } if report.recommendation else None,
            "usage_summary": report.usage_summary,
        }


class SARIFReporter:
    """Generates SARIF format reports for GitHub Security integration."""
    
    SARIF_VERSION = "2.1.0"
    TOOL_NAME = "upgrade-impact-analyzer"
    TOOL_VERSION = "1.0.0"
    
    def generate_report(self, reports: list[UpgradeReport], output_file: Path | None = None) -> str:
        """Generate SARIF report.
        
        Args:
            reports: List of upgrade reports
            output_file: Optional path to save report
            
        Returns:
            JSON string
        """
        sarif = {
            "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
            "version": self.SARIF_VERSION,
            "runs": [
                {
                    "tool": {
                        "driver": {
                            "name": self.TOOL_NAME,
                            "version": self.TOOL_VERSION,
                            "informationUri": "https://github.com/example/upgrade-impact-analyzer",
                            "rules": self._generate_rules(reports),
                        }
                    },
                    "results": self._generate_results(reports),
                }
            ],
        }
        
        json_str = json.dumps(sarif, indent=2, default=str)
        
        if output_file:
            output_file.write_text(json_str, encoding="utf-8")
        
        return json_str
    
    def _generate_rules(self, reports: list[UpgradeReport]) -> list[dict[str, Any]]:
        """Generate SARIF rules from reports."""
        rules = []
        seen_rules = set()
        
        for report in reports:
            for bc in report.breaking_changes:
                rule_id = f"UIA-{bc.api_change.change_type.value.upper()}"
                
                if rule_id not in seen_rules:
                    seen_rules.add(rule_id)
                    rules.append({
                        "id": rule_id,
                        "name": f"{bc.api_change.change_type.value.title()}Symbol",
                        "shortDescription": {
                            "text": f"Symbol {bc.api_change.change_type.value}",
                        },
                        "fullDescription": {
                            "text": f"A symbol used in your code has been {bc.api_change.change_type.value} in the upgrade target.",
                        },
                        "defaultConfiguration": {
                            "level": self._severity_to_sarif_level(report.risk_score.severity),
                        },
                        "helpUri": "https://github.com/example/upgrade-impact-analyzer/docs/rules",
                    })
        
        # Add general upgrade risk rule
        if not rules:
            rules.append({
                "id": "UIA-RISK",
                "name": "UpgradeRisk",
                "shortDescription": {
                    "text": "Dependency upgrade risk detected",
                },
                "fullDescription": {
                    "text": "A dependency upgrade has been analyzed and may pose risks.",
                },
                "defaultConfiguration": {
                    "level": "warning",
                },
            })
        
        return rules
    
    def _generate_results(self, reports: list[UpgradeReport]) -> list[dict[str, Any]]:
        """Generate SARIF results from reports."""
        results = []
        
        for report in reports:
            if report.breaking_changes:
                for bc in report.breaking_changes:
                    for usage in bc.affected_usage:
                        line = usage.line_numbers[0] if usage.line_numbers else 1
                        
                        results.append({
                            "ruleId": f"UIA-{bc.api_change.change_type.value.upper()}",
                            "level": self._severity_to_sarif_level(report.risk_score.severity),
                            "message": {
                                "text": f"{bc.api_change.description}. {bc.recommendation}",
                            },
                            "locations": [
                                {
                                    "physicalLocation": {
                                        "artifactLocation": {
                                            "uri": str(usage.file_path),
                                        },
                                        "region": {
                                            "startLine": line,
                                        },
                                    },
                                }
                            ],
                            "properties": {
                                "package": report.dependency.name,
                                "currentVersion": report.dependency.current_version,
                                "targetVersion": report.dependency.target_version,
                                "riskScore": report.risk_score.total_score,
                            },
                        })
            else:
                # Report upgrade risk even without specific breaking changes
                if report.risk_score.severity in {Severity.HIGH, Severity.CRITICAL}:
                    results.append({
                        "ruleId": "UIA-RISK",
                        "level": self._severity_to_sarif_level(report.risk_score.severity),
                        "message": {
                            "text": f"Upgrading {report.dependency.name} from {report.dependency.current_version} to {report.dependency.target_version} has {report.risk_score.severity.value} risk (score: {report.risk_score.total_score:.1f}/100)",
                        },
                        "locations": [
                            {
                                "physicalLocation": {
                                    "artifactLocation": {
                                        "uri": str(report.dependency.source_file or "requirements.txt"),
                                    },
                                    "region": {
                                        "startLine": 1,
                                    },
                                },
                            }
                        ],
                        "properties": {
                            "package": report.dependency.name,
                            "currentVersion": report.dependency.current_version,
                            "targetVersion": report.dependency.target_version,
                            "riskScore": report.risk_score.total_score,
                        },
                    })
        
        return results
    
    def _severity_to_sarif_level(self, severity: Severity) -> str:
        """Convert severity to SARIF level."""
        mapping = {
            Severity.CRITICAL: "error",
            Severity.HIGH: "error",
            Severity.MEDIUM: "warning",
            Severity.LOW: "note",
        }
        return mapping.get(severity, "warning")


class JUnitReporter:
    """Generates JUnit XML format for CI integration."""
    
    def generate_report(self, reports: list[UpgradeReport], output_file: Path | None = None) -> str:
        """Generate JUnit XML report.
        
        Args:
            reports: List of upgrade reports
            output_file: Optional path to save report
            
        Returns:
            XML string
        """
        import xml.etree.ElementTree as ET
        
        # Create testsuite
        testsuite = ET.Element("testsuite")
        testsuite.set("name", "Upgrade Impact Analysis")
        testsuite.set("tests", str(len(reports)))
        
        failures = 0
        errors = 0
        
        for report in reports:
            testcase = ET.SubElement(testsuite, "testcase")
            testcase.set("name", f"{report.dependency.name} upgrade")
            testcase.set("classname", "upgrade_analyzer")
            
            if report.risk_score.severity in {Severity.CRITICAL, Severity.HIGH}:
                failures += 1
                failure = ET.SubElement(testcase, "failure")
                failure.set("type", report.risk_score.severity.value)
                failure.set("message", f"Risk score: {report.risk_score.total_score:.1f}/100")
                
                # Add details
                details = []
                details.append(f"Package: {report.dependency.name}")
                details.append(f"Upgrade: {report.dependency.current_version} -> {report.dependency.target_version}")
                details.append(f"Severity: {report.risk_score.severity.value}")
                
                for factor in report.risk_score.factors:
                    details.append(f"{factor.name}: {factor.score:.1f}")
                
                for bc in report.breaking_changes:
                    details.append(f"Breaking: {bc.api_change.description}")
                
                failure.text = "\n".join(details)
        
        testsuite.set("failures", str(failures))
        testsuite.set("errors", str(errors))
        
        # Convert to string
        xml_str = ET.tostring(testsuite, encoding="unicode")
        
        # Add XML declaration
        xml_str = '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_str
        
        if output_file:
            output_file.write_text(xml_str, encoding="utf-8")
        
        return xml_str
