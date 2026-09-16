"""
NEXUS OVERLAY AI - Configuration Loader
Loads YAML config with environment variable overrides.

Includes Config Lock (Phase 5):
  - Computes SHA256 hash of config at load time
  - Stores hash and provides check_config_changed()
  - Logs WARNING (or optionally refuses) if config changes at runtime
"""
from __future__ import annotations

import hashlib
import logging
import os
import sys
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger("nexus_overlay.config_loader")


class Config:
    """Configuration manager with YAML + env override support + config lock."""

    _instance: Config | None = None
    _config: dict[str, Any] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._config:
            self.load()

    def load(self, config_path: str | None = None) -> None:
        """Load configuration from YAML file and compute config hash."""
        self._config_path = config_path
        if config_path is None:
            # Try default locations
            for path in [
                Path("config/default_config.yaml"),
                Path("../config/default_config.yaml"),
                Path("/sdcard/Hermes/nexus-overlay-ai/config/default_config.yaml"),
            ]:
                if path.exists():
                    config_path = str(path)
                    break

        if config_path and Path(config_path).exists():
            with open(config_path, "r") as f:
                raw_content = f.read()
            self._config = yaml.safe_load(raw_content) or {}
            self._config_raw = raw_content
        else:
            self._config = {}
            self._config_raw = ""

        # Compute and store SHA256 hash of the config
        self._config_hash = self._compute_hash(self._config_raw)

        # Override with environment variables
        self._apply_env_overrides()

        # Log config hash if configured
        self._log_config_hash()

    @staticmethod
    def _compute_hash(content: str) -> str:
        """Compute SHA256 hash of the config content string."""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    @property
    def config_hash(self) -> str:
        """The SHA256 hash of the loaded config file."""
        return self._config_hash

    def check_config_changed(self) -> bool:
        """
        Re-read the config file and check if the hash has changed.

        Returns True if the config has changed since last load.
        Logs a WARNING if a change is detected.
        """
        if not self._config_path:
            # Can't check if we don't know the path
            return False

        try:
            path = Path(self._config_path)
            if not path.exists():
                logger.warning(f"Config file not found at {self._config_path}")
                return False

            with open(path, "r") as f:
                new_content = f.read()

            new_hash = self._compute_hash(new_content)

            if new_hash != self._config_hash:
                logger.warning(
                    f"CONFIG CHANGE DETECTED! "
                    f"Old hash: {self._config_hash[:16]}... "
                    f"New hash: {new_hash[:16]}... "
                    f"File: {self._config_path}"
                )
                return True

            return False

        except Exception as e:
            logger.warning(f"Failed to check config change: {e}")
            return False

    def reload_if_changed(self) -> bool:
        """
        Re-read config file if it has changed.

        Returns True if config was reloaded (i.e., it changed).
        Optionally refuses to continue if configured via config_lock.refuse_on_change.
        """
        if not self.check_config_changed():
            return False

        refuse = self._config.get("config_lock", {}).get("refuse_on_change", False)

        if refuse:
            logger.critical(
                "CONFIG CHANGED and config_lock.refuse_on_change=true. "
                "Refusing to continue. Restart with the new config."
            )
            sys.exit(1)

        # Reload
        old_hash = self._config_hash
        self.load(self._config_path)
        logger.warning(
            f"Config reloaded after change. "
            f"Hash: {old_hash[:16]}... → {self._config_hash[:16]}..."
        )
        return True

    def _log_config_hash(self) -> None:
        """Log the config hash at startup for audit trail."""
        log_hash = self._config.get("config_lock", {}).get("log_hash_on_startup", True)
        if log_hash and self._config_hash:
            logger.info(
                f"Config SHA256: {self._config_hash} "
                f"(file: {self._config_path or 'inline'})"
            )

    def _apply_env_overrides(self) -> None:
        """Apply environment variable overrides"""
        env_mappings = {
            "TRANSPORT_HOST": ("transport", "host"),
            "TRANSPORT_PORT": ("transport", "port"),
            "DATABASE_PATH": ("database", "path"),
            "LOG_LEVEL": ("system", "log_level"),
            "OPENROUTER_API_KEY": ("ai", "providers", "openrouter", "api_key"),
            "OPENAI_API_KEY": ("ai", "providers", "openai", "api_key"),
            "ANTHROPIC_API_KEY": ("ai", "providers", "claude", "api_key"),
            "SECRET_KEY": ("system", "secret_key"),
            "AUTH_TOKEN": ("transport", "auth_token"),
            "HEALTH_PORT": ("transport", "health_port"),
        }

        for env_var, config_path in env_mappings.items():
            value = os.getenv(env_var)
            if value:
                self._set_nested(config_path, value)

    def _set_nested(self, path: tuple, value: Any) -> None:
        """Set nested config value"""
        current = self._config
        for key in path[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        current[path[-1]] = value

    def get(self, path: str, default: Any = None) -> Any:
        """Get config value by dot-separated path (e.g., 'transport.port')"""
        keys = path.split(".")
        current = self._config
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return default
        return current

    def get_section(self, section: str) -> dict:
        """Get entire config section"""
        return self._config.get(section, {})

    def all(self) -> dict:
        """Get all config"""
        return self._config.copy()

    @classmethod
    def reset(cls) -> None:
        """Reset singleton (for testing)"""
        cls._instance = None
        cls._config = {}


def get_config() -> Config:
    """Get global config instance"""
    return Config()
