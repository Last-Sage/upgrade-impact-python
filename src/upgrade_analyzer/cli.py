"""CLI interface using Typer with all features."""

import logging
from enum import Enum
from pathlib import Path

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from upgrade_analyzer.analyzer import UpgradeAnalyzer
from upgrade_analyzer.config import get_config
from upgrade_analyzer.reporters.markdown import MarkdownReporter
from upgrade_analyzer.reporters.terminal import TerminalReporter
from upgrade_analyzer.reporters.json_formats import JSONReporter, SARIFReporter, JUnitReporter

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = typer.Typer(
    name="upgrade-analyzer",
    help="Intelligent dependency upgrade risk analyzer",
    add_completion=False,
)

console = Console()


class OutputFormat(str, Enum):
    """Output format options."""
    terminal = "terminal"
    json = "json"
    sarif = "sarif"
    junit = "junit"
    markdown = "markdown"


@app.command()
def analyze(
    project_path: Path = typer.Option(
        ".",
        "--project",
        "-p",
        help="Path to project root directory",
    ),
    requirements_file: Path = typer.Option(
        None,
        "--requirements",
        "-r",
        help="Path to requirements file (auto-detected if not specified)",
    ),
    output: Path = typer.Option(
        None,
        "--output",
        "-o",
        help="Path to output file (format determined by --format)",
    ),
    output_format: OutputFormat = typer.Option(
        OutputFormat.terminal,
        "--format",
        "-f",
        help="Output format (terminal, json, sarif, junit, markdown)",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Run analysis without checking for updates",
    ),
    offline: bool = typer.Option(
        False,
        "--offline",
        help="Use only cached data (no network requests)",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show detailed output for each package",
    ),
    no_color: bool = typer.Option(
        False,
        "--no-color",
        help="Disable colored output",
    ),
    security: bool = typer.Option(
        False,
        "--security",
        "-s",
        help="Include security vulnerability scanning",
    ),
    transitive: bool = typer.Option(
        False,
        "--transitive",
        "-t",
        help="Include transitive dependencies",
    ),
    include_dev: bool = typer.Option(
        False,
        "--include-dev",
        help="Include development dependencies",
    ),
    check_only: bool = typer.Option(
        False,
        "--check-only",
        help="Exit with code 1 if high/critical risk found (CI mode)",
    ),
    packages: list[str] = typer.Option(
        None,
        "--package",
        help="Analyze only specific packages (can be repeated)",
    ),
) -> None:
    """Analyze dependency upgrade risks for your project."""
    
    # Resolve project path
    project_path = project_path.resolve()
    
    # Validate inputs
    if not project_path.exists():
        console.print(f"[red]Error: Project path not found: {project_path}[/red]")
        raise typer.Exit(1)
    
    # Auto-detect requirements file if not specified
    if requirements_file is None:
        from upgrade_analyzer.parsers.base import DependencyParser
        
        detected = DependencyParser.auto_detect_in_directory(project_path)
        if detected:
            requirements_file = detected[0]
            console.print(f"[dim]Auto-detected: {requirements_file.name}[/dim]")
        else:
            console.print(f"[red]Error: No dependency file found in {project_path}[/red]")
            console.print("[dim]Looked for: pyproject.toml, requirements.txt, Pipfile, etc.[/dim]")
            raise typer.Exit(1)
    else:
        # Resolve requirements file path
        if not requirements_file.is_absolute():
            requirements_file = project_path / requirements_file
        
        if not requirements_file.exists():
            console.print(f"[red]Error: Requirements file not found: {requirements_file}[/red]")
            raise typer.Exit(1)
    
    # Show analysis start (only for terminal output)
    if output_format == OutputFormat.terminal:
        console.print(f"\n[bold cyan]🔍 Analyzing dependencies in {project_path}[/bold cyan]")
        console.print(f"[dim]Requirements file: {requirements_file.name}[/dim]")
        
        if offline:
            console.print("[yellow]⚠️  Running in offline mode (using cached data only)[/yellow]")
        
        if dry_run:
            console.print("[yellow]⚠️  Dry run mode (no updates will be checked)[/yellow]")
        
        if security:
            console.print("[cyan]🔒 Security scanning enabled[/cyan]")
    
    try:
        # Initialize analyzer
        analyzer = UpgradeAnalyzer(
            project_root=project_path,
            dependency_file=requirements_file,
            offline=offline or dry_run,
        )
        
        # Run analysis with progress bar
        if output_format == OutputFormat.terminal:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                console=console,
            ) as progress:
                task = progress.add_task("[green]Analyzing dependencies...", total=None)
                reports = analyzer.analyze()
                progress.update(task, completed=100)
        else:
            reports = analyzer.analyze()
        
        # Filter by specific packages if requested
        if packages:
            package_set = {p.lower() for p in packages}
            reports = [r for r in reports if r.dependency.name.lower() in package_set]
        
        # Run security scan if requested
        if security and reports:
            from upgrade_analyzer.intelligence.security import SecurityScanner
            
            scanner = SecurityScanner(offline=offline)
            
            if output_format == OutputFormat.terminal:
                console.print("\n[cyan]🔒 Scanning for vulnerabilities...[/cyan]")
            
            for report in reports:
                sec_report = scanner.scan_package(report.dependency)
                
                if sec_report.is_vulnerable:
                    report.usage_summary["vulnerabilities"] = len(sec_report.vulnerabilities)
                    report.usage_summary["security_note"] = (
                        f"{len(sec_report.vulnerabilities)} vulnerabilities found"
                    )
                    
                    if sec_report.upgrade_fixes_vulns:
                        report.usage_summary["upgrade_fixes_vulns"] = True
            
            scanner.close()
        
        # Clean up
        analyzer.close()
        
        if not reports:
            if output_format == OutputFormat.terminal:
                console.print("\n[yellow]ℹ️  No dependencies found to analyze[/yellow]")
            raise typer.Exit(0)
        
        # Generate output based on format
        if output_format == OutputFormat.terminal:
            terminal_reporter = TerminalReporter(color=not no_color)
            
            console.print("\n")
            terminal_reporter.print_statistics(reports)
            console.print("\n")
            terminal_reporter.print_summary_table(reports)
            
            # Print detailed reports if verbose
            if verbose:
                console.print("\n" + "="*80 + "\n")
                console.print("[bold]Detailed Analysis[/bold]\n")
                
                for report in reports:
                    terminal_reporter.print_detailed_report(report)
        
        elif output_format == OutputFormat.json:
            reporter = JSONReporter()
            json_output = reporter.generate_report(reports, output)
            
            if not output:
                console.print(json_output)
        
        elif output_format == OutputFormat.sarif:
            reporter = SARIFReporter()
            sarif_output = reporter.generate_report(reports, output)
            
            if not output:
                console.print(sarif_output)
        
        elif output_format == OutputFormat.junit:
            reporter = JUnitReporter()
            junit_output = reporter.generate_report(reports, output)
            
            if not output:
                console.print(junit_output)
        
        elif output_format == OutputFormat.markdown:
            if output:
                markdown_reporter = MarkdownReporter()
                markdown_reporter.generate_report(reports, output)
                console.print(f"[green]✅ Markdown report saved to: {output}[/green]")
            else:
                console.print("[red]Error: --output required for markdown format[/red]")
                raise typer.Exit(1)
        
        if output and output_format not in {OutputFormat.terminal, OutputFormat.markdown}:
            console.print(f"[green]✅ Report saved to: {output}[/green]")
        
        # Check if CI should fail
        config = get_config()
        fail_on_critical = config.get("ci.fail_on_critical", True)
        fail_on_high = config.get("ci.fail_on_high_risk", True)
        
        has_critical = any(r.risk_score.severity.value == "critical" for r in reports)
        has_high = any(r.risk_score.severity.value == "high" for r in reports)
        
        if check_only or output_format != OutputFormat.terminal:
            if has_critical and fail_on_critical:
                if output_format == OutputFormat.terminal:
                    console.print("\n[red]❌ CRITICAL risk upgrades detected. CI check failed.[/red]")
                raise typer.Exit(1)
            
            elif has_high and fail_on_high:
                if output_format == OutputFormat.terminal:
                    console.print("\n[yellow]⚠️  HIGH risk upgrades detected. CI check failed.[/yellow]")
                raise typer.Exit(1)
        
        if output_format == OutputFormat.terminal:
            console.print("\n[green]✅ Analysis complete![/green]")
        
        raise typer.Exit(0)
    
    except typer.Exit:
        raise
    except Exception as e:
        if verbose:
            logger.exception("Analysis failed")
        console.print(f"\n[red]Error during analysis: {str(e)}[/red]")
        raise typer.Exit(1)


@app.command()
def clear_cache() -> None:
    """Clear all cached data."""
    
    from upgrade_analyzer.cache import get_cache
    
    console.print("[yellow]Clearing cache...[/yellow]")
    
    cache = get_cache()
    cache.clear()
    
    console.print("[green]✅ Cache cleared successfully![/green]")


@app.command()
def version() -> None:
    """Show version information."""
    
    from upgrade_analyzer import __version__
    
    console.print(f"[bold]Upgrade Impact Analyzer[/bold] v{__version__}")
    console.print("\n[dim]Features:[/dim]")
    console.print("  • Usage-centric risk scoring")
    console.print("  • Multi-source changelog fetching")
    console.print("  • API diffing with griffe")
    console.print("  • Security scanning (pip-audit/OSV)")
    console.print("  • JSON/SARIF/JUnit output formats")


@app.command()
def detect(
    project_path: Path = typer.Option(
        ".",
        "--project",
        "-p",
        help="Path to project directory",
    ),
) -> None:
    """Detect dependency files in a project."""
    
    from upgrade_analyzer.parsers.base import DependencyParser
    
    project_path = project_path.resolve()
    
    if not project_path.exists():
        console.print(f"[red]Error: Path not found: {project_path}[/red]")
        raise typer.Exit(1)
    
    detected = DependencyParser.auto_detect_in_directory(project_path)
    
    if detected:
        console.print(f"\n[bold]Detected dependency files in {project_path}:[/bold]\n")
        for file_path in detected:
            parser_class = DependencyParser.detect_parser(file_path)
            parser_name = parser_class.__name__ if parser_class else "Unknown"
            console.print(f"  📄 {file_path.name} ({parser_name})")
    else:
        console.print(f"\n[yellow]No dependency files found in {project_path}[/yellow]")


@app.command()
def scan_security(
    project_path: Path = typer.Option(
        ".",
        "--project",
        "-p",
        help="Path to project root directory",
    ),
    requirements_file: Path = typer.Option(
        None,
        "--requirements",
        "-r",
        help="Path to requirements file",
    ),
    output: Path = typer.Option(
        None,
        "--output",
        "-o",
        help="Path to output JSON file",
    ),
) -> None:
    """Scan dependencies for security vulnerabilities."""
    
    from upgrade_analyzer.parsers.base import DependencyParser
    from upgrade_analyzer.intelligence.security import SecurityScanner
    import json
    
    project_path = project_path.resolve()
    
    # Auto-detect requirements file
    if requirements_file is None:
        detected = DependencyParser.auto_detect_in_directory(project_path)
        if detected:
            requirements_file = detected[0]
        else:
            console.print("[red]Error: No dependency file found[/red]")
            raise typer.Exit(1)
    else:
        if not requirements_file.is_absolute():
            requirements_file = project_path / requirements_file
    
    # Parse dependencies
    parser_class = DependencyParser.detect_parser(requirements_file)
    if not parser_class:
        console.print(f"[red]Error: Unsupported file: {requirements_file}[/red]")
        raise typer.Exit(1)
    
    parser = parser_class(requirements_file)
    dependencies = parser.parse()
    
    console.print(f"\n[bold cyan]🔒 Scanning {len(dependencies)} dependencies...[/bold cyan]\n")
    
    scanner = SecurityScanner()
    results = []
    vulnerable_count = 0
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("[green]Scanning...", total=len(dependencies))
        
        for dep in dependencies:
            report = scanner.scan_package(dep, check_target=False)
            
            if report.is_vulnerable:
                vulnerable_count += 1
                
                for vuln in report.vulnerabilities:
                    results.append({
                        "package": dep.name,
                        "version": dep.current_version,
                        "vulnerability": vuln.id,
                        "severity": vuln.severity,
                        "summary": vuln.summary,
                        "url": vuln.url,
                    })
                    
                    console.print(
                        f"  [red]✗[/red] {dep.name}=={dep.current_version}: "
                        f"[bold]{vuln.id}[/bold] ({vuln.severity})"
                    )
            
            progress.advance(task)
    
    scanner.close()
    
    console.print(f"\n[bold]Summary:[/bold] {vulnerable_count} vulnerable packages found")
    
    if output and results:
        output.write_text(json.dumps(results, indent=2), encoding="utf-8")
        console.print(f"[green]Results saved to: {output}[/green]")
    
    if vulnerable_count > 0:
        raise typer.Exit(1)


@app.command()
def sbom(
    project_path: Path = typer.Option(
        ".",
        "--project",
        "-p",
        help="Path to project directory",
    ),
    output: Path = typer.Option(
        None,
        "--output",
        "-o",
        help="Path to output file",
    ),
    sbom_format: str = typer.Option(
        "cyclonedx",
        "--format",
        "-f",
        help="SBOM format: cyclonedx, spdx",
    ),
) -> None:
    """Generate Software Bill of Materials (SBOM)."""
    
    from upgrade_analyzer.parsers.base import DependencyParser
    from upgrade_analyzer.sbom import SBOMGenerator
    
    project_path = project_path.resolve()
    
    # Auto-detect and parse dependencies
    detected = DependencyParser.auto_detect_in_directory(project_path)
    if not detected:
        console.print("[red]Error: No dependency file found[/red]")
        raise typer.Exit(1)
    
    parser_class = DependencyParser.detect_parser(detected[0])
    parser = parser_class(detected[0])
    dependencies = parser.parse()
    
    generator = SBOMGenerator(
        project_name=project_path.name,
        project_version="0.0.0",
    )
    
    if sbom_format.lower() == "spdx":
        sbom_str = generator.generate_spdx(dependencies, output)
    else:
        sbom_str = generator.generate_cyclonedx(dependencies, output)
    
    if output:
        console.print(f"[green]✅ SBOM saved to: {output}[/green]")
    else:
        console.print(sbom_str)


@app.command()
def health(
    project_path: Path = typer.Option(
        ".",
        "--project",
        "-p",
        help="Path to project directory",
    ),
    output: Path = typer.Option(
        None,
        "--output",
        "-o",
        help="Path to output markdown file",
    ),
) -> None:
    """Analyze dependency health scores."""
    
    from upgrade_analyzer.parsers.base import DependencyParser
    from upgrade_analyzer.health import HealthScorer
    
    project_path = project_path.resolve()
    
    # Parse dependencies
    detected = DependencyParser.auto_detect_in_directory(project_path)
    if not detected:
        console.print("[red]Error: No dependency file found[/red]")
        raise typer.Exit(1)
    
    parser_class = DependencyParser.detect_parser(detected[0])
    parser = parser_class(detected[0])
    dependencies = parser.parse()
    
    console.print(f"\n[bold cyan]📊 Calculating health scores for {len(dependencies)} packages...[/bold cyan]\n")
    
    scorer = HealthScorer()
    metrics_list = []
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("[green]Scoring...", total=len(dependencies))
        
        for dep in dependencies:
            metrics = scorer.calculate_health(dep.name)
            metrics_list.append(metrics)
            
            # Show result
            grade_emoji = {"A": "🟢", "B": "🟡", "C": "🟠", "D": "🔴", "F": "⛔"}.get(metrics.health_grade, "❓")
            console.print(f"  {grade_emoji} {dep.name}: {metrics.health_grade} ({metrics.health_score:.0f}/100)")
            
            progress.advance(task)
    
    scorer.close()
    
    # Generate report
    report = scorer.generate_report(metrics_list)
    
    if output:
        output.write_text(report, encoding="utf-8")
        console.print(f"\n[green]✅ Health report saved to: {output}[/green]")


@app.command()
def licenses(
    project_path: Path = typer.Option(
        ".",
        "--project",
        "-p",
        help="Path to project directory",
    ),
    output: Path = typer.Option(
        None,
        "--output",
        "-o",
        help="Path to output markdown file",
    ),
    deny: list[str] = typer.Option(
        None,
        "--deny",
        help="Denied licenses (can be repeated)",
    ),
) -> None:
    """Audit dependency licenses."""
    
    from upgrade_analyzer.parsers.base import DependencyParser
    from upgrade_analyzer.sbom import LicenseAuditor
    
    project_path = project_path.resolve()
    
    # Parse dependencies
    detected = DependencyParser.auto_detect_in_directory(project_path)
    if not detected:
        console.print("[red]Error: No dependency file found[/red]")
        raise typer.Exit(1)
    
    parser_class = DependencyParser.detect_parser(detected[0])
    parser = parser_class(detected[0])
    dependencies = parser.parse()
    
    console.print(f"\n[bold cyan]📜 Auditing licenses for {len(dependencies)} packages...[/bold cyan]\n")
    
    auditor = LicenseAuditor()
    
    denied_set = {d.upper() for d in (deny or [])}
    
    result = auditor.audit_licenses(dependencies, denied_licenses=denied_set or None)
    report = auditor.generate_report(result, output)
    
    auditor.close()
    
    # Display summary
    console.print(f"[bold]Summary:[/bold]")
    console.print(f"  Permissive: {result['summary']['permissive']}")
    console.print(f"  Copyleft: {result['summary']['copyleft']}")
    console.print(f"  Unknown: {result['summary']['unknown']}")
    
    if result['violations']:
        console.print(f"\n[red]❌ {len(result['violations'])} license violations found![/red]")
        for v in result['violations']:
            console.print(f"  • {v['package']}: {v['license']} - {v['reason']}")
        raise typer.Exit(1)
    
    if result['warnings']:
        console.print(f"\n[yellow]⚠️ {len(result['warnings'])} warnings[/yellow]")
    
    if output:
        console.print(f"\n[green]✅ License report saved to: {output}[/green]")


@app.command()
def monorepo(
    root_path: Path = typer.Option(
        ".",
        "--root",
        "-r",
        help="Path to monorepo root",
    ),
    output: Path = typer.Option(
        None,
        "--output",
        "-o",
        help="Path to output markdown file",
    ),
    offline: bool = typer.Option(
        False,
        "--offline",
        help="Use only cached data",
    ),
) -> None:
    """Analyze dependencies across a monorepo."""
    
    from upgrade_analyzer.enterprise import MonorepoAnalyzer
    
    root_path = root_path.resolve()
    
    console.print(f"\n[bold cyan]🏢 Analyzing monorepo at {root_path}...[/bold cyan]\n")
    
    analyzer = MonorepoAnalyzer(root_path)
    projects = analyzer.discover_projects()
    
    if not projects:
        console.print("[yellow]No projects found[/yellow]")
        raise typer.Exit(0)
    
    console.print(f"[bold]Discovered {len(projects)} projects:[/bold]")
    for project in projects:
        console.print(f"  📁 {project['name']} ({project['relative_path']})")
    
    console.print("\n[bold]Analyzing...[/bold]\n")
    
    results = analyzer.analyze_all(offline=offline)
    
    # Show summary
    for project_name, reports in results.items():
        critical = sum(1 for r in reports if r.risk_score.severity.value == "critical")
        high = sum(1 for r in reports if r.risk_score.severity.value == "high")
        
        if critical:
            console.print(f"  🔴 {project_name}: {len(reports)} deps, {critical} critical")
        elif high:
            console.print(f"  🟠 {project_name}: {len(reports)} deps, {high} high")
        else:
            console.print(f"  🟢 {project_name}: {len(reports)} deps")
    
    # Shared dependencies
    shared = analyzer.find_shared_dependencies()
    if shared:
        console.print(f"\n[bold]Shared dependencies ({len(shared)}):[/bold]")
        for pkg, used_by in list(shared.items())[:10]:
            console.print(f"  • {pkg}: used by {len(used_by)} projects")
    
    # Generate report
    report = analyzer.generate_report(results)
    
    if output:
        output.write_text(report, encoding="utf-8")
        console.print(f"\n[green]✅ Monorepo report saved to: {output}[/green]")


@app.command(name="ai-analyze")
def ai_analyze(
    project_path: Path = typer.Option(
        ".",
        "--project",
        "-p",
        help="Path to project directory",
    ),
    package: str = typer.Option(
        ...,
        "--package",
        help="Package to analyze",
    ),
    from_version: str = typer.Option(
        ...,
        "--from",
        help="Current version",
    ),
    to_version: str = typer.Option(
        ...,
        "--to",
        help="Target version",
    ),
) -> None:
    """AI-powered changelog analysis (requires OPENAI_API_KEY or ANTHROPIC_API_KEY)."""
    
    from upgrade_analyzer.intelligence.llm_analyzer import LLMChangelogAnalyzer
    from upgrade_analyzer.intelligence.changelog_fetcher import ChangelogFetcher
    
    console.print(f"\n[bold cyan]🤖 AI Analysis: {package} {from_version} → {to_version}[/bold cyan]\n")
    
    # Check if LLM is available
    llm = LLMChangelogAnalyzer()
    
    if not llm.is_available:
        console.print("[red]Error: No LLM API key found[/red]")
        console.print("[dim]Set OPENAI_API_KEY or ANTHROPIC_API_KEY environment variable[/dim]")
        raise typer.Exit(1)
    
    console.print(f"[dim]Using provider: {llm.provider}[/dim]\n")
    
    # Fetch changelog
    fetcher = ChangelogFetcher()
    entries = fetcher.fetch_changelog(package, from_version, to_version)
    fetcher.close()
    
    if not entries:
        console.print("[yellow]No changelog entries found[/yellow]")
        raise typer.Exit(0)
    
    console.print("[bold]Analyzing with AI...[/bold]\n")
    
    result = llm.analyze_changelog(package, from_version, to_version, entries)
    llm.close()
    
    if not result:
        console.print("[red]AI analysis failed[/red]")
        raise typer.Exit(1)
    
    # Display results
    console.print(f"[bold]📝 Summary[/bold]\n{result.summary}\n")
    
    if result.breaking_changes:
        console.print("[bold]💥 Breaking Changes[/bold]")
        for bc in result.breaking_changes:
            console.print(f"  • {bc}")
        console.print()
    
    if result.migration_steps:
        console.print("[bold]📋 Migration Steps[/bold]")
        for i, step in enumerate(result.migration_steps, 1):
            console.print(f"  {i}. {step}")
        console.print()
    
    console.print(f"[bold]⚠️ Risk Assessment[/bold]: {result.risk_assessment}")
    console.print(f"[bold]⏱️ Estimated Effort[/bold]: {result.estimated_effort}")
    
    if result.affected_areas:
        console.print(f"[bold]📍 Affected Areas[/bold]: {', '.join(result.affected_areas)}")


@app.command(name="init-policies")
def init_policies(
    output: Path = typer.Option(
        ".upgrade-policies.toml",
        "--output",
        "-o",
        help="Path to save example policies file",
    ),
) -> None:
    """Create example risk policies configuration file."""
    
    from upgrade_analyzer.enterprise import create_example_policies_file
    
    output = Path(output)
    create_example_policies_file(output)
    
    console.print(f"[green]✅ Created example policies file: {output}[/green]")
    console.print("[dim]Edit this file to customize your risk policies[/dim]")


@app.command()
def conflicts(
    project_path: Path = typer.Option(
        ".",
        "--project",
        "-p",
        help="Path to project directory",
    ),
    output: Path = typer.Option(
        None,
        "--output",
        "-o",
        help="Path to output markdown file",
    ),
) -> None:
    """Detect dependency conflicts before upgrading."""
    
    from upgrade_analyzer.parsers.base import DependencyParser
    from upgrade_analyzer.conflict_detector import ConflictDetector
    from upgrade_analyzer.resolver import DependencyResolver
    
    project_path = project_path.resolve()
    
    # Auto-detect and parse dependencies
    detected = DependencyParser.auto_detect_in_directory(project_path)
    if not detected:
        console.print("[red]Error: No dependency file found[/red]")
        raise typer.Exit(1)
    
    parser_class = DependencyParser.detect_parser(detected[0])
    parser = parser_class(detected[0])
    dependencies = parser.parse()
    
    console.print(f"\n[bold cyan]🔍 Checking conflicts for {len(dependencies)} packages...[/bold cyan]\n")
    
    detector = ConflictDetector()
    resolver = DependencyResolver()
    
    # Get upgrade targets
    upgrades = []
    for dep in dependencies:
        target = resolver._fetch_latest_version(dep.name)
        if target and target != dep.current_version:
            upgrades.append((dep.name, dep.current_version, target))
    
    if not upgrades:
        console.print("[green]✅ All packages are up to date![/green]")
        raise typer.Exit(0)
    
    console.print(f"[dim]Analyzing {len(upgrades)} potential upgrades...[/dim]\n")
    
    # Detect conflicts
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("[green]Checking...", total=len(upgrades))
        
        reports = []
        for package, from_ver, to_ver in upgrades:
            report = detector.detect_conflicts(package, from_ver, to_ver, dependencies)
            reports.append(report)
            
            if report.conflicts:
                console.print(f"  [red]✗[/red] {package}: {len(report.conflicts)} conflict(s)")
            else:
                console.print(f"  [green]✓[/green] {package}: compatible")
            
            progress.advance(task)
    
    detector.close()
    resolver.close()
    
    # Summary
    total_conflicts = sum(len(r.conflicts) for r in reports)
    
    if total_conflicts == 0:
        console.print(f"\n[green]✅ No conflicts detected! All upgrades are safe.[/green]")
    else:
        console.print(f"\n[red]⚠️ {total_conflicts} conflicts found![/red]")
        
        for report in reports:
            if report.conflicts:
                console.print(f"\n[bold]{report.package}[/bold] ({report.from_version} → {report.to_version}):")
                for conflict in report.conflicts:
                    console.print(f"  • {conflict.reason}")
    
    # Generate report
    markdown_report = detector.generate_conflict_report(reports)
    
    if output:
        output.write_text(markdown_report, encoding="utf-8")
        console.print(f"\n[green]📄 Report saved to: {output}[/green]")
    
    if total_conflicts > 0:
        raise typer.Exit(1)


if __name__ == "__main__":
    app()

