"""NLP analysis of changelog content."""

import re

from upgrade_analyzer.models import ChangelogEntry, Severity


class ChangelogAnalyzer:
    """Analyzes changelog text for breaking changes and risk keywords."""
    
    # Severity keyword mappings
    CRITICAL_KEYWORDS = [
        "removed",
        "deleted",
        "breaking change",
        "breaking",
        "incompatible",
        "no longer supported",
        "no longer",
        "dropped support",
        "dropped",
    ]
    
    HIGH_KEYWORDS = [
        "deprecated",
        "renamed",
        "changed behavior",
        "behavior change",
        "major change",
        "migration required",
        "must migrate",
    ]
    
    MEDIUM_KEYWORDS = [
        "changed",
        "modified",
        "updated",
        "migrated",
        "refactored",
        "replaced",
    ]
    
    LOW_KEYWORDS = [
        "added",
        "improved",
        "enhanced",
        "optimized",
        "fixed",
        "bugfix",
    ]
    
    def analyze_changelog(self, entry: ChangelogEntry) -> ChangelogEntry:
        """Analyze changelog entry for severity keywords.
        
        Args:
            entry: Changelog entry to analyze
            
        Returns:
            Updated changelog entry with severity keywords
        """
        content_lower = entry.content.lower()
        keywords: list[tuple[str, Severity]] = []
        
        # Check for critical keywords
        for keyword in self.CRITICAL_KEYWORDS:
            if keyword in content_lower:
                keywords.append((keyword, Severity.CRITICAL))
        
        # Check for high severity keywords
        for keyword in self.HIGH_KEYWORDS:
            if keyword in content_lower:
                keywords.append((keyword, Severity.HIGH))
        
        # Check for medium severity keywords
        for keyword in self.MEDIUM_KEYWORDS:
            if keyword in content_lower:
                keywords.append((keyword, Severity.MEDIUM))
        
        # Check for low severity keywords
        for keyword in self.LOW_KEYWORDS:
            if keyword in content_lower:
                keywords.append((keyword, Severity.LOW))
        
        entry.severity_keywords = keywords
        
        return entry
    
    def extract_breaking_changes(self, entry: ChangelogEntry) -> list[str]:
        """Extract breaking change descriptions from changelog.
        
        Args:
            entry: Changelog entry
            
        Returns:
            List of breaking change descriptions
        """
        breaking_changes = []
        
        # Look for "Breaking Changes" section
        breaking_section_pattern = r"#+\s*Breaking\s+Changes?\s*[:\-]?\s*(.*?)(?=\n#+|\Z)"
        matches = re.findall(
            breaking_section_pattern,
            entry.content,
            re.IGNORECASE | re.DOTALL
        )
        
        if matches:
            for match in matches:
                # Extract bullet points or lines
                lines = match.strip().split("\n")
                for line in lines:
                    line = line.strip()
                    if line and (line.startswith("-") or line.startswith("*")):
                        breaking_changes.append(line.lstrip("-*").strip())
        
        # Also look for lines mentioning breaking changes
        for line in entry.content.split("\n"):
            line_lower = line.lower()
            if any(kw in line_lower for kw in ["breaking", "removed", "deprecated"]):
                if line.strip() and line.strip() not in breaking_changes:
                    breaking_changes.append(line.strip())
        
        return breaking_changes[:10]  # Limit to 10 items
    
    def calculate_changelog_severity_score(self, entry: ChangelogEntry) -> float:
        """Calculate severity score based on keywords.
        
        Args:
            entry: Changelog entry (must be analyzed first)
            
        Returns:
            Severity score (0-100)
        """
        if not entry.severity_keywords:
            return 0.0
        
        # Weight keywords by severity
        severity_weights = {
            Severity.CRITICAL: 100,
            Severity.HIGH: 70,
            Severity.MEDIUM: 40,
            Severity.LOW: 10,
        }
        
        # Calculate weighted score
        total_weight = 0.0
        keyword_count = len(entry.severity_keywords)
        
        for _, severity in entry.severity_keywords:
            total_weight += severity_weights.get(severity, 0)
        
        # Average and normalize
        if keyword_count > 0:
            score = total_weight / keyword_count
        else:
            score = 0.0
        
        # Cap at 100
        return min(score, 100.0)
    
    def analyze_multiple_entries(
        self,
        entries: list[ChangelogEntry]
    ) -> list[ChangelogEntry]:
        """Analyze multiple changelog entries.
        
        Args:
            entries: List of changelog entries
            
        Returns:
            List of analyzed entries
        """
        return [self.analyze_changelog(entry) for entry in entries]
