"""Terminal reporter using Rich library."""

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

from upgrade_analyzer.models import Severity, UpgradeReport


class TerminalReporter:
    """Generates terminal output using Rich."""
    
    def __init__(self, color: bool = True) -> None:
        """Initialize terminal reporter.
        
        Args:
            color: If True, use colored output
        """
        self.console = Console(color_system="auto" if color else None)
    
    def print_summary_table(self, reports: list[UpgradeReport]) -> None:
        """Print summary table of all dependency upgrades.
        
        Args:
            reports: List of upgrade reports
        """
        # Sort by risk score (descending)
        sorted_reports = sorted(
            reports,
            key=lambda r: r.risk_score.total_score,
            reverse=True
        )
        
        # Create table
        table = Table(
            title="📦 Dependency Upgrade Analysis",
            show_header=True,
            header_style="bold cyan",
        )
        
        table.add_column("Package", style="bold")
        table.add_column("Current", justify="center")
        table.add_column("Target", justify="center")
        table.add_column("Risk Score", justify="right")
        table.add_column("Severity", justify="center")
        table.add_column("Issues", justify="right")
        
        # Add rows
        for report in sorted_reports:
            # Get severity color
            severity_color = self._get_severity_color(report.risk_score.severity)
            severity_icon = self._get_severity_icon(report.risk_score.severity)
            
            # Format risk score
            risk_text = f"{report.risk_score.total_score:.1f}"
            
            # Count issues
            issue_count = len(report.breaking_changes)
            
            table.add_row(
                report.dependency.name,
                report.dependency.current_version,
                report.dependency.target_version or "latest",
                risk_text,
                f"[{severity_color}]{severity_icon} {report.risk_score.severity.value}[/{severity_color}]",
                str(issue_count),
            )
        
        self.console.print(table)
    
    def print_detailed_report(self, report: UpgradeReport) -> None:
        """Print detailed report for a single dependency.
        
        Args:
            report: Upgrade report
        """
        dep = report.dependency
        
        # Header
        title = f"📦 {dep.name}: {dep.current_version} → {dep.target_version}"
        self.console.print(f"\n[bold]{title}[/bold]")
        
        # Risk score panel
        severity_color = self._get_severity_color(report.risk_score.severity)
        severity_icon = self._get_severity_icon(report.risk_score.severity)
        
        risk_panel = Panel(
            f"[{severity_color}]{severity_icon} {report.risk_score.severity.value.upper()}[/{severity_color}]\n"
            f"Risk Score: {report.risk_score.total_score:.1f}/100",
            title="Risk Assessment",
            border_style=severity_color,
        )
        self.console.print(risk_panel)
        
        # Risk factors
        if report.risk_score.factors:
            self.console.print("\n[bold]Risk Factors:[/bold]")
            
            for factor in report.risk_score.factors:
                bar_length = int(factor.score / 5)  # Scale to 0-20
                bar = "█" * bar_length + "░" * (20 - bar_length)
                
                self.console.print(
                    f"  • {factor.name}: [{bar}] {factor.score:.1f} "
                    f"(weight: {factor.weight:.1%})"
                )
                self.console.print(f"    {factor.description}", style="dim")
        
        # Breaking changes
        if report.breaking_changes:
            self.console.print("\n[bold red]⚠️  Breaking Changes:[/bold red]")
            
            for change in report.breaking_changes[:5]:  # Limit to 5
                self.console.print(f"\n  • {change.api_change.symbol_name}", style="bold")
                self.console.print(f"    {change.api_change.description}", style="dim")
                self.console.print(f"    {change.impact_summary}", style="yellow")
        
        # Recommendation
        if report.recommendation:
            rec = report.recommendation
            
            self.console.print("\n[bold]💡 Recommendation:[/bold]")
            self.console.print(f"  {rec.rationale}")
            self.console.print(f"  Estimated Effort: [bold]{rec.estimated_effort}[/bold]")
            
            if len(rec.recommended_path) > 1:
                path_str = " → ".join(rec.recommended_path)
                self.console.print(f"  Suggested Path: {path_str}", style="cyan")
        
        self.console.print("")  # Blank line
    
    def print_statistics(self, reports: list[UpgradeReport]) -> None:
        """Print overall statistics.
        
        Args:
            reports: List of reports
        """
        total = len(reports)
        
        # Count by severity
        critical = sum(1 for r in reports if r.risk_score.severity == Severity.CRITICAL)
        high = sum(1 for r in reports if r.risk_score.severity == Severity.HIGH)
        medium = sum(1 for r in reports if r.risk_score.severity == Severity.MEDIUM)
        low = sum(1 for r in reports if r.risk_score.severity == Severity.LOW)
        
        # Create statistics text
        stats = Text()
        stats.append("📊 Summary: ", style="bold")
        stats.append(f"{total} dependencies analyzed | ")
        
        if critical > 0:
            stats.append(f"🔴 {critical} Critical ", style="bold red")
        if high > 0:
            stats.append(f"🟠 {high} High ", style="bold yellow")
        if medium > 0:
            stats.append(f"🟡 {medium} Medium ", style="bold blue")
        if low > 0:
            stats.append(f"🟢 {low} Low ", style="bold green")
        
        self.console.print(Panel(stats, border_style="blue"))
    
    @staticmethod
    def _get_severity_color(severity: Severity) -> str:
        """Get color for severity level.
        
        Args:
            severity: Severity level
            
        Returns:
            Color name
        """
        colors = {
            Severity.CRITICAL: "red",
            Severity.HIGH: "yellow",
            Severity.MEDIUM: "blue",
            Severity.LOW: "green",
        }
        
        return colors.get(severity, "white")
    
    @staticmethod
    def _get_severity_icon(severity: Severity) -> str:
        """Get icon for severity level.
        
        Args:
            severity: Severity level
            
        Returns:
            Icon character
        """
        icons = {
            Severity.CRITICAL: "🔴",
            Severity.HIGH: "🟠",
            Severity.MEDIUM: "🟡",
            Severity.LOW: "🟢",
        }
        
        return icons.get(severity, "⚪")
