"""Dependency health scoring and metrics."""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx

from upgrade_analyzer.cache import get_cache

logger = logging.getLogger(__name__)


@dataclass
class HealthMetrics:
    """Health metrics for a package."""
    
    package_name: str
    
    # Maintenance metrics
    last_release_date: str | None = None
    days_since_last_release: int = -1
    release_frequency: float = 0.0  # releases per year
    is_maintained: bool = True
    
    # Popularity metrics
    downloads_last_month: int = 0
    stars: int = 0
    forks: int = 0
    
    # Quality metrics
    has_tests: bool = False
    has_ci: bool = False
    has_type_hints: bool = False
    documentation_url: str | None = None
    
    # Security metrics
    known_vulnerabilities: int = 0
    
    # Overall score
    health_score: float = 0.0  # 0-100
    health_grade: str = "?"  # A, B, C, D, F
    
    # Breakdown
    score_breakdown: dict[str, float] = field(default_factory=dict)


class HealthScorer:
    """Calculate package health scores."""
    
    # Weight factors
    WEIGHTS = {
        "maintenance": 0.30,
        "popularity": 0.20,
        "quality": 0.25,
        "security": 0.25,
    }
    
    def __init__(self, offline: bool = False) -> None:
        """Initialize health scorer.
        
        Args:
            offline: If True, use only cached data
        """
        self.offline = offline
        self.cache = get_cache()
        self.client = httpx.Client(timeout=30.0) if not offline else None
    
    def calculate_health(self, package_name: str) -> HealthMetrics:
        """Calculate health metrics for a package.
        
        Args:
            package_name: Package name
            
        Returns:
            Health metrics
        """
        cache_key = f"health:{package_name}"
        cached = self.cache.get(cache_key, cache_type="health", ttl_hours=168)
        
        if cached:
            return HealthMetrics(**cached)
        
        metrics = HealthMetrics(package_name=package_name)
        
        # Fetch data from various sources
        pypi_data = self._fetch_pypi_data(package_name)
        github_data = self._fetch_github_data(package_name, pypi_data)
        downloads = self._fetch_download_stats(package_name)
        
        # Populate metrics
        self._populate_maintenance_metrics(metrics, pypi_data)
        self._populate_popularity_metrics(metrics, downloads, github_data)
        self._populate_quality_metrics(metrics, pypi_data, github_data)
        
        # Calculate overall score
        self._calculate_overall_score(metrics)
        
        # Cache result
        self.cache.set(cache_key, metrics.__dict__, cache_type="health")
        
        return metrics
    
    def _fetch_pypi_data(self, package_name: str) -> dict[str, Any]:
        """Fetch package data from PyPI."""
        if not self.client:
            return {}
        
        try:
            response = self.client.get(f"https://pypi.org/pypi/{package_name}/json")
            
            if response.status_code == 200:
                return response.json()
                
        except Exception as e:
            logger.debug(f"Error fetching PyPI data for {package_name}: {e}")
        
        return {}
    
    def _fetch_github_data(self, package_name: str, pypi_data: dict) -> dict[str, Any]:
        """Fetch GitHub repository data."""
        if not self.client:
            return {}
        
        # Try to find GitHub URL
        github_url = None
        
        project_urls = pypi_data.get("info", {}).get("project_urls", {}) or {}
        for key, url in project_urls.items():
            if "github.com" in str(url).lower():
                github_url = url
                break
        
        if not github_url:
            home_page = pypi_data.get("info", {}).get("home_page", "")
            if "github.com" in home_page:
                github_url = home_page
        
        if not github_url:
            return {}
        
        # Extract owner/repo
        try:
            import re
            match = re.search(r"github\.com/([^/]+)/([^/]+)", github_url)
            if not match:
                return {}
            
            owner, repo = match.groups()
            repo = repo.rstrip(".git")
            
            # Fetch repo data
            response = self.client.get(
                f"https://api.github.com/repos/{owner}/{repo}",
                headers={"Accept": "application/vnd.github.v3+json"},
            )
            
            if response.status_code == 200:
                return response.json()
                
        except Exception as e:
            logger.debug(f"Error fetching GitHub data: {e}")
        
        return {}
    
    def _fetch_download_stats(self, package_name: str) -> int:
        """Fetch download statistics from PyPI Stats."""
        if not self.client:
            return 0
        
        try:
            # Use pypistats API
            response = self.client.get(
                f"https://pypistats.org/api/packages/{package_name}/recent",
                headers={"Accept": "application/json"},
            )
            
            if response.status_code == 200:
                data = response.json()
                return data.get("data", {}).get("last_month", 0)
                
        except Exception as e:
            logger.debug(f"Error fetching download stats: {e}")
        
        return 0
    
    def _populate_maintenance_metrics(self, metrics: HealthMetrics, pypi_data: dict) -> None:
        """Populate maintenance-related metrics."""
        releases = pypi_data.get("releases", {})
        
        if not releases:
            metrics.is_maintained = False
            return
        
        # Find most recent release
        release_dates = []
        
        for version, files in releases.items():
            for file_info in files:
                upload_time = file_info.get("upload_time_iso_8601")
                if upload_time:
                    try:
                        dt = datetime.fromisoformat(upload_time.replace("Z", "+00:00"))
                        release_dates.append(dt)
                    except ValueError:
                        continue
        
        if release_dates:
            release_dates.sort(reverse=True)
            latest = release_dates[0]
            
            metrics.last_release_date = latest.isoformat()
            
            now = datetime.now(timezone.utc)
            metrics.days_since_last_release = (now - latest).days
            
            # Calculate release frequency (releases per year)
            if len(release_dates) >= 2:
                oldest = release_dates[-1]
                years = max((latest - oldest).days / 365.25, 0.1)
                metrics.release_frequency = len(release_dates) / years
            
            # Determine if maintained (no release in 2+ years is concerning)
            metrics.is_maintained = metrics.days_since_last_release < 730
    
    def _populate_popularity_metrics(
        self,
        metrics: HealthMetrics,
        downloads: int,
        github_data: dict,
    ) -> None:
        """Populate popularity-related metrics."""
        metrics.downloads_last_month = downloads
        metrics.stars = github_data.get("stargazers_count", 0)
        metrics.forks = github_data.get("forks_count", 0)
    
    def _populate_quality_metrics(
        self,
        metrics: HealthMetrics,
        pypi_data: dict,
        github_data: dict,
    ) -> None:
        """Populate quality-related metrics."""
        info = pypi_data.get("info", {})
        
        # Check for type hints support
        classifiers = info.get("classifiers", [])
        for classifier in classifiers:
            if "Typing :: Typed" in classifier:
                metrics.has_type_hints = True
                break
        
        # Documentation URL
        project_urls = info.get("project_urls", {}) or {}
        for key in ["Documentation", "Docs", "docs"]:
            if key in project_urls:
                metrics.documentation_url = project_urls[key]
                break
        
        # GitHub-based quality signals
        if github_data:
            # Has CI if actions directory or common CI config
            # (simplified - would need to check repo contents)
            metrics.has_ci = github_data.get("has_wiki", False)  # Proxy metric
    
    def _calculate_overall_score(self, metrics: HealthMetrics) -> None:
        """Calculate overall health score."""
        scores = {}
        
        # Maintenance score (0-100)
        if metrics.is_maintained:
            if metrics.days_since_last_release < 0:
                maintenance = 50
            elif metrics.days_since_last_release < 90:
                maintenance = 100
            elif metrics.days_since_last_release < 180:
                maintenance = 80
            elif metrics.days_since_last_release < 365:
                maintenance = 60
            elif metrics.days_since_last_release < 730:
                maintenance = 40
            else:
                maintenance = 20
            
            # Bonus for high release frequency
            if metrics.release_frequency > 4:
                maintenance = min(100, maintenance + 10)
        else:
            maintenance = 10
        
        scores["maintenance"] = maintenance
        
        # Popularity score (0-100)
        downloads = metrics.downloads_last_month
        if downloads > 10_000_000:
            popularity = 100
        elif downloads > 1_000_000:
            popularity = 90
        elif downloads > 100_000:
            popularity = 70
        elif downloads > 10_000:
            popularity = 50
        elif downloads > 1_000:
            popularity = 30
        else:
            popularity = 10
        
        # Bonus for GitHub stars
        if metrics.stars > 10000:
            popularity = min(100, popularity + 20)
        elif metrics.stars > 1000:
            popularity = min(100, popularity + 10)
        
        scores["popularity"] = popularity
        
        # Quality score (0-100)
        quality = 40  # Base
        if metrics.has_type_hints:
            quality += 20
        if metrics.has_ci:
            quality += 20
        if metrics.documentation_url:
            quality += 20
        
        scores["quality"] = min(100, quality)
        
        # Security score (0-100)
        if metrics.known_vulnerabilities == 0:
            security = 100
        elif metrics.known_vulnerabilities < 3:
            security = 60
        elif metrics.known_vulnerabilities < 5:
            security = 40
        else:
            security = 20
        
        scores["security"] = security
        
        # Calculate weighted score
        total = sum(
            scores[category] * weight
            for category, weight in self.WEIGHTS.items()
        )
        
        metrics.health_score = round(total, 1)
        metrics.score_breakdown = scores
        
        # Assign grade
        if total >= 90:
            metrics.health_grade = "A"
        elif total >= 80:
            metrics.health_grade = "B"
        elif total >= 70:
            metrics.health_grade = "C"
        elif total >= 60:
            metrics.health_grade = "D"
        else:
            metrics.health_grade = "F"
    
    def generate_report(
        self,
        metrics_list: list[HealthMetrics],
    ) -> str:
        """Generate health report markdown.
        
        Args:
            metrics_list: List of health metrics
            
        Returns:
            Markdown report
        """
        lines = [
            "# Dependency Health Report",
            "",
            "| Package | Grade | Score | Maintenance | Popularity | Quality | Security |",
            "|---------|-------|-------|-------------|------------|---------|----------|",
        ]
        
        for m in sorted(metrics_list, key=lambda x: x.health_score, reverse=True):
            grade_emoji = {"A": "🟢", "B": "🟡", "C": "🟠", "D": "🔴", "F": "⛔"}.get(m.health_grade, "❓")
            
            lines.append(
                f"| {m.package_name} | {grade_emoji} {m.health_grade} | {m.health_score:.0f} | "
                f"{m.score_breakdown.get('maintenance', 0):.0f} | "
                f"{m.score_breakdown.get('popularity', 0):.0f} | "
                f"{m.score_breakdown.get('quality', 0):.0f} | "
                f"{m.score_breakdown.get('security', 0):.0f} |"
            )
        
        lines.extend([
            "",
            "## Score Breakdown",
            "",
            "- **Maintenance** (30%): Release frequency, days since last update",
            "- **Popularity** (20%): Downloads, GitHub stars",
            "- **Quality** (25%): Type hints, CI, documentation",
            "- **Security** (25%): Known vulnerabilities",
        ])
        
        return "\n".join(lines)
    
    def close(self) -> None:
        """Close HTTP client."""
        if self.client:
            self.client.close()
