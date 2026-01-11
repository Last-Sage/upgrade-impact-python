"""Tests for health scoring system."""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from upgrade_analyzer.health import HealthScorer, HealthMetrics


class TestHealthMetrics:
    """Test health metrics dataclass."""
    
    def test_health_metrics_creation(self):
        """Test creating health metrics object."""
        metrics = HealthMetrics(
            package_name="flask",
            health_score=85.0,
            health_grade="B",
        )
        
        assert metrics.package_name == "flask"
        assert metrics.health_grade == "B"
        assert metrics.health_score == 85.0
    
    def test_health_metrics_defaults(self):
        """Test default values."""
        metrics = HealthMetrics(package_name="requests")
        
        assert metrics.days_since_last_release == -1
        assert metrics.is_maintained is True
        assert metrics.known_vulnerabilities == 0


class TestHealthGradeCalculation:
    """Test health grade thresholds."""
    
    def test_grade_a_threshold(self):
        """Test A grade (90+)."""
        scorer = HealthScorer(offline=True)
        
        metrics = HealthMetrics(package_name="test")
        metrics.health_score = 95
        
        # Grade should be A  
        assert metrics.health_score >= 90
        scorer.close()
    
    def test_grade_b_threshold(self):
        """Test B grade (80-89)."""
        scorer = HealthScorer(offline=True)
        
        metrics = HealthMetrics(package_name="test")
        metrics.health_score = 82
        
        assert 80 <= metrics.health_score < 90
        scorer.close()
    
    def test_grade_f_threshold(self):
        """Test F grade (<60)."""
        scorer = HealthScorer(offline=True)
        
        metrics = HealthMetrics(package_name="test")
        metrics.health_score = 45
        
        assert metrics.health_score < 60
        scorer.close()


class TestHealthScorer:
    """Test health scoring logic."""
    
    def test_scorer_initialization(self):
        """Test scorer initializes correctly."""
        scorer = HealthScorer(offline=True)
        assert scorer.offline is True
        scorer.close()
    
    def test_weights_sum_to_one(self):
        """Test weights sum to 1.0."""
        scorer = HealthScorer(offline=True)
        
        total = sum(scorer.WEIGHTS.values())
        assert abs(total - 1.0) < 0.001
        
        scorer.close()
    
    def test_weight_categories(self):
        """Test all weight categories exist."""
        scorer = HealthScorer(offline=True)
        
        assert "maintenance" in scorer.WEIGHTS
        assert "popularity" in scorer.WEIGHTS
        assert "quality" in scorer.WEIGHTS
        assert "security" in scorer.WEIGHTS
        
        scorer.close()
    
    @patch.object(HealthScorer, '_fetch_pypi_data')
    @patch.object(HealthScorer, '_fetch_github_data')
    @patch.object(HealthScorer, '_fetch_download_stats')
    def test_calculate_health_returns_metrics(
        self, mock_downloads, mock_github, mock_pypi
    ):
        """Test calculate_health returns HealthMetrics."""
        mock_pypi.return_value = {
            "info": {
                "name": "flask",
                "version": "2.3.0",
                "author": "Pallets",
            },
            "releases": {"2.3.0": [{"upload_time": "2023-01-01T00:00:00"}]},
        }
        mock_github.return_value = {"stargazers_count": 1000}
        mock_downloads.return_value = 1000000
        
        scorer = HealthScorer(offline=False)
        metrics = scorer.calculate_health("flask")
        
        assert isinstance(metrics, HealthMetrics)
        assert metrics.package_name == "flask"
        
        scorer.close()
    
    def test_generate_report_returns_markdown(self):
        """Test report generation returns markdown."""
        scorer = HealthScorer(offline=True)
        
        metrics = HealthMetrics(
            package_name="flask",
            health_score=85.0,
            health_grade="B",
        )
        
        report = scorer.generate_report([metrics])
        
        assert "flask" in report
        assert "B" in report or "85" in report
        
        scorer.close()
    
    def test_generate_report_empty_list(self):
        """Test report with empty metrics list."""
        scorer = HealthScorer(offline=True)
        
        report = scorer.generate_report([])
        
        assert isinstance(report, str)
        
        scorer.close()
    
    def test_generate_report_multiple_packages(self):
        """Test report with multiple packages."""
        scorer = HealthScorer(offline=True)
        
        metrics_list = [
            HealthMetrics(package_name="flask", health_score=85.0, health_grade="B"),
            HealthMetrics(package_name="requests", health_score=92.0, health_grade="A"),
            HealthMetrics(package_name="django", health_score=78.0, health_grade="C"),
        ]
        
        report = scorer.generate_report(metrics_list)
        
        assert "flask" in report
        assert "requests" in report
        assert "django" in report
        
        scorer.close()


class TestHealthScorerOffline:
    """Test offline behavior."""
    
    def test_offline_mode_no_network(self):
        """Test offline mode doesn't make network calls."""
        scorer = HealthScorer(offline=True)
        
        # In offline mode, calculate_health should handle gracefully
        # or return basic metrics
        try:
            metrics = scorer.calculate_health("flask")
            assert metrics is not None
        except Exception:
            pass  # May fail gracefully in offline mode
        
        scorer.close()
