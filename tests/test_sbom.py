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
        generator = SBOMGenerator()
        assert generator is not None
        generator.close()
    
    def test_generate_cyclonedx(self):
        """Test CycloneDX format generation."""
        generator = SBOMGenerator()
        
        deps = [
            Dependency(name="flask", current_version="2.3.0"),
            Dependency(name="requests", current_version="2.31.0"),
        ]
        
        sbom = generator.generate(deps, format="cyclonedx")
        
        # Should be valid JSON
        parsed = json.loads(sbom)
        
        # Check CycloneDX structure
        assert "bomFormat" in parsed
        assert parsed["bomFormat"] == "CycloneDX"
        assert "specVersion" in parsed
        assert "components" in parsed
        assert len(parsed["components"]) == 2
        
        generator.close()
    
    def test_generate_spdx(self):
        """Test SPDX format generation."""
        generator = SBOMGenerator()
        
        deps = [
            Dependency(name="flask", current_version="2.3.0"),
        ]
        
        sbom = generator.generate(deps, format="spdx")
        
        # Should be valid JSON
        parsed = json.loads(sbom)
        
        # Check SPDX structure
        assert "spdxVersion" in parsed
        assert "packages" in parsed
        
        generator.close()
    
    def test_generate_with_metadata(self):
        """Test SBOM includes package metadata."""
        generator = SBOMGenerator()
        
        deps = [
            Dependency(name="flask", current_version="2.3.0"),
        ]
        
        sbom = generator.generate(deps, format="cyclonedx")
        parsed = json.loads(sbom)
        
        component = parsed["components"][0]
        assert component["name"] == "flask"
        assert component["version"] == "2.3.0"
        assert "purl" in component  # Package URL
        
        generator.close()
    
    def test_include_transitive_deps(self):
        """Test SBOM includes transitive dependencies."""
        generator = SBOMGenerator()
        
        deps = [
            Dependency(name="flask", current_version="2.3.0", is_transitive=False),
            Dependency(name="werkzeug", current_version="2.3.0", is_transitive=True),
        ]
        
        sbom = generator.generate(deps, format="cyclonedx", include_transitive=True)
        parsed = json.loads(sbom)
        
        assert len(parsed["components"]) == 2
        
        generator.close()


class TestLicenseAuditor:
    """Test license auditing."""
    
    def test_auditor_initialization(self):
        """Test auditor initializes correctly."""
        auditor = LicenseAuditor()
        assert auditor is not None
        auditor.close()
    
    def test_known_licenses(self):
        """Test that common licenses are recognized."""
        auditor = LicenseAuditor()
        
        assert auditor.is_osi_approved("MIT")
        assert auditor.is_osi_approved("Apache-2.0")
        assert auditor.is_osi_approved("BSD-3-Clause")
        
        auditor.close()
    
    def test_permissive_licenses(self):
        """Test permissive license classification."""
        auditor = LicenseAuditor()
        
        assert auditor.is_permissive("MIT")
        assert auditor.is_permissive("Apache-2.0")
        assert auditor.is_permissive("BSD-2-Clause")
        
        auditor.close()
    
    def test_copyleft_licenses(self):
        """Test copyleft license classification."""
        auditor = LicenseAuditor()
        
        assert auditor.is_copyleft("GPL-3.0")
        assert auditor.is_copyleft("LGPL-3.0")
        assert auditor.is_copyleft("AGPL-3.0")
        
        auditor.close()
    
    def test_deny_list_check(self):
        """Test deny list enforcement."""
        auditor = LicenseAuditor(deny_list=["AGPL-3.0", "GPL-3.0"])
        
        result = auditor.audit_license("AGPL-3.0")
        
        assert not result.allowed
        assert "AGPL-3.0" in result.reason
        
        auditor.close()
    
    def test_allow_list_check(self):
        """Test allow list enforcement."""
        auditor = LicenseAuditor(allow_list=["MIT", "Apache-2.0"])
        
        allowed_result = auditor.audit_license("MIT")
        assert allowed_result.allowed
        
        denied_result = auditor.audit_license("GPL-3.0")
        assert not denied_result.allowed
        
        auditor.close()
    
    def test_audit_packages(self):
        """Test auditing multiple packages."""
        auditor = LicenseAuditor(deny_list=["AGPL-3.0"])
        
        deps = [
            Dependency(name="flask", current_version="2.3.0"),
            Dependency(name="requests", current_version="2.31.0"),
        ]
        
        # Mock license fetching
        with patch.object(auditor, '_fetch_license') as mock_fetch:
            mock_fetch.side_effect = ["BSD-3-Clause", "Apache-2.0"]
            
            results = auditor.audit_packages(deps)
            
            assert len(results) == 2
            assert all(r.allowed for r in results)
        
        auditor.close()
    
    def test_generate_compliance_report(self):
        """Test compliance report generation."""
        auditor = LicenseAuditor()
        
        deps = [
            Dependency(name="flask", current_version="2.3.0"),
        ]
        
        with patch.object(auditor, '_fetch_license', return_value="BSD-3-Clause"):
            report = auditor.generate_report(deps)
        
        assert "flask" in report
        assert "BSD-3-Clause" in report
        
        auditor.close()
