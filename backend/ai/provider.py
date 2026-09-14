"""
NEXUS OVERLAY AI - AI Provider Base
Abstract base class for AI analysis providers with fallback logic.
"""
from __future__ import annotations
import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from backend.models import (
    MarketSnapshot, AIAssessment, AIProviderType,
    now_ms,
)
from backend.config_loader import get_config

logger = logging.getLogger(__name__)


@dataclass
class ProviderConfig:
    """AI Provider configuration."""
    model: str
    max_tokens: int
    temperature: float
    rate_limit_per_minute: int
    timeout_seconds: float = 30.0


class AIProvider(ABC):
    """
    Abstract base class for AI analysis providers.
    
    All providers must implement analyze() which takes a structured
    MarketSnapshot and returns an AIAssessment with bullish/bearish/neutral
    assessment, confidence, and explanation.
    """
    
    def __init__(self, config: ProviderConfig | None = None):
        cfg = config or self._default_config()
        self.config = cfg
        self._last_call_time: float = 0
        self._call_count: int = 0
        self._rate_limit_window_start: float = 0
        self._available: bool = True
        self._consecutive_failures: int = 0
        self._max_consecutive_failures: int = 5
        self._lock = asyncio.Lock()
    
    @abstractmethod
    def _default_config(self) -> ProviderConfig:
        """Return default configuration for this provider."""
        ...
    
    @abstractmethod
    def provider_type(self) -> AIProviderType:
        """Return the provider type enum."""
        ...
    
    @abstractmethod
    async def _analyze_impl(self, snapshot: MarketSnapshot) -> AIAssessment:
        """
        Provider-specific analysis implementation.
        Must be implemented by subclasses.
        """
        ...
    
    @property
    def is_available(self) -> bool:
        """Check if provider is available (not rate limited, not failed)."""
        return self._available and self._consecutive_failures < self._max_consecutive_failures
    
    async def _check_rate_limit(self) -> bool:
        """Check and enforce rate limit. Returns True if allowed."""
        async with self._lock:
            now = asyncio.get_event_loop().time()
            
            # Reset window if needed
            if now - self._rate_limit_window_start > 60.0:
                self._call_count = 0
                self._rate_limit_window_start = now
            
            if self._call_count >= self.config.rate_limit_per_minute:
                return False
            
            self._call_count += 1
            self._last_call_time = now
            return True
    
    async def analyze(self, snapshot: MarketSnapshot) -> AIAssessment:
        """
        Analyze market snapshot with rate limiting and fallback.
        
        Returns AIAssessment with assessment, confidence, explanation.
        Falls back to deterministic assessment if provider fails.
        """
        if not self.is_available:
            logger.warning(f"{self.provider_type().value} provider unavailable, using fallback")
            return self._fallback_assessment(snapshot, "Provider unavailable")
        
        # Check rate limit
        if not await self._check_rate_limit():
            logger.warning(f"{self.provider_type().value} rate limited, using fallback")
            return self._fallback_assessment(snapshot, "Rate limited")
        
        try:
            # Call provider implementation
            result = await asyncio.wait_for(
                self._analyze_impl(snapshot),
                timeout=self.config.timeout_seconds,
            )
            
            # Reset failure count on success
            self._consecutive_failures = 0
            self._available = True
            
            logger.debug(f"{self.provider_type().value} analysis: {result.assessment} ({result.confidence:.2f})")
            return result
            
        except asyncio.TimeoutError:
            self._consecutive_failures += 1
            logger.error(f"{self.provider_type().value} analysis timeout")
            return self._fallback_assessment(snapshot, "Timeout")
        
        except Exception as e:
            self._consecutive_failures += 1
            logger.error(f"{self.provider_type().value} analysis error: {e}")
            
            if self._consecutive_failures >= self._max_consecutive_failures:
                self._available = False
                logger.error(f"{self.provider_type().value} marked unavailable after {self._consecutive_failures} failures")
            
            return self._fallback_assessment(snapshot, f"Error: {e}")
    
    def _fallback_assessment(self, snapshot: MarketSnapshot, reason: str) -> AIAssessment:
        """
        Generate deterministic fallback assessment when AI is unavailable.
        Uses basic technical analysis from snapshot.
        """
        trend = snapshot.trend.get("primary", "NEUTRAL")
        structure = snapshot.structure.get("type", "NEUTRAL")
        regime = snapshot.regime
        
        # Simple deterministic logic
        bullish_signals = 0
        bearish_signals = 0
        
        if trend == "BULLISH":
            bullish_signals += 2
        elif trend == "BEARISH":
            bearish_signals += 2
        
        if structure in ("BOS", "CHoCH", "HH", "HL"):
            bullish_signals += 1
        elif structure in ("LH", "LL"):
            bearish_signals += 1
        
        if "BULLISH" in regime:
            bullish_signals += 1
        elif "BEARISH" in regime:
            bearish_signals += 1
        
        if bullish_signals > bearish_signals:
            assessment = "bullish"
            confidence = min(0.5 + (bullish_signals - bearish_signals) * 0.1, 0.7)
        elif bearish_signals > bullish_signals:
            assessment = "bearish"
            confidence = min(0.5 + (bearish_signals - bullish_signals) * 0.1, 0.7)
        else:
            assessment = "neutral"
            confidence = 0.3
        
        explanation = f"Deterministic fallback ({reason}): trend={trend}, structure={structure}, regime={regime}"
        
        return AIAssessment(
            provider=self.provider_type(),
            assessment=assessment,
            confidence=confidence,
            explanation=explanation,
            timestamp=now_ms(),
        )
    
    async def health_check(self) -> bool:
        """Health check - can be overridden by providers."""
        return self.is_available
    
    def get_stats(self) -> dict:
        """Get provider statistics."""
        return {
            "provider": self.provider_type().value,
            "model": self.config.model,
            "available": self._available,
            "consecutive_failures": self._consecutive_failures,
            "calls_this_minute": self._call_count,
            "rate_limit": self.config.rate_limit_per_minute,
        }


class AIProviderManager:
    """
    Manages multiple AI providers with fallback chain.
    Tries providers in order until one succeeds.
    """
    
    def __init__(self, providers: list[AIProvider] | None = None):
        self.providers: list[AIProvider] = providers or []
        self._fallback_to_deterministic: bool = True
    
    def add_provider(self, provider: AIProvider) -> None:
        """Add a provider to the chain."""
        self.providers.append(provider)
    
    async def analyze(self, snapshot: MarketSnapshot) -> AIAssessment:
        """
        Try each provider in order until one succeeds.
        Falls back to deterministic if all fail and fallback enabled.
        """
        for provider in self.providers:
            if provider.is_available:
                result = await provider.analyze(snapshot)
                if result.confidence > 0:  # Any valid result
                    return result
        
        # All providers failed or unavailable
        if self._fallback_to_deterministic and self.providers:
            logger.warning("All AI providers failed, using deterministic fallback")
            return self.providers[0]._fallback_assessment(snapshot, "All providers failed")
        
        # Return neutral assessment
        return AIAssessment(
            provider=AIProviderType.LOCAL,
            assessment="neutral",
            confidence=0.0,
            explanation="No AI providers available",
            timestamp=now_ms(),
        )
    
    def set_fallback(self, enabled: bool) -> None:
        self._fallback_to_deterministic = enabled
    
    def get_stats(self) -> list[dict]:
        return [p.get_stats() for p in self.providers]