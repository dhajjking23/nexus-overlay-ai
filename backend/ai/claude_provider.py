"""
NEXUS OVERLAY AI - Claude API Provider
Anthropic Claude provider for market analysis with same interface as OpenAI.
"""
from __future__ import annotations
import json
import os
import logging

import aiohttp

from backend.ai.provider import AIProvider, ProviderConfig
from backend.models import MarketSnapshot, AIAssessment, AIProviderType, now_ms

logger = logging.getLogger(__name__)

CLAUDE_SYSTEM_PROMPT = """You are a professional gold (XAUUSD) trading analyst. Analyze the provided market data and give a concise trading assessment.

You MUST respond with valid JSON in this exact format:
{
    "assessment": "bullish" | "bearish" | "neutral" | "contradictions" | "missing_confirmation",
    "confidence": 0.0 to 1.0,
    "explanation": "Brief 2-3 sentence technical explanation",
    "key_factors": ["factor1", "factor2"],
    "risks": ["risk1", "risk2"]
}

Rules:
- Be direct and concise
- Only use the data provided
- If data is insufficient, say "neutral" with low confidence
- Never give financial advice, only technical analysis
- Consider timeframe alignment and market structure
"""

CLAUDE_USER_TEMPLATE = """Analyze XAUUSD market conditions:

Price: {price} | Spread: {spread}
Trend: {trend}
Structure: {structure}
Liquidity: {liquidity}
Price Action: {price_action}
Momentum: {momentum}
Volatility: {volatility}
Session: {session} | Regime: {regime}
Data Quality: {data_quality:.0%}

Provide your technical analysis assessment as JSON."""

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"


class ClaudeProvider(AIProvider):
    """
    Anthropic Claude provider for market analysis.
    
    Features:
    - Same interface as OpenAI provider
    - Structured prompt with JSON output
    - Rate limiting and fallback
    - Supports Claude 3 Haiku for cost efficiency
    """
    
    def __init__(self, config: ProviderConfig | None = None):
        super().__init__(config)
        self._api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
        
        if not self._api_key:
            from backend.config_loader import get_config
            cfg = get_config()
            self._api_key = cfg.get("ai.providers.claude.api_key", "")
        
        if not self._api_key:
            logger.warning("Anthropic API key not set - provider will be unavailable")
            self._available = False
    
    def _default_config(self) -> ProviderConfig:
        from backend.config_loader import get_config
        cfg = get_config()
        claude_cfg = cfg.get_section("ai").get("providers", {}).get("claude", {})
        return ProviderConfig(
            model=claude_cfg.get("model", "claude-3-haiku-20240307"),
            max_tokens=claude_cfg.get("max_tokens", 500),
            temperature=claude_cfg.get("temperature", 0.1),
            rate_limit_per_minute=claude_cfg.get("rate_limit_per_minute", 10),
            timeout_seconds=30.0,
        )
    
    def provider_type(self) -> AIProviderType:
        return AIProviderType.CLAUDE
    
    def _format_prompt(self, snapshot: MarketSnapshot) -> str:
        """Format market snapshot into analysis prompt."""
        trend_str = ", ".join(f"{k}: {v}" for k, v in snapshot.trend.items()) if snapshot.trend else "N/A"
        structure_str = ", ".join(f"{k}: {v}" for k, v in snapshot.structure.items()) if snapshot.structure else "N/A"
        liquidity_str = json.dumps(snapshot.liquidity, default=str)[:200] if snapshot.liquidity else "N/A"
        price_action_str = json.dumps(snapshot.price_action, default=str)[:200] if snapshot.price_action else "N/A"
        momentum_str = json.dumps(snapshot.momentum, default=str)[:200] if snapshot.momentum else "N/A"
        volatility_str = json.dumps(snapshot.volatility, default=str)[:200] if snapshot.volatility else "N/A"
        
        return CLAUDE_USER_TEMPLATE.format(
            price=f"{snapshot.price:.2f}",
            spread=f"{snapshot.spread:.2f}",
            trend=trend_str,
            structure=structure_str,
            liquidity=liquidity_str,
            price_action=price_action_str,
            momentum=momentum_str,
            volatility=volatility_str,
            session=snapshot.session,
            regime=snapshot.regime,
            data_quality=snapshot.data_quality,
        )
    
    def _parse_response(self, text: str) -> dict:
        """Parse Claude response JSON."""
        text = text.strip()
        
        # Strip markdown code blocks
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [l for l in lines[1:] if not l.strip().startswith("```")]
            text = "\n".join(lines).strip()
        
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start:end])
                except json.JSONDecodeError:
                    pass
            return {}
    
    async def _analyze_impl(self, snapshot: MarketSnapshot) -> AIAssessment:
        """Call Claude API for market analysis."""
        prompt = self._format_prompt(snapshot)
        
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        
        payload = {
            "model": self.config.model,
            "max_tokens": self.config.max_tokens,
            "system": CLAUDE_SYSTEM_PROMPT,
            "messages": [
                {"role": "user", "content": prompt},
            ],
            "temperature": self.config.temperature,
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                ANTHROPIC_API_URL,
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=self.config.timeout_seconds),
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise RuntimeError(f"Claude API error {resp.status}: {error_text[:500]}")
                
                data = await resp.json()
        
        # Extract response content
        content_blocks = data.get("content", [])
        if not content_blocks:
            raise RuntimeError("Empty response from Claude")
        
        content = content_blocks[0].get("text", "")
        parsed = self._parse_response(content)
        
        if not parsed:
            raise RuntimeError("Failed to parse Claude response")
        
        assessment = parsed.get("assessment", "neutral").lower()
        if assessment not in ("bullish", "bearish", "neutral", "contradictions", "missing_confirmation"):
            assessment = "neutral"
        
        confidence = float(parsed.get("confidence", 0.5))
        confidence = max(0.0, min(1.0, confidence))
        
        explanation = parsed.get("explanation", "")
        key_factors = parsed.get("key_factors", [])
        risks = parsed.get("risks", [])
        
        if key_factors:
            explanation += f" Key factors: {', '.join(key_factors[:3])}"
        if risks:
            explanation += f" Risks: {', '.join(risks[:2])}"
        
        return AIAssessment(
            provider=AIProviderType.CLAUDE,
            assessment=assessment,
            confidence=confidence,
            explanation=explanation[:500],
            timestamp=now_ms(),
        )