"""Configuration management for Upgrade Impact Analyzer."""

import logging
import os
from pathlib import Path
from typing import Any

import toml

logger = logging.getLogger(__name__)


class Config:
    """Application configuration."""
    
    def __init__(self, config_file: Path | None = None) -> None:
        """Initialize configuration.
        
        Args:
            config_file: Optional path to configuration file
        """
        self.config_file = config_file
        self._config: dict[str, Any] = self._load_config()
    
    def _load_config(self) -> dict[str, Any]:
        """Load configuration from file or defaults."""
        config: dict[str, Any] = self._get_defaults()
        
        if self.config_file and self.config_file.exists():
            try:
                file_config = toml.load(self.config_file)
                config.update(file_config)
                logger.debug(f"Loaded config from {self.config_file}")
            except toml.TomlDecodeError as e:
                logger.warning(f"Invalid TOML in config file {self.config_file}: {e}")
            except Exception as e:
                logger.warning(f"Error loading config file {self.config_file}: {e}")
        
        return config
    
    @staticmethod
    def _get_defaults() -> dict[str, Any]:
        """Get default configuration values."""
        home = Path.home()
        cache_dir = home / ".upgrade_analyzer" / "cache"
        
        return {
            "cache": {
                "directory": str(cache_dir),
                "pypi_ttl_hours": 24,
                "changelog_ttl_days": 7,
                "enabled": True,
            },
            "risk_scoring": {
                "semver_weight": 0.3,
                "usage_weight": 0.5,
                "changelog_weight": 0.2,
                "thresholds": {
                    "critical": 80,
                    "high": 60,
                    "medium": 30,
                    "low": 0,
                },
            },
            "analysis": {
                "scan_git_ignored": False,
                "exclude_patterns": [
                    "**/venv/**",
                    "**/.venv/**",
                    "**/env/**",
                    "**/node_modules/**",
                    "**/__pycache__/**",
                    "**/.git/**",
                ],
                "include_transitive": True,
                "max_depth": None,  # Unlimited
            },
            "output": {
                "color": True,
                "markdown_report": True,
                "terminal_table": True,
                "sort_by": "risk_score",  # or "name", "severity"
            },
            "ci": {
                "fail_on_high_risk": True,
                "fail_on_critical": True,
            },
        }
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value using dot notation.
        
        Args:
            key: Configuration key (e.g., "cache.directory")
            default: Default value if key not found
            
        Returns:
            Configuration value
        """
        keys = key.split(".")
        value: Any = self._config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    @property
    def cache_dir(self) -> Path:
        """Get cache directory path."""
        cache_path = Path(self.get("cache.directory", "~/.upgrade_analyzer/cache"))
        return cache_path.expanduser()
    
    @property
    def cache_enabled(self) -> bool:
        """Check if caching is enabled."""
        return bool(self.get("cache.enabled", True))
    
    @property
    def exclude_patterns(self) -> list[str]:
        """Get file exclusion patterns."""
        return self.get("analysis.exclude_patterns", [])
    
    @property
    def semver_weight(self) -> float:
        """Get SemVer weight for risk scoring."""
        return float(self.get("risk_scoring.semver_weight", 0.3))
    
    @property
    def usage_weight(self) -> float:
        """Get usage weight for risk scoring."""
        return float(self.get("risk_scoring.usage_weight", 0.5))
    
    @property
    def changelog_weight(self) -> float:
        """Get changelog weight for risk scoring."""
        return float(self.get("risk_scoring.changelog_weight", 0.2))


def load_ignore_file(project_root: Path) -> set[str]:
    """Load packages to ignore from .upgradeignore file.
    
    Args:
        project_root: Root directory of the project
        
    Returns:
        Set of package names to ignore
    """
    ignore_file = project_root / ".upgradeignore"
    ignored: set[str] = set()
    
    if not ignore_file.exists():
        return ignored
    
    try:
        with open(ignore_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                
                # Skip comments and empty lines
                if not line or line.startswith("#"):
                    continue
                
                # Extract package name (before == or >=, etc.)
                package_name = line.split("==")[0].split(">=")[0].split("<=")[0].split("~=")[0]
                package_name = package_name.strip()
                
                if package_name:
                    ignored.add(package_name)
    
    except FileNotFoundError:
        return ignored  # File doesn't exist, not an error
    except PermissionError as e:
        logger.warning(f"Cannot read ignore file {ignore_file}: {e}")
    except Exception as e:
        logger.warning(f"Error parsing ignore file {ignore_file}: {e}")
    
    return ignored


# Global config instance
_config: Config | None = None


def get_config(config_file: Path | None = None) -> Config:
    """Get or create global configuration instance.
    
    Args:
        config_file: Optional path to configuration file
        
    Returns:
        Config instance
    """
    global _config
    
    if _config is None:
        _config = Config(config_file)
    
    return _config
