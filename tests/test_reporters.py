"""Tests for JSON, SARIF, and JUnit reporters."""

from pathlib import Path

import pytest

from upgrade_analyzer.models import (
    APIChange,
    BreakingChange,
    ChangeType,
    Dependency,
    RiskFactor,
    RiskScore,
    Severity,
    UpgradeReport,
    UsageNode,
)
from upgrade_analyzer.reporters.json_formats import (
    JSONReporter,
    SARIFReporter,
    JUnitReporter,
)


@pytest.fixture
def sample_report():
    """Create a sample upgrade report for testing."""
    dep = Dependency(
        name="requests",
        current_version="2.28.0",
        target_version="2.31.0",
    )
    
    risk_score = RiskScore(
        total_score=65.0,
        severity=Severity.HIGH,
        factors=[
            RiskFactor(name="SemVer", score=40, weight=0.3, description="Minor version bump"),
            RiskFactor(name="Usage", score=80, weight=0.5, description="High usage"),
            RiskFactor(name="Changelog", score=30, weight=0.2, description="Some changes"),
        ]
    )
    
    api_change = APIChange(
        symbol_name="requests.Session.get",
        change_type=ChangeType.MODIFIED,
        old_signature="(url, **kwargs)",
        new_signature="(url, *, timeout=None, **kwargs)",
        description="Added timeout parameter",
    )
    
    usage_node = UsageNode(
        package_name="requests",
        symbol_path="requests.Session.get",
        file_path=Path("src/client.py"),
        line_numbers=[10, 25],
    )
    
    breaking_change = BreakingChange(
        dependency=dep,
        api_change=api_change,
        affected_usage=[usage_node],
        recommendation="Update function calls to include timeout parameter",
    )
    
    return UpgradeReport(
        dependency=dep,
        risk_score=risk_score,
        api_changes=[api_change],
        breaking_changes=[breaking_change],
        changelog_entries=[],
        recommendation=None,
        usage_summary={"files": 3, "calls": 15},
    )


class TestJSONReporter:
    """Tests for JSON reporter."""
    
    def test_generate_report(self, sample_report):
        """Test JSON report generation."""
        reporter = JSONReporter()
        json_str = reporter.generate_report([sample_report])
        
        import json
        data = json.loads(json_str)
        
        assert data["version"] == "1.0"
        assert "generated_at" in data
        assert len(data["dependencies"]) == 1
        
        dep = data["dependencies"][0]
        assert dep["package"] == "requests"
        assert dep["current_version"] == "2.28.0"
        assert dep["target_version"] == "2.31.0"
        assert dep["risk_score"]["total"] == 65.0
        assert dep["risk_score"]["severity"] == "high"
    
    def test_summary_generation(self, sample_report):
        """Test summary statistics."""
        reporter = JSONReporter()
        json_str = reporter.generate_report([sample_report])
        
        import json
        data = json.loads(json_str)
        
        summary = data["summary"]
        assert summary["total_dependencies"] == 1
        assert summary["high_risk"] == 1
        assert summary["total_breaking_changes"] == 1
    
    def test_save_to_file(self, sample_report, tmp_path):
        """Test saving report to file."""
        output_file = tmp_path / "report.json"
        
        reporter = JSONReporter()
        reporter.generate_report([sample_report], output_file)
        
        assert output_file.exists()
        content = output_file.read_text()
        assert "requests" in content


class TestSARIFReporter:
    """Tests for SARIF reporter."""
    
    def test_generate_sarif(self, sample_report):
        """Test SARIF report generation."""
        reporter = SARIFReporter()
        sarif_str = reporter.generate_report([sample_report])
        
        import json
        data = json.loads(sarif_str)
        
        assert data["version"] == "2.1.0"
        assert "$schema" in data
        assert len(data["runs"]) == 1
        
        run = data["runs"][0]
        assert run["tool"]["driver"]["name"] == "upgrade-impact-analyzer"
        assert len(run["results"]) > 0
    
    def test_sarif_rules(self, sample_report):
        """Test SARIF rules generation."""
        reporter = SARIFReporter()
        sarif_str = reporter.generate_report([sample_report])
        
        import json
        data = json.loads(sarif_str)
        
        rules = data["runs"][0]["tool"]["driver"]["rules"]
        assert len(rules) > 0
    
    def test_sarif_severity_mapping(self, sample_report):
        """Test severity to SARIF level mapping."""
        reporter = SARIFReporter()
        
        assert reporter._severity_to_sarif_level(Severity.CRITICAL) == "error"
        assert reporter._severity_to_sarif_level(Severity.HIGH) == "error"
        assert reporter._severity_to_sarif_level(Severity.MEDIUM) == "warning"
        assert reporter._severity_to_sarif_level(Severity.LOW) == "note"


class TestJUnitReporter:
    """Tests for JUnit XML reporter."""
    
    def test_generate_junit(self, sample_report):
        """Test JUnit XML generation."""
        reporter = JUnitReporter()
        xml_str = reporter.generate_report([sample_report])
        
        assert '<?xml version="1.0"' in xml_str
        assert "<testsuite" in xml_str
        assert 'name="Upgrade Impact Analysis"' in xml_str
    
    def test_junit_failure(self, sample_report):
        """Test JUnit failure reporting for high risk."""
        reporter = JUnitReporter()
        xml_str = reporter.generate_report([sample_report])
        
        assert "<failure" in xml_str
        assert "requests" in xml_str
    
    def test_save_junit_to_file(self, sample_report, tmp_path):
        """Test saving JUnit to file."""
        output_file = tmp_path / "junit.xml"
        
        reporter = JUnitReporter()
        reporter.generate_report([sample_report], output_file)
        
        assert output_file.exists()
        assert "<testsuite" in output_file.read_text()
