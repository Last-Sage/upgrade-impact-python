# � Upgrade Impact Analyzer

> **Intelligent dependency upgrade risk analysis with usage-centric scoring**

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

Upgrade Impact Analyzer goes beyond simple SemVer rules. It analyzes **your actual code usage** against library changelogs, API changes, and known vulnerabilities to tell you exactly how risky an upgrade really is.

## ✨ Key Features

| Feature                   | Description                                                |
| ------------------------- | ---------------------------------------------------------- |
| **Usage-Centric Scoring** | Risk scored by actual code usage, not just version numbers |
| **API Diffing**           | Detects removed/modified/deprecated symbols using griffe   |
| **Security Scanning**     | CVE detection via pip-audit and OSV.dev                    |
| **Multi-Format Output**   | Terminal, JSON, SARIF, JUnit XML, Markdown                 |
| **CI/CD Integration**     | GitHub Actions, pre-commit hooks                           |
| **Lock File Support**     | poetry.lock, Pipfile.lock, conda environment.yml           |

## 🚀 Quick Start

```bash
# Install
pip install upgrade-impact-analyzer

# Analyze your project
upgrade-analyzer analyze

# With security scanning
upgrade-analyzer analyze --security

# JSON output for CI
upgrade-analyzer analyze --format json --output report.json
```

## � Installation

```bash
# Basic installation
pip install upgrade-impact-analyzer

# With security scanning support
pip install upgrade-impact-analyzer[security]

# With all optional features
pip install upgrade-impact-analyzer[all]
```

## � Usage

### Basic Analysis

```bash
# Auto-detect dependency file
upgrade-analyzer analyze

# Specify project path
upgrade-analyzer analyze --project /path/to/project

# Specify requirements file
upgrade-analyzer analyze --requirements requirements-prod.txt
```

### Output Formats

```bash
# Terminal (default) - colorful table output
upgrade-analyzer analyze

# JSON - machine-readable
upgrade-analyzer analyze --format json --output report.json

# SARIF - GitHub Security tab integration
upgrade-analyzer analyze --format sarif --output results.sarif

# JUnit XML - CI test reporting
upgrade-analyzer analyze --format junit --output junit.xml

# Markdown - documentation
upgrade-analyzer analyze --format markdown --output report.md
```

### Security Scanning

```bash
# Scan for vulnerabilities
upgrade-analyzer scan-security

# Include in analysis
upgrade-analyzer analyze --security

# Save security report
upgrade-analyzer scan-security --output vulnerabilities.json
```

### CI Mode

```bash
# Exit with code 1 if high/critical risks found
upgrade-analyzer analyze --check-only

# Filter specific packages
upgrade-analyzer analyze --package requests --package flask
```

### Other Commands

```bash
# Detect dependency files in project
upgrade-analyzer detect

# Clear cache
upgrade-analyzer clear-cache

# Show version
upgrade-analyzer version
```

## 🔧 Configuration

### Environment Variables

| Variable       | Description                             |
| -------------- | --------------------------------------- |
| `GITHUB_TOKEN` | GitHub API token for higher rate limits |
| `GH_TOKEN`     | Alternative GitHub token variable       |

### Config File (`.upgrade-analyzer.toml`)

```toml
[risk_scoring]
semver_weight = 0.3
usage_weight = 0.5
changelog_weight = 0.2

[risk_scoring.thresholds]
critical = 80
high = 60
medium = 30

[ci]
fail_on_critical = true
fail_on_high_risk = true

[analysis]
exclude_patterns = ["**/venv/**", "**/.venv/**", "**/node_modules/**"]
```

### Ignore File (`.upgradeignore`)

```
# Packages to skip
django  # Framework - manual upgrades
celery  # Pin to specific version
```

## � GitHub Actions

Add to `.github/workflows/upgrade-analysis.yml`:

```yaml
name: Upgrade Impact Analysis
on:
  pull_request:
    paths: ["requirements*.txt", "pyproject.toml", "Pipfile"]

jobs:
  analyze:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - run: pip install upgrade-impact-analyzer

      - name: Run analysis
        run: upgrade-analyzer analyze --format sarif --output results.sarif --security
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}

      - uses: github/codeql-action/upload-sarif@v3
        with:
          sarif_file: results.sarif
```

## 🪝 Pre-commit Hook

Add to `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: local
    hooks:
      - id: upgrade-analyzer
        name: Upgrade Impact Analysis
        entry: upgrade-analyzer analyze --check-only
        language: system
        pass_filenames: false
        files: (requirements.*\.txt|pyproject\.toml)$
```

## 📊 Risk Scoring Algorithm

The risk score (0-100) combines three factors:

| Factor                 | Weight | Description                        |
| ---------------------- | ------ | ---------------------------------- |
| **Usage Impact**       | 50%    | How many used symbols are affected |
| **SemVer Distance**    | 30%    | Major/minor/patch version delta    |
| **Changelog Severity** | 20%    | Breaking changes in release notes  |

**Severity Levels:**

- 🔴 **Critical** (80-100): Breaking changes affecting used code
- 🟠 **High** (60-79): Significant API changes
- 🟡 **Medium** (30-59): Notable changes, review recommended
- 🟢 **Low** (0-29): Safe to upgrade

## 📁 Supported Dependency Files

| File               | Parser                 |
| ------------------ | ---------------------- |
| `requirements.txt` | RequirementsParser     |
| `pyproject.toml`   | PyprojectParser        |
| `Pipfile`          | PipfileParser          |
| `poetry.lock`      | PoetryLockParser       |
| `Pipfile.lock`     | PipfileLockParser      |
| `environment.yml`  | CondaEnvironmentParser |
| `setup.py`         | SetupPyParser          |

## 🏗️ Architecture

```
upgrade_analyzer/
├── parsers/          # Dependency file parsers
├── scanner/          # AST-based code analysis
├── intelligence/     # PyPI, changelog, API diffing, security
├── recommendations/  # Upgrade path suggestions
├── reporters/        # Output formatters
├── cli.py           # Typer CLI
└── analyzer.py      # Main orchestrator
```

## 🧪 Development

```bash
# Clone repo
git clone https://github.com/example/upgrade-impact-analyzer
cd upgrade-impact-analyzer

# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run with coverage
pytest --cov=upgrade_analyzer

# Type checking
mypy src/

# Linting
ruff check src/
```

## 📄 License

MIT License - see [LICENSE](LICENSE) for details.
