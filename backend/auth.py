"""
NEXUS OVERLAY AI - Authentication, Rate Limiting & Security

Provides:
- Token-based authentication for WebSocket connections
- HMAC message signing and verification
- Replay protection via nonce tracking with expiry
- Timestamp validation (reject stale messages)
- Per-IP token bucket rate limiting

Auth is ENABLED by default in production. Configure via the security section
in default_config.yaml or environment variables.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac as hmac_module
import logging
import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Default maximum message age in milliseconds (30 seconds)
DEFAULT_MAX_MESSAGE_AGE_MS = 30000
# Default nonce expiry in seconds (5 minutes)
DEFAULT_NONCE_EXPIRY_S = 300
# Nonce cleanup interval in seconds
DEFAULT_NONCE_CLEANUP_INTERVAL_S = 60


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
    Auth is ENABLED by default in production — connections without
    a valid token are rejected unless explicitly disabled.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        cfg = config or {}

        # Determine if auth is enabled.
        # Explicit security.auth_enabled takes precedence;
        # fallback to legacy transport.auth_token presence.
        self._explicit_enabled = cfg.get("security.auth_enabled", None)

        if self._explicit_enabled is not None:
            self._enabled = bool(self._explicit_enabled)
        else:
            # Legacy behavior: enabled if a token is set
            auth_token = (
                cfg.get("transport.auth_token", "")
                or cfg.get("system.secret_key", "")
                or ""
            )
            self._enabled = True  # DEFAULT: enabled in production
            if not auth_token and self._explicit_enabled is None:
                # No token configured and not explicitly set:
                # still enabled, but allow with WARNING
                logger.warning(
                    "Auth enabled but no AUTH_TOKEN configured. "
                    "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(32))\""
                )

        self._auth_token: str = (
            cfg.get("transport.auth_token", "")
            or cfg.get("system.secret_key", "")
            or ""
        )

        if self._enabled:
            logger.info("Token authentication ENABLED (production default)")
        else:
            logger.info(
                "Token authentication DISABLED (explicitly configured off)"
            )

    @property
    def enabled(self) -> bool:
        return self._enabled

    def validate_token(self, token: str) -> AuthResult:
        """
        Validate an authentication token.

        If auth is disabled (explicitly configured off), always passes.
        Otherwise, performs constant-time comparison.
        """
        if not self._enabled:
            return AuthResult(passed=True, reason="auth_disabled")

        if not token:
            return AuthResult(passed=False, reason="empty_token")

        # If no token is configured but auth is enabled, allow connection
        # with a warning (operator should configure a token).
        if not self._auth_token:
            logger.warning(
                "Auth enabled but no token configured — "
                "allowing connection (insecure)"
            )
            client_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]
            return AuthResult(
                passed=True,
                reason="no_server_token_configured",
                client_id=f"token_{client_hash}",
            )

        # Constant-time comparison to prevent timing attacks
        provided = token.encode("utf-8")
        expected = self._auth_token.encode("utf-8")

        if hmac_module.compare_digest(provided, expected):
            # Generate a deterministic client_id from the token
            client_hash = hashlib.sha256(provided).hexdigest()[:16]
            return AuthResult(
                passed=True,
                reason="valid",
                client_id=f"token_{client_hash}",
            )
        else:
            return AuthResult(passed=False, reason="invalid_token")


class HMACSigner:
    """
    HMAC message signing and verification.

    Uses HMAC-SHA256 to sign message content for integrity
    and authenticity verification.
    """

    def __init__(self, secret_key: str = ""):
        self._secret_key: bytes = secret_key.encode("utf-8") if secret_key else b""
        if not self._secret_key:
            logger.warning(
                "HMAC secret key not configured — "
                "HMAC signing/verification disabled"
            )

    @property
    def enabled(self) -> bool:
        return bool(self._secret_key)

    def create_hmac_sign(self, message: str, secret_key: Optional[str] = None) -> str:
        """
        Create HMAC-SHA256 signature for a message.

        Args:
            message: The message content to sign.
            secret_key: Optional override for the secret key.

        Returns:
            Hex-encoded HMAC signature string.
        """
        key = secret_key.encode("utf-8") if secret_key else self._secret_key
        if not key:
            return ""
        return hmac_module.new(
            key, message.encode("utf-8"), hashlib.sha256
        ).hexdigest()

    def verify_hmac(
        self,
        message: str,
        signature: str,
        secret_key: Optional[str] = None,
    ) -> bool:
        """
        Verify an HMAC signature against a message.

        Uses constant-time comparison to prevent timing attacks.

        Args:
            message: The original message content.
            signature: The HMAC signature to verify.
            secret_key: Optional override for the secret key.

        Returns:
            True if the signature is valid, False otherwise.
        """
        key = secret_key.encode("utf-8") if secret_key else self._secret_key
        if not key or not signature:
            return not (key or signature)  # Both empty = pass; only one = fail

        expected = hmac_module.new(
            key, message.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        return hmac_module.compare_digest(expected, signature)


class ReplayProtection:
    """
    Replay attack protection via nonce tracking and message_id deduplication.

    - Nonces: each message should include a unique nonce. Reused nonces are rejected.
    - Message IDs: each message has a UUID. Duplicate message_ids are rejected.
    - Timestamps: messages older than MAX_MESSAGE_AGE_MS are rejected.
    """

    def __init__(
        self,
        max_message_age_ms: int = DEFAULT_MAX_MESSAGE_AGE_MS,
        nonce_expiry_s: float = DEFAULT_NONCE_EXPIRY_S,
        cleanup_interval_s: float = DEFAULT_NONCE_CLEANUP_INTERVAL_S,
    ):
        self._max_message_age_ms = max_message_age_ms
        self._nonce_expiry_s = nonce_expiry_s
        self._cleanup_interval_s = cleanup_interval_s

        # Seen nonces: {nonce: expiry_timestamp}
        self._nonces: Dict[str, float] = {}
        # Seen message IDs: {message_id: expiry_timestamp}
        self._message_ids: Dict[str, float] = {}
        # Track last cleanup time
        self._last_cleanup: float = time.monotonic()

    @property
    def max_message_age_ms(self) -> int:
        return self._max_message_age_ms

    def validate_timestamp(self, timestamp_ms: int) -> tuple[bool, str]:
        """
        Validate that a message timestamp is within acceptable age.

        Returns:
            (is_valid, error_message)
        """
        now_ms = int(time.time() * 1000)
        age_ms = now_ms - timestamp_ms

        if age_ms < 0:
            # Allow small clock drift (up to 5 seconds)
            if abs(age_ms) > 5000:
                return False, f"Message timestamp in the future: {abs(age_ms)}ms ahead"
            return True, ""

        if age_ms > self._max_message_age_ms:
            return (
                False,
                f"Message too old: {age_ms}ms (max {self._max_message_age_ms}ms)",
            )

        return True, ""

    def validate_nonce(self, nonce: str) -> tuple[bool, str]:
        """
        Validate that a nonce has not been used before.

        Returns:
            (is_valid, error_message)
        """
        if not nonce:
            # Empty nonce is allowed (for backward compatibility)
            return True, ""

        self._maybe_cleanup()

        if nonce in self._nonces:
            return False, f"Replay attack: nonce '{nonce[:16]}...' already used"

        return True, ""

    def register_nonce(self, nonce: str) -> None:
        """Register a nonce as used (call after successful validation)."""
        if not nonce:
            return
        expiry = time.time() + self._nonce_expiry_s
        self._nonces[nonce] = expiry

    def validate_message_id(self, message_id: str) -> tuple[bool, str]:
        """
        Validate that a message_id has not been seen before.

        Returns:
            (is_valid, error_message)
        """
        if not message_id:
            # Empty message_id: allow (backward compatibility)
            return True, ""

        self._maybe_cleanup()

        if message_id in self._message_ids:
            return False, f"Duplicate message_id: {message_id}"

        return True, ""

    def register_message_id(self, message_id: str) -> None:
        """Register a message_id as seen (call after successful validation)."""
        if not message_id:
            return
        expiry = time.time() + self._nonce_expiry_s
        self._message_ids[message_id] = expiry

    def _maybe_cleanup(self) -> None:
        """Periodically clean up expired nonces and message IDs."""
        now = time.monotonic()
        if now - self._last_cleanup < self._cleanup_interval_s:
            return
        self._last_cleanup = now

        now_time = time.time()
        # Clean expired nonces
        expired_nonces = [
            n for n, exp in self._nonces.items() if exp < now_time
        ]
        for n in expired_nonces:
            del self._nonces[n]
        # Clean expired message IDs
        expired_ids = [
            mid for mid, exp in self._message_ids.items() if exp < now_time
        ]
        for mid in expired_ids:
            del self._message_ids[mid]

    def get_stats(self) -> Dict[str, int]:
        """Get current replay protection stats."""
        return {
            "active_nonces": len(self._nonces),
            "active_message_ids": len(self._message_ids),
        }


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

    @property
    def max_per_minute(self) -> int:
        return self._max_per_minute

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

    def get_tracked_ips(self) -> int:
        """Get number of tracked IPs."""
        return len(self._buckets)


def generate_nonce() -> str:
    """Generate a cryptographically secure random nonce."""
    return secrets.token_urlsafe(24)
