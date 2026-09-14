"""
NEXUS OVERLAY AI - Local Model Provider (Ollama)
Local inference via Ollama endpoint. Same interface as OpenAI/Claude.
"""
from __future__ import annotations
import json
import os
import logging

import aiohttp

from backend.ai.provider import AIProvider, ProviderConfig
from backend.models import MarketSnapshot, AIAssessment, AIProviderType, now_ms

logger = logging.getLogger(__name__)

LOCAL_SYSTEM_PROMPT = """You are a professional gold (XAUUSD) trading analyst. Analyze the provided market data and give a concise trading assessment.

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
- Never give financial advice, only technical analysis"""

LOCAL_USER_TEMPLATE = """Analyze XAUUSD market conditions:

Price: {price} | Spread: {spread}
Trend: {trend}
Structure: {structure}
Liquidity: {liquidity}
Price Action: {price_action}
Momentum: {momentum}
Volatility: {volatility}
Session: {session} | Regime: {regime}
Data Quality: {data_quality:.0%}

Respond with JSON analysis:"""


class LocalProvider(AIProvider):
    """
    Local model provider via Ollama API.
    
    Features:
    - Connects to locally hosted Ollama instance
    - No API key required
    - Lower latency (no network round-trip)
    - Configurable model (llama3, mistral, etc.)
    - Same interface as cloud providers
    """
    
    def __init__(self, config: ProviderConfig | None = None):
        super().__init__(config)
        self._endpoint = self.config.model  # Endpoint is set via model field in config
        self._model_name = "llama3"
        
        from backend.config_loader import get_config
        cfg = get_config()
        local_cfg = cfg.get_section("ai").get("providers", {}).get("local", {})
        self._endpoint = local_cfg.get("endpoint", "http://localhost:11434/api/generate")
        self._model_name = local_cfg.get("model", "llama3")
        
        logger.info(f"Local provider configured: {self._endpoint} (model: {self._model_name})")
    
    def _default_config(self) -> ProviderConfig:
        return ProviderConfig(
            model="http://localhost:11434/api/generate",
            max_tokens=500,
            temperature=0.1,
            rate_limit_per_minute=30,  # Local models can handle more
            timeout_seconds=60.0,  # Local models may be slower
        )
    
    def provider_type(self) -> AIProviderType:
        return AIProviderType.LOCAL
    
    def _format_prompt(self, snapshot: MarketSnapshot) -> str:
        """Format market snapshot into analysis prompt."""
        trend_str = ", ".join(f"{k}: {v}" for k, v in snapshot.trend.items()) if snapshot.trend else "N/A"
        structure_str = ", ".join(f"{k}: {v}" for k, v in snapshot.structure.items()) if snapshot.structure else "N/A"
        liquidity_str = json.dumps(snapshot.liquidity, default=str)[:200] if snapshot.liquidity else "N/A"
        price_action_str = json.dumps(snapshot.price_action, default=str)[:200] if snapshot.price_action else "N/A"
        momentum_str = json.dumps(snapshot.momentum, default=str)[:200] if snapshot.momentum else "N/A"
        volatility_str = json.dumps(snapshot.volatility, default=str)[:200] if snapshot.volatility else "N/A"
        
        return LOCAL_USER_TEMPLATE.format(
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
        """Parse local model response JSON."""
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
        """Call Ollama API for local model analysis."""
        prompt = self._format_prompt(snapshot)
        
        payload = {
            "model": self._model_name,
            "prompt": prompt,
            "system": LOCAL_SYSTEM_PROMPT,
            "stream": False,
            "options": {
                "temperature": self.config.temperature,
                "num_predict": self.config.max_tokens,
            },
            "format": "json",
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                self._endpoint,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=self.config.timeout_seconds),
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise RuntimeError(f"Ollama API error {resp.status}: {error_text[:500]}")
                
                data = await resp.json()
        
        # Extract response
        response_text = data.get("response", "")
        if not response_text:
            raise RuntimeError("Empty response from local model")
        
        parsed = self._parse_response(response_text)
        
        if not parsed:
            # Try to use the raw response for a basic assessment
            lower_text = response_text.lower()
            if "bullish" in lower_text:
                return AIAssessment(
                    provider=AIProviderType.LOCAL,
                    assessment="bullish",
                    confidence=0.4,
                    explanation=response_text[:500],
                    timestamp=now_ms(),
                )
            elif "bearish" in lower_text:
                return AIAssessment(
                    provider=AIProviderType.LOCAL,
                    assessment="bearish",
                    confidence=0.4,
                    explanation=response_text[:500],
                    timestamp=now_ms(),
                )
            else:
                return AIAssessment(
                    provider=AIProviderType.LOCAL,
                    assessment="neutral",
                    confidence=0.3,
                    explanation=response_text[:500],
                    timestamp=now_ms(),
                )
        
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
            provider=AIProviderType.LOCAL,
            assessment=assessment,
            confidence=confidence,
            explanation=explanation[:500],
            timestamp=now_ms(),
        )
    
    async def health_check(self) -> bool:
        """Check if Ollama is running and model is available."""
        try:
            base_url = self._endpoint.rsplit("/api/generate", 1)[0]
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{base_url}/api/tags",
                    timeout=aiohttp.ClientTimeout(total=5.0),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        models = [m.get("name", "") for m in data.get("models", [])]
                        if any(self._model_name in m for m in models):
                            self._available = True
                            return True
            self._available = False
            return False
        except Exception:
            self._available = False
            return False