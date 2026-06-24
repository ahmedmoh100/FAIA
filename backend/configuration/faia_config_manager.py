"""
FAIA Configuration Manager
Centralized configuration system for all FAIA services and models
"""

import json
import re
import os
import logging
from typing import Dict, List, Optional, Any, Union
from pathlib import Path

logger = logging.getLogger(__name__)


class FAIAConfigManager:
    def __init__(self, config_path: Union[str, Path, None] = None):
        if config_path is None:
            config_path = Path(__file__).parent / "faia_config.json"
        self.config_path = Path(config_path)
        self.config = self.load_config()

    def load_config(self) -> Dict[str, Any]:
        """Load configuration from JSON file with environment variable substitution."""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config_text = f.read()
                config_text = self._substitute_env_vars(config_text)
                return json.loads(config_text)
        except FileNotFoundError:
            logger.warning("Config file %s not found. Using default config.", self.config_path)
            return self.get_default_config()
        except json.JSONDecodeError as e:
            logger.warning("Error parsing config file: %s. Using default config.", e)
            return self.get_default_config()

    def _substitute_env_vars(self, config_text: str) -> str:
        """Replace ${VAR_NAME} placeholders with environment variable values."""
        def replace_var(match):
            var_name = match.group(1)
            value = os.getenv(var_name)
            if value is None:
                logger.debug("Environment variable '%s' not set, keeping placeholder", var_name)
                return match.group(0)
            # Escape backslashes and quotes for JSON safety (handles Windows paths and quoted values)
            return value.replace('\\', '\\\\').replace('"', '\\"')

        return re.sub(r'\$\{([^}]+)\}', replace_var, config_text)

    def get_default_config(self) -> Dict[str, Any]:
        """Return default configuration if file is missing."""
        return {
            "system": {"name": "FAIA", "version": "1.0.0"},
            "models": {"qwen": {"type": "local"}},
            "prompts": {"system_prompts": {"default": "You are FAIA, a helpful AI assistant."}},
            "response_cleaning": {"enabled": True, "training_artifacts": []},
            "fallback": {"primary_model": "qwen"},
            "rag": {"enabled": True},
            "performance": {"cache": {"enabled": True}, "database": {}},
            "security": {}
        }

    def get_rag_config(self) -> Dict[str, Any]:
        """Get RAG configuration."""
        return self.config.get("rag", {})

    def is_cache_enabled(self) -> bool:
        """Check if caching is enabled."""
        return self.config.get("performance", {}).get("cache", {}).get("enabled", True)

    def is_rag_enabled(self) -> bool:
        """Check if RAG is enabled."""
        return self.config.get("rag", {}).get("enabled", True)

    def get_moderation_config(self) -> Dict[str, Any]:
        """Get moderation configuration."""
        return self.config.get("moderation", {})

    def is_moderation_enabled(self) -> bool:
        """Check if moderation is enabled."""
        return self.config.get("moderation", {}).get("enabled", True)

    def get_moderation_risk_levels(self) -> Dict[str, Any]:
        """Get moderation risk level definitions."""
        return self.config.get("moderation", {}).get("risk_levels", {})

    def get_moderation_categories(self) -> Dict[str, List[str]]:
        """Get moderation categories and their keywords."""
        return self.config.get("moderation", {}).get("categories", {})

    def detect_moderation_category(self, content: str) -> Optional[str]:
        """Detect which moderation category content falls into.
        Uses word-boundary matching to avoid false positives (e.g. 'kill' in 'skill')."""
        content_lower = content.lower()
        categories = self.get_moderation_categories()

        for category, keywords in categories.items():
            for keyword in keywords:
                if re.search(r'\b' + re.escape(keyword.lower()) + r'\b', content_lower):
                    return category
        return "other"


# Global instance
config_manager = FAIAConfigManager()


# Convenience functions
def get_config() -> FAIAConfigManager:
    """Get the global config manager instance."""
    return config_manager


def get_rag_config() -> Dict[str, Any]:
    """Get RAG config using global config."""
    return config_manager.get_rag_config()


def get_moderation_config() -> Dict[str, Any]:
    """Get moderation config using global config."""
    return config_manager.get_moderation_config()
