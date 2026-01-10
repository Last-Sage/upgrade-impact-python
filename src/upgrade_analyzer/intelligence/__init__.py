"""Intelligence module exports."""

from upgrade_analyzer.intelligence.api_differ import APIDiffer
from upgrade_analyzer.intelligence.changelog_fetcher import ChangelogFetcher
from upgrade_analyzer.intelligence.changelog_nlp import ChangelogAnalyzer
from upgrade_analyzer.intelligence.pypi_client import PyPIClient
from upgrade_analyzer.intelligence.risk_scorer import RiskScorer
from upgrade_analyzer.intelligence.security import SecurityScanner, Vulnerability, SecurityReport

__all__ = [
    "APIDiffer",
    "ChangelogFetcher",
    "ChangelogAnalyzer",
    "PyPIClient",
    "RiskScorer",
    "SecurityScanner",
    "Vulnerability",
    "SecurityReport",
]
