"""
NEXUS OVERLAY AI - OpenAI API Provider
Sends structured market snapshot to GPT-4o-mini for analysis.
Returns structured AI assessment with bullish/bearish/neutral + confidence + explanation.
Rate limited.
"""
from __future__ import annotations
import json
import os
import logging

import aiohttp

from backend.ai.provider import AIProvider, ProviderConfig
from backend.models import MarketSnapshot, AIAssessment, AIProviderType, now_ms

logger = logging.getLogger(__name__)

ANALYSIS_SYSTEM_PROMPT = """You are a professional gold (XAUUSD) trading analyst. Analyze the provided market data and give a concise trading assessment.

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

ANALYSIS_USER_TEMPLATE = """Analyze XAUUSD market conditions:

Price: {price} | Spread: {spread}
Trend: {trend}
Structure: {structure}
Liquidity: {liquidity}
Price Action: {price_action}
Momentum: {momentum}
Volatility: {volatility}
Session: {session} | Regime: {regime}
Data Quality: {data_quality:.0%}

Provide your technical analysis assessment."""

OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"


class OpenAIProvider(AIProvider):
    """
    OpenAI GPT-4o-mini provider for market analysis.
    
    Features:
    - Structured prompt engineering for consistent outputs
    - Rate limiting (configurable per minute)
    - Automatic retry on transient failures
    - JSON response parsing with fallback
    """
    
    def __init__(self, config: ProviderConfig | None = None):
        super().__init__(config)
        self._api_key: str = os.getenv("OPENAI_API_KEY", "")
        
        # Check config for API key
        if not self._api_key:
            from backend.config_loader import get_config
            cfg = get_config()
            self._api_key = cfg.get("ai.providers.openai.api_key", "")
        
        if not self._api_key:
            logger.warning("OpenAI API key not set - provider will be unavailable")
            self._available = False
    
    def _default_config(self) -> ProviderConfig:
        from backend.config_loader import get_config
        cfg = get_config()
        openai_cfg = cfg.get_section("ai").get("providers", {}).get("openai", {})
        return ProviderConfig(
            model=openai_cfg.get("model", "gpt-4o-mini"),
            max_tokens=openai_cfg.get("max_tokens", 500),
            temperature=openai_cfg.get("temperature", 0.1),
            rate_limit_per_minute=openai_cfg.get("rate_limit_per_minute", 10),
            timeout_seconds=30.0,
        )
    
    def provider_type(self) -> AIProviderType:
        return AIProviderType.OPENAI
    
    def _format_prompt(self, snapshot: MarketSnapshot) -> str:
        """Format market snapshot into analysis prompt."""
        trend_str = ", ".join(f"{k}: {v}" for k, v in snapshot.trend.items()) if snapshot.trend else "N/A"
        structure_str = ", ".join(f"{k}: {v}" for k, v in snapshot.structure.items()) if snapshot.structure else "N/A"
        liquidity_str = json.dumps(snapshot.liquidity, default=str)[:200] if snapshot.liquidity else "N/A"
        price_action_str = json.dumps(snapshot.price_action, default=str)[:200] if snapshot.price_action else "N/A"
        momentum_str = json.dumps(snapshot.momentum, default=str)[:200] if snapshot.momentum else "N/A"
        volatility_str = json.dumps(snapshot.volatility, default=str)[:200] if snapshot.volatility else "N/A"
        
        return ANALYSIS_USER_TEMPLATE.format(
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
    
    def _parse_response(self, response_text: str) -> dict:
        """Parse OpenAI response JSON, handling markdown code blocks."""
        text = response_text.strip()
        
        # Strip markdown code blocks if present
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove first and last lines (```json and ```)
            lines = [l for l in lines[1:] if not l.strip().startswith("```")]
            text = "\n".join(lines).strip()
        
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Try to find JSON object in response
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start:end])
                except json.JSONDecodeError:
                    pass
            return {}
    
    async def _analyze_impl(self, snapshot: MarketSnapshot) -> AIAssessment:
        """Call OpenAI API for market analysis."""
        prompt = self._format_prompt(snapshot)
        
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        
        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": self.config.max_tokens,
            "temperature": self.config.temperature,
            "response_format": {"type": "json_object"},
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                OPENAI_API_URL,
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=self.config.timeout_seconds),
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise RuntimeError(f"OpenAI API error {resp.status}: {error_text[:500]}")
                
                data = await resp.json()
        
        # Extract response
        content = data["choices"][0]["message"]["content"]
        parsed = self._parse_response(content)
        
        if not parsed:
            raise RuntimeError("Failed to parse OpenAI response")
        
        # Map assessment string to enum-like string
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
            provider=AIProviderType.OPENAI,
            assessment=assessment,
            confidence=confidence,
            explanation=explanation[:500],
            timestamp=now_ms(),
        )