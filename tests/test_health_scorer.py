"""Tests for health scoring system."""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from upgrade_analyzer.health import HealthScorer, PackageHealth, HealthGrade


class TestHealthGrade:
    """Test health grade enum."""
    
    def test_grade_from_score_a(self):
        """Test A grade threshold."""
        grade = HealthGrade.from_score(95)
        assert grade == HealthGrade.A
        assert grade.emoji == "🟢"
    
    def test_grade_from_score_b(self):
        """Test B grade threshold."""
        grade = HealthGrade.from_score(82)
        assert grade == HealthGrade.B
        assert grade.emoji == "🟢"
    
    def test_grade_from_score_c(self):
        """Test C grade threshold."""
        grade = HealthGrade.from_score(72)
        assert grade == HealthGrade.C
        assert grade.emoji == "🟡"
    
    def test_grade_from_score_d(self):
        """Test D grade threshold."""
        grade = HealthGrade.from_score(62)
        assert grade == HealthGrade.D
        assert grade.emoji == "🟠"
    
    def test_grade_from_score_f(self):
        """Test F grade threshold."""
        grade = HealthGrade.from_score(45)
        assert grade == HealthGrade.F
        assert grade.emoji == "🔴"


class TestPackageHealth:
    """Test package health dataclass."""
    
    def test_package_health_creation(self):
        """Test creating package health object."""
        health = PackageHealth(
            name="flask",
            version="2.3.0",
            overall_score=85.0,
            grade=HealthGrade.B,
            maintenance_score=90.0,
            popularity_score=85.0,
            quality_score=80.0,
            security_score=85.0,
        )
        
        assert health.name == "flask"
        assert health.grade == HealthGrade.B
        assert health.overall_score == 85.0


class TestHealthScorer:
    """Test health scoring logic."""
    
    def test_scorer_initialization(self):
        """Test scorer initializes correctly."""
        scorer = HealthScorer(offline=True)
        assert scorer.offline is True
        scorer.close()
    
    def test_calculate_maintenance_score_active(self):
        """Test maintenance score for active package."""
        scorer = HealthScorer(offline=True)
        
        # Recent release (within 30 days)
        from datetime import datetime, timedelta
        recent_date = (datetime.now() - timedelta(days=15)).isoformat()
        
        score = scorer._calculate_maintenance_score(
            last_release=recent_date,
            release_frequency=12,  # Monthly releases
            has_ci=True,
        )
        
        assert score >= 80  # Active = high score
        scorer.close()
    
    def test_calculate_maintenance_score_stale(self):
        """Test maintenance score for stale package."""
        scorer = HealthScorer(offline=True)
        
        # Old release (over 2 years)
        from datetime import datetime, timedelta
        old_date = (datetime.now() - timedelta(days=800)).isoformat()
        
        score = scorer._calculate_maintenance_score(
            last_release=old_date,
            release_frequency=0,
            has_ci=False,
        )
        
        assert score <= 40  # Stale = low score
        scorer.close()
    
    def test_calculate_popularity_score(self):
        """Test popularity score calculation."""
        scorer = HealthScorer(offline=True)
        
        score = scorer._calculate_popularity_score(
            downloads_per_month=1000000,  # Popular
            github_stars=10000,
            dependents_count=500,
        )
        
        assert score >= 70  # Popular = high score
        scorer.close()
    
    def test_calculate_quality_score(self):
        """Test quality score calculation."""
        scorer = HealthScorer(offline=True)
        
        score = scorer._calculate_quality_score(
            has_tests=True,
            has_docs=True,
            has_type_hints=True,
            code_coverage=85.0,
        )
        
        assert score >= 80  # High quality
        scorer.close()
    
    def test_calculate_security_score_no_vulns(self):
        """Test security score with no vulnerabilities."""
        scorer = HealthScorer(offline=True)
        
        score = scorer._calculate_security_score(
            known_vulnerabilities=0,
            has_security_policy=True,
        )
        
        assert score >= 90  # No vulns = high score
        scorer.close()
    
    def test_calculate_security_score_with_vulns(self):
        """Test security score with vulnerabilities."""
        scorer = HealthScorer(offline=True)
        
        score = scorer._calculate_security_score(
            known_vulnerabilities=3,
            has_security_policy=False,
        )
        
        assert score <= 50  # Vulns = low score
        scorer.close()
    
    def test_overall_score_weighted(self):
        """Test overall score is properly weighted."""
        scorer = HealthScorer(offline=True)
        
        # Weights should sum to 1.0
        assert abs(
            scorer.weights["maintenance"]
            + scorer.weights["popularity"]
            + scorer.weights["quality"]
            + scorer.weights["security"]
            - 1.0
        ) < 0.001
        
        scorer.close()
    
    def test_generate_health_report(self):
        """Test markdown report generation."""
        scorer = HealthScorer(offline=True)
        
        packages = [
            PackageHealth(
                name="flask",
                version="2.3.0",
                overall_score=85.0,
                grade=HealthGrade.B,
                maintenance_score=90.0,
                popularity_score=85.0,
                quality_score=80.0,
                security_score=85.0,
            ),
            PackageHealth(
                name="requests",
                version="2.31.0",
                overall_score=92.0,
                grade=HealthGrade.A,
                maintenance_score=95.0,
                popularity_score=90.0,
                quality_score=90.0,
                security_score=93.0,
            ),
        ]
        
        report = scorer.generate_report(packages)
        
        assert "flask" in report
        assert "requests" in report
        assert "🟢" in report  # A or B grade
        
        scorer.close()
