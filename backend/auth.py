"""
NEXUS OVERLAY AI - Authentication & Rate Limiting

Provides token-based authentication and per-IP rate limiting
for WebSocket connections. Auth is optional: if no AUTH_TOKEN is
configured, all connections are allowed.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class AuthResult:
    """Result of an authentication check."""
    passed: bool
    reason: str = ""
    client_id: str = ""


class TokenAuth:
    """
    Token-based authentication for WebSocket connections.
    
    Validates incoming tokens against a configured AUTH_TOKEN.
    Uses constant-time comparison to prevent timing attacks.
    If no token is configured, all connections are allowed.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        cfg = config or {}
        # Support both transport.auth_token and system.secret_key
        self._auth_token: str = (
            cfg.get("transport.auth_token", "")
            or cfg.get("system.secret_key", "")
            or ""
        )
        self._enabled = bool(self._auth_token)
        if self._enabled:
            logger.info("Token authentication enabled")
        else:
            logger.info("Token authentication disabled (no AUTH_TOKEN configured)")

    @property
    def enabled(self) -> bool:
        return self._enabled

    def validate_token(self, token: str) -> AuthResult:
        """
        Validate an authentication token.
        
        If auth is disabled (no token configured), always passes.
        Otherwise, performs constant-time comparison.
        """
        if not self._enabled:
            return AuthResult(passed=True, reason="auth_disabled")

        if not token:
            return AuthResult(passed=False, reason="empty_token")

        # Constant-time comparison to prevent timing attacks
        provided = token.encode("utf-8")
        expected = self._auth_token.encode("utf-8")

        if hmac.compare_digest(provided, expected):
            # Generate a deterministic client_id from the token
            client_hash = hashlib.sha256(provided).hexdigest()[:16]
            return AuthResult(
                passed=True,
                reason="valid",
                client_id=f"token_{client_hash}",
            )
        else:
            return AuthResult(passed=False, reason="invalid_token")


class RateLimiter:
    """
    Per-IP token bucket rate limiter.
    
    Each IP gets a bucket of tokens that refills over time.
    When the bucket is empty, requests are rejected.
    """

    def __init__(self, max_per_minute: int = 120, burst: int = 20):
        """
        Args:
            max_per_minute: Maximum requests per minute (sustained rate).
            burst: Maximum burst size (instant refill cap).
        """
        self._max_per_minute = max(1, max_per_minute)
        self._burst = max(1, burst)
        self._refill_rate = self._max_per_minute / 60.0  # tokens per second
        # {ip: (tokens_remaining, last_refill_time)}
        self._buckets: Dict[str, list] = {}
        self._lock = asyncio.Lock()

    def check_rate_limit(self, ip: str) -> bool:
        """
        Check if the given IP is within rate limits.
        Synchronous check using token bucket algorithm.
        Returns True if allowed, False if rate limited.
        """
        now = time.monotonic()

        if ip not in self._buckets:
            self._buckets[ip] = [float(self._burst) - 1.0, now]
            return True

        bucket = self._buckets[ip]
        tokens, last_time = bucket[0], bucket[1]

        # Refill tokens based on elapsed time
        elapsed = now - last_time
        tokens = min(self._burst, tokens + elapsed * self._refill_rate)

        if tokens < 1.0:
            bucket[0] = tokens
            bucket[1] = now
            return False

        # Consume one token
        bucket[0] = tokens - 1.0
        bucket[1] = now
        return True

    def cleanup_stale(self, max_age: float = 300.0) -> int:
        """
        Remove buckets that haven't been used in max_age seconds.
        Returns number of entries removed.
        """
        now = time.monotonic()
        stale_ips = [
            ip for ip, (_, last_time) in self._buckets.items()
            if now - last_time > max_age
        ]
        for ip in stale_ips:
            del self._buckets[ip]
        return len(stale_ips)

    def get_bucket_info(self, ip: str) -> Optional[Dict[str, Any]]:
        """Get current bucket state for an IP (for monitoring)."""
        if ip not in self._buckets:
            return None
        tokens, last_time = self._buckets[ip]
        return {
            "tokens": round(tokens, 2),
            "last_time": last_time,
            "max_tokens": self._burst,
        }
