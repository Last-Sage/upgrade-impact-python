# 🔍 Upgrade Impact Analyzer

> **Intelligent dependency upgrade risk analysis with AI-powered insights**

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

Upgrade Impact Analyzer goes beyond simple SemVer rules. It analyzes **your actual code usage** against library changelogs, API changes, and known vulnerabilities to tell you exactly how risky an upgrade really is.

## ✨ Key Features

| Feature                   | Description                                                |
| ------------------------- | ---------------------------------------------------------- |
| **Usage-Centric Scoring** | Risk scored by actual code usage, not just version numbers |
| **AI-Powered Analysis**   | LLM changelog summarization (OpenAI/Anthropic)             |
| **Conflict Detection**    | Detect incompatible upgrades before they break your code   |
| **Security Scanning**     | CVE detection via pip-audit and OSV.dev                    |
| **Health Scoring**        | A-F grades based on maintenance, popularity, quality       |
| **SBOM Generation**       | CycloneDX 1.5 and SPDX 2.3 formats                         |
| **License Auditing**      | Compliance checking with deny lists                        |
| **Monorepo Support**      | Analyze multiple projects with shared deps                 |
| **Custom Policies**       | Define risk thresholds per package                         |
| **Multi-Format Output**   | Terminal, JSON, SARIF, JUnit XML, Markdown                 |
| **CI/CD Integration**     | GitHub Actions, pre-commit hooks                           |

## 🚀 Quick Start

```bash
# Install
pip install upgrade-impact-analyzer

# Analyze your project
upgrade-analyzer analyze

# Check for conflicts before upgrading
upgrade-analyzer conflicts

# With security scanning
upgrade-analyzer analyze --security

# Generate SBOM
upgrade-analyzer sbom --output sbom.json

# Health scoring
upgrade-analyzer health

# AI-powered analysis (requires OPENAI_API_KEY)
upgrade-analyzer ai-analyze --package requests --from 2.28.0 --to 2.31.0
```

## 📦 Installation

```bash
# Basic installation
pip install upgrade-impact-analyzer

# With security scanning support
pip install upgrade-impact-analyzer[security]

# With all optional features
pip install upgrade-impact-analyzer[all]
```

## 💡 Usage

### Basic Analysis

```bash
upgrade-analyzer analyze                              # Auto-detect files
upgrade-analyzer analyze --project /path/to/project   # Specify path
upgrade-analyzer analyze --format sarif --output results.sarif  # SARIF output
```

### 🔍 Conflict Detection

Detect incompatible dependencies **before** upgrading:

```bash
upgrade-analyzer conflicts                    # Check all upgrades
upgrade-analyzer conflicts --output conflicts.md  # Save report
```

Features:

- Forward conflicts (X requires Y>=2.0, but 1.x installed)
- Reverse conflicts (A depends on B<3.0, can't upgrade B to 3.x)
- Cross-upgrade conflicts (upgrading X and Y together breaks)

### 🤖 AI-Powered Analysis

```bash
# Requires OPENAI_API_KEY or ANTHROPIC_API_KEY
export OPENAI_API_KEY="sk-..."

upgrade-analyzer ai-analyze \
  --package requests \
  --from 2.28.0 \
  --to 2.31.0
```

### 📊 Health Scoring

```bash
upgrade-analyzer health                    # Show A-F grades
upgrade-analyzer health --output health.md # Save report
```

### 📋 SBOM Generation

```bash
upgrade-analyzer sbom --output sbom.json          # CycloneDX
upgrade-analyzer sbom --format spdx --output sbom.spdx.json  # SPDX
```

### 📜 License Auditing

```bash
upgrade-analyzer licenses                          # Basic audit
upgrade-analyzer licenses --deny AGPL-3.0          # Deny specific
```

### 🏢 Monorepo Support

```bash
upgrade-analyzer monorepo --root /path/to/monorepo
upgrade-analyzer monorepo --output monorepo-report.md
```

### 📋 Custom Risk Policies

```bash
upgrade-analyzer init-policies   # Create .upgrade-policies.toml
```

Example policy:

```toml
[[policies]]
name = "Critical Package Stability"
packages = ["django", "flask", "sqlalchemy"]
max_semver_major = 1
require_approval = true
```

## 📊 All CLI Commands

| Command         | Description                          |
| --------------- | ------------------------------------ |
| `analyze`       | Analyze upgrade risks (main command) |
| `conflicts`     | Detect dependency conflicts          |
| `sbom`          | Generate SBOM (CycloneDX/SPDX)       |
| `health`        | Calculate health scores (A-F grades) |
| `licenses`      | Audit dependency licenses            |
| `monorepo`      | Analyze monorepo projects            |
| `ai-analyze`    | AI-powered changelog analysis        |
| `scan-security` | Vulnerability scanning               |
| `detect`        | Detect dependency files              |
| `init-policies` | Create policies template             |
| `clear-cache`   | Clear cached data                    |
| `version`       | Show version info                    |

## 🔧 Configuration

### Environment Variables

| Variable            | Description                             |
| ------------------- | --------------------------------------- |
| `GITHUB_TOKEN`      | GitHub API token for higher rate limits |
| `OPENAI_API_KEY`    | OpenAI API key for AI analysis          |
| `ANTHROPIC_API_KEY` | Anthropic API key for AI analysis       |

## 🧪 Running Tests

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run all tests
pytest

# Run with coverage
pytest --cov=upgrade_analyzer

# Run specific test file
pytest tests/test_risk_scorer.py -v

# Run with verbose output
pytest -v --tb=short
```

## 🔄 GitHub Actions

```yaml
- run: upgrade-analyzer analyze --format sarif --output results.sarif
  env:
    GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}

- uses: github/codeql-action/upload-sarif@v3
  with:
    sarif_file: results.sarif
```

## 🏗️ Architecture

```
upgrade_analyzer/
├── analyzer.py          # Main orchestrator
├── cli.py               # Typer CLI commands
├── conflict_detector.py # Dependency conflict detection
├── http_client.py       # Async HTTP with retry
├── cache.py             # Thread-safe caching
├── health.py            # Health scoring (A-F)
├── sbom.py              # SBOM & license auditing
├── enterprise.py        # Monorepo & policies
├── intelligence/        # Risk analysis
│   ├── api_differ.py   # API diffing (griffe)
│   ├── risk_scorer.py  # Risk calculation
│   ├── security.py     # CVE detection
│   └── llm_analyzer.py # AI analysis
├── parsers/             # Dependency parsers
├── reporters/           # Output formatters
└── scanner/             # Code analysis
    └── ast_analyzer.py  # AST-based usage detection
```

## 📄 License

MIT License - see [LICENSE](LICENSE) for details.
