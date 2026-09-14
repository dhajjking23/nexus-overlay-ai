"""
NEXUS OVERLAY AI - Configuration Loader
Loads YAML config with environment variable overrides
"""
from __future__ import annotations
import os
from pathlib import Path
from typing import Any
import yaml


class Config:
    """Configuration manager with YAML + env override support"""
    
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
        """Load configuration from YAML file"""
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
                self._config = yaml.safe_load(f) or {}
        else:
            self._config = {}
        
        # Override with environment variables
        self._apply_env_overrides()
    
    def _apply_env_overrides(self) -> None:
        """Apply environment variable overrides"""
        env_mappings = {
            "TRANSPORT_HOST": ("transport", "host"),
            "TRANSPORT_PORT": ("transport", "port"),
            "DATABASE_PATH": ("database", "path"),
            "LOG_LEVEL": ("system", "log_level"),
            "OPENAI_API_KEY": ("ai", "providers", "openai", "api_key"),
            "ANTHROPIC_API_KEY": ("ai", "providers", "claude", "api_key"),
            "SECRET_KEY": ("system", "secret_key"),
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