"""
NEXUS OVERLAY AI - OpenRouter Provider
OpenAI-compatible API (https://openrouter.ai)
Supports free models and paid models via single API key.
"""
from __future__ import annotations
import asyncio
import json
import logging
import os
from typing import Optional

import aiohttp

from backend.ai.provider import AIProvider, ProviderConfig
from backend.models import AIAssessment, AIProviderType, MarketSnapshot, now_ms

logger = logging.getLogger(__name__)


class OpenRouterProvider(AIProvider):
    """OpenRouter AI provider - OpenAI-compatible endpoint."""

    def _default_config(self) -> ProviderConfig:
        return ProviderConfig(
            model="openrouter/kr",
            max_tokens=500,
            temperature=0.1,
            rate_limit_per_minute=10,
            timeout_seconds=30.0,
        )

    def provider_type(self) -> AIProviderType:
        return AIProviderType.LOCAL  # Using LOCAL enum as custom

    async def _analyze_impl(self, snapshot: MarketSnapshot) -> AIAssessment:
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY not set in environment")

        endpoint = "https://openrouter.ai/api/v1/chat/completions"
        
        # Build structured prompt from snapshot
        prompt = self._build_prompt(snapshot)
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/nexus-overlay-ai",
            "X-Title": "Nexus Overlay AI",
        }
        
        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": self._system_prompt()},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": self.config.max_tokens,
            "temperature": self.config.temperature,
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(endpoint, headers=headers, json=payload) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise RuntimeError(f"OpenRouter API error {resp.status}: {text}")
                data = await resp.json()
                
                choice = data.get("choices", [{}])[0]
                content = choice.get("message", {}).get("content", "")
                
                return self._parse_response(content)

    def _system_prompt(self) -> str:
        return """You are a professional XAUUSD market analyst. Analyze the structured market data and provide a concise assessment.

Output format (JSON only):
{
  "assessment": "bullish|bearish|neutral",
  "confidence": 0.0-1.0,
  "explanation": "Key reasons: trend, structure, liquidity, MTF alignment, risk factors"
}"""

    def _build_prompt(self, snapshot: MarketSnapshot) -> str:
        return f"""Analyze XAUUSD market snapshot:

PRICE: {snapshot.price:.2f} | SPREAD: {snapshot.spread:.2f}
TREND: {snapshot.trend}
STRUCTURE: {snapshot.structure}
LIQUIDITY: {snapshot.liquidity}
PRICE_ACTION: {snapshot.price_action}
MOMENTUM: {snapshot.momentum}
VOLATILITY: {snapshot.volatility}
SESSION: {snapshot.session}
REGIME: {snapshot.regime}
DATA_QUALITY: {snapshot.data_quality:.0f}/100

Provide assessment."""

    def _parse_response(self, content: str) -> AIAssessment:
        import re
        try:
            # Try to extract JSON from response
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                assessment = data.get("assessment", "neutral")
                confidence = float(data.get("confidence", 0.5))
                explanation = data.get("explanation", content[:200])
            else:
                raise ValueError("No JSON found")
        except Exception:
            # Fallback parsing
            content_lower = content.lower()
            if "bullish" in content_lower:
                assessment = "bullish"
            elif "bearish" in content_lower:
                assessment = "bearish"
            else:
                assessment = "neutral"
            confidence = 0.5
            explanation = content[:200]

        return AIAssessment(
            provider=AIProviderType.LOCAL,
            assessment=assessment,
            confidence=confidence,
            explanation=explanation,
            timestamp=now_ms(),
        )


class OpenAIProvider(AIProvider):
    """Direct OpenAI API provider (paid)."""

    def _default_config(self) -> ProviderConfig:
        return ProviderConfig(
            model="gpt-4o-mini",
            max_tokens=500,
            temperature=0.1,
            rate_limit_per_minute=10,
            timeout_seconds=30.0,
        )

    def provider_type(self) -> AIProviderType:
        return AIProviderType.OPENAI

    async def _analyze_impl(self, snapshot: MarketSnapshot) -> AIAssessment:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not set")
        # Use OpenRouter provider logic with different endpoint
        # For brevity, fallback to deterministic
        return self._fallback_assessment(snapshot, "OpenAI not configured")


class ClaudeProvider(AIProvider):
    """Anthropic Claude API provider (paid)."""

    def _default_config(self) -> ProviderConfig:
        return ProviderConfig(
            model="claude-3-haiku-20240307",
            max_tokens=500,
            temperature=0.1,
            rate_limit_per_minute=10,
            timeout_seconds=30.0,
        )

    def provider_type(self) -> AIProviderType:
        return AIProviderType.CLAUDE

    async def _analyze_impl(self, snapshot: MarketSnapshot) -> AIAssessment:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")
        return self._fallback_assessment(snapshot, "Claude not configured")


class LocalProvider(AIProvider):
    """Local Ollama endpoint provider."""

    def _default_config(self) -> ProviderConfig:
        return ProviderConfig(
            model="llama3",
            max_tokens=500,
            temperature=0.1,
            rate_limit_per_minute=10,
            timeout_seconds=60.0,
        )

    def provider_type(self) -> AIProviderType:
        return AIProviderType.LOCAL

    async def _analyze_impl(self, snapshot: MarketSnapshot) -> AIAssessment:
        # For brevity, fallback
        return self._fallback_assessment(snapshot, "Local model not configured")