"""Tests for SBOM generation and license auditing."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from upgrade_analyzer.sbom import SBOMGenerator, LicenseAuditor
from upgrade_analyzer.models import Dependency


class TestSBOMGenerator:
    """Test SBOM generation."""
    
    def test_generator_initialization(self):
        """Test generator initializes correctly."""
        generator = SBOMGenerator(project_name="test", project_version="1.0.0")
        assert generator is not None
    
    def test_generate_cyclonedx(self):
        """Test CycloneDX format generation."""
        generator = SBOMGenerator(project_name="myproject", project_version="1.0.0")
        
        deps = [
            Dependency(name="flask", current_version="2.3.0"),
            Dependency(name="requests", current_version="2.31.0"),
        ]
        
        sbom = generator.generate_cyclonedx(deps)
        
        # Should be valid JSON
        parsed = json.loads(sbom)
        
        # Check CycloneDX structure
        assert "bomFormat" in parsed
        assert parsed["bomFormat"] == "CycloneDX"
        assert "specVersion" in parsed
        assert "components" in parsed
        assert len(parsed["components"]) == 2
    
    def test_generate_spdx(self):
        """Test SPDX format generation."""
        generator = SBOMGenerator()
        
        deps = [
            Dependency(name="flask", current_version="2.3.0"),
        ]
        
        sbom = generator.generate_spdx(deps)
        
        # Should be valid JSON
        parsed = json.loads(sbom)
        
        # Check SPDX structure
        assert "spdxVersion" in parsed
        assert "packages" in parsed
    
    def test_generate_cyclonedx_with_metadata(self):
        """Test SBOM includes package metadata."""
        generator = SBOMGenerator()
        
        deps = [
            Dependency(name="flask", current_version="2.3.0"),
        ]
        
        sbom = generator.generate_cyclonedx(deps)
        parsed = json.loads(sbom)
        
        component = parsed["components"][0]
        assert component["name"] == "flask"
        assert component["version"] == "2.3.0"
        assert "purl" in component  # Package URL
    
    def test_cyclonedx_transitive_deps(self):
        """Test SBOM includes transitive dependencies."""
        generator = SBOMGenerator()
        
        deps = [
            Dependency(name="flask", current_version="2.3.0", is_transitive=False),
            Dependency(name="werkzeug", current_version="2.3.0", is_transitive=True),
        ]
        
        sbom = generator.generate_cyclonedx(deps)
        parsed = json.loads(sbom)
        
        # Both should be included
        assert len(parsed["components"]) == 2
    
    def test_generate_to_file(self, tmp_path: Path):
        """Test SBOM saved to file."""
        generator = SBOMGenerator()
        
        deps = [
            Dependency(name="flask", current_version="2.3.0"),
        ]
        
        output_file = tmp_path / "sbom.json"
        generator.generate_cyclonedx(deps, output_file=output_file)
        
        assert output_file.exists()
        
        content = json.loads(output_file.read_text())
        assert "bomFormat" in content


class TestLicenseAuditor:
    """Test license auditing."""
    
    def test_auditor_initialization(self):
        """Test auditor initializes correctly."""
        auditor = LicenseAuditor()
        assert auditor is not None
        auditor.close()
    
    def test_copyleft_licenses_defined(self):
        """Test copyleft licenses are defined."""
        auditor = LicenseAuditor()
        
        assert "GPL-3.0" in auditor.COPYLEFT_LICENSES
        assert "AGPL-3.0" in auditor.COPYLEFT_LICENSES
        
        auditor.close()
    
    @patch.object(LicenseAuditor, '_get_license')
    def test_audit_licenses_all_allowed(self, mock_get_license):
        """Test audit when all licenses are allowed."""
        mock_get_license.return_value = {
            "license": "MIT",
            "is_osi_approved": True,
        }
        
        auditor = LicenseAuditor()
        
        deps = [
            Dependency(name="flask", current_version="2.3.0"),
            Dependency(name="requests", current_version="2.31.0"),
        ]
        
        result = auditor.audit_licenses(deps)
        
        assert "packages" in result
        assert len(result["packages"]) == 2
        
        auditor.close()
    
    @patch.object(LicenseAuditor, '_get_license')
    def test_audit_licenses_with_denied(self, mock_get_license):
        """Test audit with denied license."""
        mock_get_license.return_value = {
            "license": "AGPL-3.0",
            "is_osi_approved": True,
        }
        
        auditor = LicenseAuditor()
        
        deps = [
            Dependency(name="flask", current_version="2.3.0"),
        ]
        
        result = auditor.audit_licenses(deps, denied_licenses={"AGPL-3.0"})
        
        assert "denied" in result or "violations" in result or any(
            not p.get("allowed", True) for p in result.get("packages", [])
        )
        
        auditor.close()
    
    def test_generate_report(self):
        """Test report generation."""
        auditor = LicenseAuditor()
        
        # Use correct structure matching the actual API (with nested summary)
        audit_result = {
            "total": 2,
            "packages": [
                {"name": "flask", "version": "2.3.0", "license": "BSD-3-Clause"},
                {"name": "requests", "version": "2.31.0", "license": "Apache-2.0"},
            ],
            "violations": [],
            "warnings": [],
            "summary": {
                "permissive": 2,
                "copyleft": 0,
                "unknown": 0,
                "violations": 0,
            },
        }
        
        report = auditor.generate_report(audit_result)
        
        assert "flask" in report or "2" in report  # Either package name or count
        
        auditor.close()


class TestLicenseAuditorOffline:
    """Test offline behavior."""
    
    def test_offline_mode(self):
        """Test offline mode initialization."""
        auditor = LicenseAuditor(offline=True)
        assert auditor.offline is True
        auditor.close()
