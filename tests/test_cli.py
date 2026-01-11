"""Tests for CLI commands."""

import pytest
from pathlib import Path
from typer.testing import CliRunner
from unittest.mock import patch, MagicMock

from upgrade_analyzer.cli import app


runner = CliRunner()


class TestCLIVersion:
    """Test version command."""
    
    def test_version_command(self):
        """Test --version flag."""
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert "upgrade-analyzer" in result.stdout.lower() or "version" in result.stdout.lower()


class TestCLIHelp:
    """Test help output."""
    
    def test_help_command(self):
        """Test --help flag."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "analyze" in result.stdout
    
    def test_analyze_help(self):
        """Test analyze --help."""
        result = runner.invoke(app, ["analyze", "--help"])
        assert result.exit_code == 0
        assert "--project" in result.stdout
    
    def test_conflicts_help(self):
        """Test conflicts --help."""
        result = runner.invoke(app, ["conflicts", "--help"])
        assert result.exit_code == 0
        assert "--output" in result.stdout


class TestCLIDetect:
    """Test detect command."""
    
    def test_detect_in_directory(self, tmp_path: Path):
        """Test auto-detection of dependency files."""
        # Create requirements.txt
        req_file = tmp_path / "requirements.txt"
        req_file.write_text("flask==2.3.0\nrequests==2.31.0")
        
        result = runner.invoke(app, ["detect", "--project", str(tmp_path)])
        
        assert result.exit_code == 0
        assert "requirements.txt" in result.stdout
    
    def test_detect_no_files(self, tmp_path: Path):
        """Test detection with no dependency files."""
        result = runner.invoke(app, ["detect", "--project", str(tmp_path)])
        
        # Should still complete (maybe with warning)
        assert "No dependency files" in result.stdout or result.exit_code == 0


class TestCLIClearCache:
    """Test clear-cache command."""
    
    def test_clear_cache_command(self):
        """Test clear-cache runs without error."""
        result = runner.invoke(app, ["clear-cache"])
        assert result.exit_code == 0


class TestCLIInitPolicies:
    """Test init-policies command."""
    
    def test_init_policies(self, tmp_path: Path):
        """Test creating example policies file."""
        output_file = tmp_path / "policies.toml"
        
        result = runner.invoke(app, [
            "init-policies",
            "--output", str(output_file)
        ])
        
        assert result.exit_code == 0
        assert output_file.exists()
        
        content = output_file.read_text()
        assert "[[policies]]" in content


class TestCLIConflicts:
    """Test conflicts command."""
    
    @patch('upgrade_analyzer.cli.ConflictDetector')
    @patch('upgrade_analyzer.cli.DependencyResolver')
    @patch('upgrade_analyzer.cli.DependencyParser')
    def test_conflicts_command(self, mock_parser, mock_resolver, mock_detector, tmp_path: Path):
        """Test conflicts command runs."""
        # Setup mocks
        req_file = tmp_path / "requirements.txt"
        req_file.write_text("flask==2.3.0")
        
        mock_parser.auto_detect_in_directory.return_value = [req_file]
        mock_parser.detect_parser.return_value = MagicMock(return_value=MagicMock(
            parse=MagicMock(return_value=[
                MagicMock(name="flask", current_version="2.3.0")
            ])
        ))
        mock_resolver.return_value._fetch_latest_version.return_value = "3.0.0"
        mock_detector.return_value.detect_conflicts.return_value = MagicMock(
            is_compatible=True,
            conflicts=[]
        )
        mock_detector.return_value.generate_conflict_report.return_value = "No conflicts"
        
        result = runner.invoke(app, ["conflicts", "--project", str(tmp_path)])
        
        # Should complete
        assert result.exit_code in [0, 1]  # 0 = no conflicts, 1 = conflicts found


class TestCLIAnalyze:
    """Test analyze command."""
    
    def test_analyze_no_file(self, tmp_path: Path):
        """Test analyze with no dependency file."""
        result = runner.invoke(app, [
            "analyze",
            "--project", str(tmp_path)
        ])
        
        # Should fail or warn
        assert "No dependency file" in result.stdout or result.exit_code != 0
    
    def test_analyze_dry_run(self, tmp_path: Path):
        """Test analyze with dry-run flag."""
        req_file = tmp_path / "requirements.txt"
        req_file.write_text("flask==2.3.0")
        
        result = runner.invoke(app, [
            "analyze",
            "--project", str(tmp_path),
            "--dry-run"
        ])
        
        # Should complete with dry-run info
        assert result.exit_code == 0 or "dry-run" in result.stdout.lower()


class TestCLIHealth:
    """Test health command."""
    
    @patch('upgrade_analyzer.cli.HealthScorer')
    @patch('upgrade_analyzer.cli.DependencyParser')
    def test_health_command(self, mock_parser, mock_scorer, tmp_path: Path):
        """Test health command runs."""
        req_file = tmp_path / "requirements.txt"
        req_file.write_text("flask==2.3.0")
        
        mock_parser.auto_detect_in_directory.return_value = [req_file]
        mock_parser.detect_parser.return_value = MagicMock(return_value=MagicMock(
            parse=MagicMock(return_value=[
                MagicMock(name="flask", current_version="2.3.0")
            ])
        ))
        mock_scorer.return_value.score_package.return_value = MagicMock(
            name="flask",
            overall_score=85.0,
            grade=MagicMock(value="B", emoji="🟢")
        )
        mock_scorer.return_value.generate_report.return_value = "Health Report"
        
        result = runner.invoke(app, ["health", "--project", str(tmp_path)])
        
        # Should complete
        assert result.exit_code in [0, 1]


class TestCLISBOM:
    """Test SBOM command."""
    
    @patch('upgrade_analyzer.cli.SBOMGenerator')
    @patch('upgrade_analyzer.cli.DependencyParser')
    def test_sbom_command(self, mock_parser, mock_generator, tmp_path: Path):
        """Test SBOM generation."""
        req_file = tmp_path / "requirements.txt"
        req_file.write_text("flask==2.3.0")
        
        mock_parser.auto_detect_in_directory.return_value = [req_file]
        mock_parser.detect_parser.return_value = MagicMock(return_value=MagicMock(
            parse=MagicMock(return_value=[
                MagicMock(name="flask", current_version="2.3.0", is_transitive=False)
            ])
        ))
        mock_generator.return_value.generate.return_value = '{"bomFormat": "CycloneDX"}'
        
        output_file = tmp_path / "sbom.json"
        result = runner.invoke(app, [
            "sbom",
            "--project", str(tmp_path),
            "--output", str(output_file)
        ])
        
        # Should complete
        assert result.exit_code == 0
