"""Tests for dependency conflict detector."""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from upgrade_analyzer.conflict_detector import (
    ConflictDetector,
    ConflictInfo,
    CompatibilityReport,
)
from upgrade_analyzer.models import Dependency


class TestConflictInfo:
    """Test conflict info dataclass."""
    
    def test_conflict_info_creation(self):
        """Test creating conflict info."""
        conflict = ConflictInfo(
            package="requests",
            required_by="flask",
            required_version=">=2.0,<3.0",
            conflicting_package="requests",
            conflicting_version="3.0.0",
            reason="Version mismatch",
            severity="high",
            resolution="Downgrade requests",
        )
        
        assert conflict.package == "requests"
        assert conflict.severity == "high"


class TestCompatibilityReport:
    """Test compatibility report dataclass."""
    
    def test_compatible_report(self):
        """Test compatible upgrade report."""
        report = CompatibilityReport(
            package="flask",
            from_version="2.0.0",
            to_version="2.3.0",
            is_compatible=True,
        )
        
        assert report.is_compatible
        assert len(report.conflicts) == 0
    
    def test_incompatible_report(self):
        """Test incompatible upgrade report."""
        conflict = ConflictInfo(
            package="werkzeug",
            required_by="flask",
            required_version=">=3.0",
            conflicting_package="werkzeug",
            conflicting_version="2.0.0",
            reason="Requires werkzeug 3.x",
        )
        
        report = CompatibilityReport(
            package="flask",
            from_version="2.0.0",
            to_version="3.0.0",
            is_compatible=False,
            conflicts=[conflict],
        )
        
        assert not report.is_compatible
        assert len(report.conflicts) == 1


class TestConflictDetector:
    """Test conflict detection logic."""
    
    @patch('upgrade_analyzer.conflict_detector.SyncHTTPClient')
    def test_detector_initialization(self, mock_client):
        """Test detector initializes correctly."""
        detector = ConflictDetector(offline=True)
        assert detector.offline is True
        detector.close()
    
    @patch('upgrade_analyzer.conflict_detector.SyncHTTPClient')
    def test_detect_no_conflicts(self, mock_client):
        """Test detection when no conflicts exist."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "info": {"requires_dist": ["werkzeug>=2.0"]}
        }
        mock_client.return_value.get.return_value = mock_response
        
        detector = ConflictDetector()
        
        installed = [
            Dependency(name="werkzeug", current_version="2.3.0"),
        ]
        
        report = detector.detect_conflicts(
            package="flask",
            from_version="2.0.0",
            to_version="2.3.0",
            installed_deps=installed,
        )
        
        assert report.is_compatible
        detector.close()
    
    @patch('upgrade_analyzer.conflict_detector.SyncHTTPClient')
    def test_detect_forward_conflict(self, mock_client):
        """Test detecting forward dependency conflict."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "info": {"requires_dist": ["werkzeug>=3.0"]}  # Requires 3.x
        }
        mock_client.return_value.get.return_value = mock_response
        
        detector = ConflictDetector()
        
        installed = [
            Dependency(name="werkzeug", current_version="2.3.0"),  # Has 2.x
        ]
        
        report = detector.detect_conflicts(
            package="flask",
            from_version="2.0.0",
            to_version="3.0.0",
            installed_deps=installed,
        )
        
        assert not report.is_compatible
        assert len(report.conflicts) >= 1
        assert any(c.package.lower() == "werkzeug" for c in report.conflicts)
        detector.close()
    
    def test_generate_conflict_report_no_conflicts(self):
        """Test markdown report with no conflicts."""
        detector = ConflictDetector(offline=True)
        
        reports = [
            CompatibilityReport(
                package="flask",
                from_version="2.0.0",
                to_version="2.3.0",
                is_compatible=True,
            )
        ]
        
        markdown = detector.generate_conflict_report(reports)
        
        assert "No conflicts detected" in markdown
        detector.close()
    
    def test_generate_conflict_report_with_conflicts(self):
        """Test markdown report with conflicts."""
        detector = ConflictDetector(offline=True)
        
        conflict = ConflictInfo(
            package="werkzeug",
            required_by="flask",
            required_version=">=3.0",
            conflicting_package="werkzeug",
            conflicting_version="2.0.0",
            reason="Version mismatch",
            severity="high",
        )
        
        reports = [
            CompatibilityReport(
                package="flask",
                from_version="2.0.0",
                to_version="3.0.0",
                is_compatible=False,
                conflicts=[conflict],
            )
        ]
        
        markdown = detector.generate_conflict_report(reports)
        
        assert "1 conflicts detected" in markdown
        assert "werkzeug" in markdown
        assert "🔴" in markdown  # High severity icon
        detector.close()


class TestConflictDetectorOffline:
    """Test offline behavior."""
    
    def test_offline_returns_none_for_deps(self):
        """Test offline mode returns None for dependency fetch."""
        detector = ConflictDetector(offline=True)
        
        deps = detector._get_package_dependencies("flask", "2.0.0")
        assert deps is None
        
        detector.close()
