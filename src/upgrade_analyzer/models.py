"""Core data models for the Upgrade Impact Analyzer."""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class Severity(Enum):
    """Risk severity levels."""
    
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ChangeType(Enum):
    """Types of API changes."""
    
    REMOVED = "removed"
    MODIFIED = "modified"
    DEPRECATED = "deprecated"
    ADDED = "added"


@dataclass
class Dependency:
    """Represents a package dependency."""
    
    name: str
    current_version: str
    target_version: str | None = None
    source_file: Path | None = None
    is_transitive: bool = False
    extras: list[str] = field(default_factory=list)
    
    def __str__(self) -> str:
        """String representation."""
        return f"{self.name}=={self.current_version}"


@dataclass
class UsageNode:
    """Represents usage of a symbol from a package."""
    
    package_name: str
    symbol_path: str  # e.g., "requests.get" or "requests.auth.HTTPBasicAuth"
    file_path: Path
    line_numbers: list[int] = field(default_factory=list)
    call_count: int = 0
    
    def __str__(self) -> str:
        """String representation."""
        return f"{self.symbol_path} in {self.file_path.name} (L{self.line_numbers})"


@dataclass
class CallSite:
    """Represents a specific call to a function with arguments."""
    
    symbol: str
    file_path: Path
    line_number: int
    arguments: dict[str, Any] = field(default_factory=dict)
    positional_args: list[str] = field(default_factory=list)
    keyword_args: dict[str, str] = field(default_factory=dict)


@dataclass
class ChangelogEntry:
    """Represents an entry in a changelog."""
    
    version: str
    release_date: str | None = None
    content: str = ""
    severity_keywords: list[tuple[str, Severity]] = field(default_factory=list)
    
    @property
    def max_severity(self) -> Severity:
        """Get the maximum severity from keywords."""
        if not self.severity_keywords:
            return Severity.LOW
        
        severity_order = {
            Severity.LOW: 0,
            Severity.MEDIUM: 1,
            Severity.HIGH: 2,
            Severity.CRITICAL: 3,
        }
        
        return max(
            (sev for _, sev in self.severity_keywords),
            key=lambda s: severity_order[s],
            default=Severity.LOW
        )


@dataclass
class APIChange:
    """Represents a change in API surface."""
    
    symbol_name: str
    change_type: ChangeType
    old_signature: str | None = None
    new_signature: str | None = None
    description: str = ""
    
    @property
    def is_breaking(self) -> bool:
        """Check if this is likely a breaking change."""
        return self.change_type in {ChangeType.REMOVED, ChangeType.MODIFIED}


@dataclass
class RiskFactor:
    """Individual contributing factor to risk score."""
    
    name: str
    score: float  # 0-100
    weight: float  # 0-1
    description: str


@dataclass
class RiskScore:
    """Overall risk score for an upgrade."""
    
    total_score: float  # 0-100
    severity: Severity
    factors: list[RiskFactor] = field(default_factory=list)
    
    @property
    def weighted_score(self) -> float:
        """Calculate weighted score from factors."""
        if not self.factors:
            return self.total_score
        
        return sum(f.score * f.weight for f in self.factors)
    
    @staticmethod
    def from_score(score: float) -> Severity:
        """Determine severity from numeric score."""
        if score >= 80:
            return Severity.CRITICAL
        elif score >= 60:
            return Severity.HIGH
        elif score >= 30:
            return Severity.MEDIUM
        else:
            return Severity.LOW


@dataclass
class BreakingChange:
    """Represents a detected breaking change in user code."""
    
    dependency: Dependency
    api_change: APIChange
    affected_usage: list[UsageNode]
    recommendation: str = ""
    
    @property
    def impact_summary(self) -> str:
        """Get a summary of the impact."""
        file_count = len({u.file_path for u in self.affected_usage})
        usage_count = sum(u.call_count for u in self.affected_usage)
        
        return f"Affects {usage_count} usage(s) across {file_count} file(s)"


@dataclass
class UpgradeRecommendation:
    """Recommendation for upgrading a dependency."""
    
    dependency: Dependency
    recommended_path: list[str]  # List of versions to upgrade through
    rationale: str
    estimated_effort: str  # "Low", "Medium", "High"
    deprecation_warnings: list[str] = field(default_factory=list)


@dataclass
class UpgradeReport:
    """Complete analysis report for a dependency upgrade."""
    
    dependency: Dependency
    risk_score: RiskScore
    api_changes: list[APIChange]
    breaking_changes: list[BreakingChange]
    changelog_entries: list[ChangelogEntry]
    recommendation: UpgradeRecommendation | None = None
    usage_summary: dict[str, int] = field(default_factory=dict)
    
    @property
    def is_safe(self) -> bool:
        """Check if upgrade is considered safe."""
        return self.risk_score.severity in {Severity.LOW, Severity.MEDIUM}
