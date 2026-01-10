"""Slack and Teams notification integration."""

import json
import logging
from dataclasses import dataclass

import httpx

from upgrade_analyzer.models import Severity, UpgradeReport

logger = logging.getLogger(__name__)


@dataclass
class NotificationConfig:
    """Notification configuration."""
    
    webhook_url: str
    channel: str | None = None
    mention_users: list[str] | None = None
    min_severity: Severity = Severity.HIGH


class SlackNotifier:
    """Send notifications to Slack."""
    
    def __init__(self, webhook_url: str) -> None:
        """Initialize Slack notifier.
        
        Args:
            webhook_url: Slack webhook URL
        """
        self.webhook_url = webhook_url
        self.client = httpx.Client(timeout=30.0)
    
    def send_report(
        self,
        reports: list[UpgradeReport],
        project_name: str = "Project",
        min_severity: Severity = Severity.HIGH,
    ) -> bool:
        """Send upgrade analysis report to Slack.
        
        Args:
            reports: List of upgrade reports
            project_name: Name of the project
            min_severity: Minimum severity to report
            
        Returns:
            True if notification sent successfully
        """
        # Filter by severity
        filtered = [
            r for r in reports
            if self._severity_gte(r.risk_score.severity, min_severity)
        ]
        
        if not filtered:
            logger.info("No reports meet severity threshold - skipping notification")
            return True
        
        # Build message
        message = self._build_message(filtered, project_name)
        
        try:
            response = self.client.post(
                self.webhook_url,
                json=message,
            )
            
            if response.status_code == 200:
                logger.info("Slack notification sent successfully")
                return True
            else:
                logger.error(f"Slack notification failed: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending Slack notification: {e}")
            return False
    
    def _build_message(self, reports: list[UpgradeReport], project_name: str) -> dict:
        """Build Slack message payload."""
        
        # Count by severity
        critical = sum(1 for r in reports if r.risk_score.severity == Severity.CRITICAL)
        high = sum(1 for r in reports if r.risk_score.severity == Severity.HIGH)
        
        # Determine overall status
        if critical > 0:
            status_emoji = "🔴"
            status_text = "CRITICAL"
            color = "#D32F2F"
        elif high > 0:
            status_emoji = "🟠"
            status_text = "HIGH RISK"
            color = "#FF9800"
        else:
            status_emoji = "🟡"
            status_text = "MEDIUM RISK"
            color = "#FFC107"
        
        # Build blocks
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{status_emoji} Upgrade Impact Analysis - {project_name}",
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Status:* {status_text}\n*Dependencies requiring attention:* {len(reports)}",
                }
            },
            {"type": "divider"},
        ]
        
        # Add top 5 risky packages
        for report in sorted(reports, key=lambda r: r.risk_score.total_score, reverse=True)[:5]:
            emoji = self._severity_emoji(report.risk_score.severity)
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"{emoji} *{report.dependency.name}*: "
                        f"`{report.dependency.current_version}` → `{report.dependency.target_version}`\n"
                        f"Risk Score: {report.risk_score.total_score:.0f}/100 | "
                        f"Breaking Changes: {len(report.breaking_changes)}"
                    ),
                }
            })
        
        return {
            "blocks": blocks,
            "attachments": [
                {
                    "color": color,
                    "text": f"Run `upgrade-analyzer analyze` for full details.",
                }
            ],
        }
    
    @staticmethod
    def _severity_gte(sev1: Severity, sev2: Severity) -> bool:
        """Check if sev1 >= sev2."""
        order = {Severity.LOW: 0, Severity.MEDIUM: 1, Severity.HIGH: 2, Severity.CRITICAL: 3}
        return order.get(sev1, 0) >= order.get(sev2, 0)
    
    @staticmethod
    def _severity_emoji(severity: Severity) -> str:
        """Get emoji for severity."""
        return {
            Severity.CRITICAL: "🔴",
            Severity.HIGH: "🟠",
            Severity.MEDIUM: "🟡",
            Severity.LOW: "🟢",
        }.get(severity, "⚪")
    
    def close(self) -> None:
        """Close HTTP client."""
        self.client.close()


class TeamsNotifier:
    """Send notifications to Microsoft Teams."""
    
    def __init__(self, webhook_url: str) -> None:
        """Initialize Teams notifier.
        
        Args:
            webhook_url: Teams webhook URL
        """
        self.webhook_url = webhook_url
        self.client = httpx.Client(timeout=30.0)
    
    def send_report(
        self,
        reports: list[UpgradeReport],
        project_name: str = "Project",
        min_severity: Severity = Severity.HIGH,
    ) -> bool:
        """Send upgrade analysis report to Teams.
        
        Args:
            reports: List of upgrade reports
            project_name: Name of the project
            min_severity: Minimum severity to report
            
        Returns:
            True if notification sent successfully
        """
        # Filter by severity
        order = {Severity.LOW: 0, Severity.MEDIUM: 1, Severity.HIGH: 2, Severity.CRITICAL: 3}
        filtered = [
            r for r in reports
            if order.get(r.risk_score.severity, 0) >= order.get(min_severity, 0)
        ]
        
        if not filtered:
            return True
        
        # Build adaptive card
        card = self._build_card(filtered, project_name)
        
        try:
            response = self.client.post(
                self.webhook_url,
                json=card,
            )
            
            return response.status_code in {200, 202}
                
        except Exception as e:
            logger.error(f"Error sending Teams notification: {e}")
            return False
    
    def _build_card(self, reports: list[UpgradeReport], project_name: str) -> dict:
        """Build Teams adaptive card payload."""
        
        critical = sum(1 for r in reports if r.risk_score.severity == Severity.CRITICAL)
        high = sum(1 for r in reports if r.risk_score.severity == Severity.HIGH)
        
        if critical > 0:
            theme_color = "D32F2F"
            status = "CRITICAL"
        elif high > 0:
            theme_color = "FF9800"
            status = "HIGH RISK"
        else:
            theme_color = "FFC107"
            status = "ATTENTION NEEDED"
        
        # Build facts
        facts = []
        for report in sorted(reports, key=lambda r: r.risk_score.total_score, reverse=True)[:5]:
            facts.append({
                "name": report.dependency.name,
                "value": f"{report.dependency.current_version} → {report.dependency.target_version} (Score: {report.risk_score.total_score:.0f})",
            })
        
        return {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "themeColor": theme_color,
            "summary": f"Upgrade Impact Analysis - {project_name}",
            "sections": [
                {
                    "activityTitle": f"📦 Upgrade Impact Analysis - {project_name}",
                    "activitySubtitle": f"Status: {status}",
                    "facts": facts,
                    "markdown": True,
                }
            ],
            "potentialAction": [
                {
                    "@type": "OpenUri",
                    "name": "View Details",
                    "targets": [
                        {"os": "default", "uri": "https://github.com"}
                    ]
                }
            ]
        }
    
    def close(self) -> None:
        """Close HTTP client."""
        self.client.close()
