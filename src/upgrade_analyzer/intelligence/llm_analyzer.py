"""AI-powered changelog analysis using LLMs."""

import logging
import os
from dataclasses import dataclass

import httpx

from upgrade_analyzer.cache import get_cache
from upgrade_analyzer.models import ChangelogEntry, Severity

logger = logging.getLogger(__name__)


@dataclass
class AIAnalysisResult:
    """Result of AI-powered changelog analysis."""
    
    summary: str
    breaking_changes: list[str]
    migration_steps: list[str]
    risk_assessment: str
    affected_areas: list[str]
    estimated_effort: str  # "low", "medium", "high"


class LLMChangelogAnalyzer:
    """Analyze changelogs using Large Language Models."""
    
    SYSTEM_PROMPT = """You are an expert Python developer analyzing package changelogs.
Your task is to:
1. Summarize breaking changes in plain English
2. Identify specific migration steps needed
3. Assess risk level (low/medium/high)
4. List affected code areas
5. Estimate migration effort

Be concise and actionable. Focus on practical developer needs."""

    def __init__(self, provider: str = "auto") -> None:
        """Initialize LLM analyzer.
        
        Args:
            provider: LLM provider ("openai", "anthropic", "auto")
        """
        self.cache = get_cache()
        self.client = httpx.Client(timeout=60.0)
        
        # Auto-detect provider based on available API keys
        if provider == "auto":
            if os.environ.get("OPENAI_API_KEY"):
                self.provider = "openai"
            elif os.environ.get("ANTHROPIC_API_KEY"):
                self.provider = "anthropic"
            else:
                self.provider = None
                logger.info("No LLM API key found - AI analysis disabled")
        else:
            self.provider = provider
        
        self.api_key = self._get_api_key()
    
    def _get_api_key(self) -> str | None:
        """Get API key for current provider."""
        if self.provider == "openai":
            return os.environ.get("OPENAI_API_KEY")
        elif self.provider == "anthropic":
            return os.environ.get("ANTHROPIC_API_KEY")
        return None
    
    @property
    def is_available(self) -> bool:
        """Check if LLM analysis is available."""
        return self.provider is not None and self.api_key is not None
    
    def analyze_changelog(
        self,
        package_name: str,
        from_version: str,
        to_version: str,
        changelog_entries: list[ChangelogEntry],
        code_context: str | None = None,
    ) -> AIAnalysisResult | None:
        """Analyze changelog using LLM.
        
        Args:
            package_name: Name of the package
            from_version: Current version
            to_version: Target version
            changelog_entries: Changelog entries to analyze
            code_context: Optional code snippets showing current usage
            
        Returns:
            AI analysis result or None if unavailable
        """
        if not self.is_available:
            return None
        
        # Check cache first
        cache_key = f"llm_analysis:{package_name}:{from_version}:{to_version}"
        cached = self.cache.get(cache_key, cache_type="llm", ttl_hours=168)  # 1 week
        
        if cached:
            return AIAnalysisResult(**cached)
        
        # Build prompt
        changelog_text = "\n\n".join(
            f"## {e.version}\n{e.content}"
            for e in changelog_entries[:10]  # Limit to recent entries
        )
        
        user_prompt = f"""Analyze the following changelog for upgrading {package_name} from {from_version} to {to_version}.

CHANGELOG:
{changelog_text[:4000]}

{f"CURRENT CODE USAGE:\n{code_context[:1000]}" if code_context else ""}

Provide:
1. **Summary** (2-3 sentences)
2. **Breaking Changes** (list)
3. **Migration Steps** (numbered list)
4. **Risk Assessment** (low/medium/high with reason)
5. **Affected Areas** (list of modules/features)
6. **Estimated Effort** (low/medium/high)

Format your response as JSON:
{{"summary": "...", "breaking_changes": [...], "migration_steps": [...], "risk_assessment": "...", "affected_areas": [...], "estimated_effort": "..."}}"""

        try:
            result = self._call_llm(user_prompt)
            
            if result:
                # Cache result
                self.cache.set(cache_key, result.__dict__, cache_type="llm")
                return result
                
        except Exception as e:
            logger.error(f"LLM analysis failed: {e}")
        
        return None
    
    def _call_llm(self, prompt: str) -> AIAnalysisResult | None:
        """Call LLM API."""
        if self.provider == "openai":
            return self._call_openai(prompt)
        elif self.provider == "anthropic":
            return self._call_anthropic(prompt)
        return None
    
    def _call_openai(self, prompt: str) -> AIAnalysisResult | None:
        """Call OpenAI API."""
        try:
            response = self.client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "gpt-4o-mini",
                    "messages": [
                        {"role": "system", "content": self.SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.3,
                    "max_tokens": 1000,
                },
            )
            
            if response.status_code == 200:
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                return self._parse_response(content)
                
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
        
        return None
    
    def _call_anthropic(self, prompt: str) -> AIAnalysisResult | None:
        """Call Anthropic API."""
        try:
            response = self.client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "claude-3-haiku-20240307",
                    "max_tokens": 1000,
                    "system": self.SYSTEM_PROMPT,
                    "messages": [
                        {"role": "user", "content": prompt},
                    ],
                },
            )
            
            if response.status_code == 200:
                data = response.json()
                content = data["content"][0]["text"]
                return self._parse_response(content)
                
        except Exception as e:
            logger.error(f"Anthropic API error: {e}")
        
        return None
    
    def _parse_response(self, content: str) -> AIAnalysisResult | None:
        """Parse LLM response into structured result."""
        import json
        import re
        
        try:
            # Try to extract JSON from response
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            
            if json_match:
                data = json.loads(json_match.group())
                
                return AIAnalysisResult(
                    summary=data.get("summary", ""),
                    breaking_changes=data.get("breaking_changes", []),
                    migration_steps=data.get("migration_steps", []),
                    risk_assessment=data.get("risk_assessment", ""),
                    affected_areas=data.get("affected_areas", []),
                    estimated_effort=data.get("estimated_effort", "medium"),
                )
        except json.JSONDecodeError:
            pass
        
        # Fallback: return raw summary
        return AIAnalysisResult(
            summary=content[:500],
            breaking_changes=[],
            migration_steps=[],
            risk_assessment="unknown",
            affected_areas=[],
            estimated_effort="medium",
        )
    
    def generate_migration_code(
        self,
        old_code: str,
        api_changes: list,
        package_name: str,
    ) -> str | None:
        """Generate migration code suggestions.
        
        Args:
            old_code: Current code using the package
            api_changes: List of API changes
            package_name: Package name
            
        Returns:
            Suggested code changes or None
        """
        if not self.is_available:
            return None
        
        changes_text = "\n".join(
            f"- {c.symbol_name}: {c.change_type.value} - {c.description}"
            for c in api_changes[:10]
        )
        
        prompt = f"""Given these API changes for {package_name}:

{changes_text}

And this code:
```python
{old_code[:2000]}
```

Suggest the minimal code changes needed to migrate. Show only the modified lines with comments explaining each change.
"""
        
        try:
            if self.provider == "openai":
                response = self.client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "gpt-4o-mini",
                        "messages": [
                            {"role": "system", "content": "You are an expert Python developer. Provide concise code migration suggestions."},
                            {"role": "user", "content": prompt},
                        ],
                        "temperature": 0.2,
                        "max_tokens": 1500,
                    },
                )
                
                if response.status_code == 200:
                    return response.json()["choices"][0]["message"]["content"]
                    
        except Exception as e:
            logger.error(f"Migration code generation failed: {e}")
        
        return None
    
    def close(self) -> None:
        """Close HTTP client."""
        self.client.close()
