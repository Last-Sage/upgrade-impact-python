"""Markdown report generator."""

from pathlib import Path

from upgrade_analyzer.models import UpgradeReport, Severity


class MarkdownReporter:
    """Generates Markdown reports."""
    
    def generate_report(self, reports: list[UpgradeReport], output_file: Path) -> None:
        """Generate comprehensive markdown report.
        
        Args:
            reports: List of upgrade reports
            output_file: Path to output file
        """
        # Sort by risk score
        sorted_reports = sorted(
            reports,
            key=lambda r: r.risk_score.total_score,
            reverse=True
        )
        
        # Build markdown content
        lines: list[str] = []
        
        # Header
        lines.append("# 📦 Upgrade Impact Analysis Report\n")
        lines.append(f"**Total Dependencies Analyzed:** {len(reports)}\n")
        
        # Summary statistics
        lines.append("## 📊 Summary\n")
        lines.append(self._generate_summary_table(sorted_reports))
        lines.append("")
        
        # Group by severity
        for severity in [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW]:
            severity_reports = [
                r for r in sorted_reports
                if r.risk_score.severity == severity
            ]
            
            if severity_reports:
                lines.append(f"## {self._get_severity_emoji(severity)} {severity.value.title()} Risk Upgrades\n")
                
                for report in severity_reports:
                    lines.append(self._generate_package_section(report))
                    lines.append("---\n")
        
        # Write to file
        with open(output_file, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
    
    def _generate_summary_table(self, reports: list[UpgradeReport]) -> str:
        """Generate summary table.
        
        Args:
            reports: List of reports
            
        Returns:
            Markdown table string
        """
        lines = [
            "| Package | Current | Target | Risk Score | Severity | Issues |",
            "|---------|---------|--------|------------|----------|--------|",
        ]
        
        for report in reports:
            emoji = self._get_severity_emoji(report.risk_score.severity)
            
            lines.append(
                f"| **{report.dependency.name}** "
                f"| {report.dependency.current_version} "
                f"| {report.dependency.target_version or 'latest'} "
                f"| {report.risk_score.total_score:.1f}/100 "
                f"| {emoji} {report.risk_score.severity.value} "
                f"| {len(report.breaking_changes)} |"
            )
        
        return "\n".join(lines)
    
    def _generate_package_section(self, report: UpgradeReport) -> str:
        """Generate detailed section for a package.
        
        Args:
            report: Upgrade report
            
        Returns:
            Markdown string
        """
        dep = report.dependency
        lines: list[str] = []
        
        # Package header
        lines.append(f"### {dep.name}: `{dep.current_version}` → `{dep.target_version}`\n")
        
        # Risk score
        emoji = self._get_severity_emoji(report.risk_score.severity)
        lines.append(f"**Risk Score:** {report.risk_score.total_score:.1f}/100 ({emoji} {report.risk_score.severity.value})\n")
        
        # Risk factors
        if report.risk_score.factors:
            lines.append("**Risk Factors:**\n")
            
            for factor in report.risk_score.factors:
                percentage = int((factor.score / 100) * 20)  # Convert to 20-char bar
                bar = "█" * percentage + "░" * (20 - percentage)
                
                lines.append(
                    f"- **{factor.name}**: `{bar}` {factor.score:.1f}/100 (weight: {factor.weight:.0%})"
                )
                lines.append(f"  - {factor.description}")
            
            lines.append("")
        
        # Breaking changes
        if report.breaking_changes:
            lines.append(f"**⚠️  Breaking Changes Detected:** {len(report.breaking_changes)}\n")
            
            for i, change in enumerate(report.breaking_changes[:10], 1):  # Limit to 10
                lines.append(f"{i}. **`{change.api_change.symbol_name}`** - {change.api_change.description}")
                lines.append(f"   - {change.impact_summary}")
                
                # Show affected files
                if change.affected_usage:
                    files = {u.file_path.name for u in change.affected_usage[:3]}
                    lines.append(f"   - Affected files: `{'`, `'.join(files)}`")
                
                lines.append("")
        
        # Recommendation
        if report.recommendation:
            rec = report.recommendation
            
            lines.append("**💡 Recommendation:**\n")
            lines.append(f"- {rec.rationale}")
            lines.append(f"- **Estimated Effort:** {rec.estimated_effort}")
            
            if len(rec.recommended_path) > 1:
                path_str = " → ".join(f"`{v}`" for v in rec.recommended_path)
                lines.append(f"- **Suggested Upgrade Path:** {path_str}")
            
            if rec.deprecation_warnings:
                lines.append("\n**Deprecation Warnings:**\n")
                for warning in rec.deprecation_warnings:
                    lines.append(f"- {warning}")
            
            lines.append("")
        
        # Usage summary
        if report.usage_summary:
            lines.append("**Usage Summary:**\n")
            
            if "total_files" in report.usage_summary:
                lines.append(f"- Files using this package: {report.usage_summary['total_files']}")
            
            if "unique_symbols" in report.usage_summary:
                lines.append(f"- Unique symbols imported: {report.usage_summary['unique_symbols']}")
            
            if "total_calls" in report.usage_summary:
                lines.append(f"- Total function calls: {report.usage_summary['total_calls']}")
            
            lines.append("")
        
        return "\n".join(lines)
    
    @staticmethod
    def _get_severity_emoji(severity: Severity) -> str:
        """Get emoji for severity.
        
        Args:
            severity: Severity level
            
        Returns:
            Emoji character
        """
        emojis = {
            Severity.CRITICAL: "🔴",
            Severity.HIGH: "🟠",
            Severity.MEDIUM: "🟡",
            Severity.LOW: "🟢",
        }
        
        return emojis.get(severity, "⚪")
