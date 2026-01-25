"""
Configuration Management for Trace

This module handles persistent configuration storage for Trace settings.
Settings are stored in a JSON file at ~/Library/Application Support/Trace/config.json

Configuration schema:
    {
        "appearance": {
            "show_in_dock": false,
            "launch_at_login": true
        },
        "capture": {
            "summarization_interval_minutes": 60,
            "daily_revision_hour": 3,
            "blocked_apps": [],
            "blocked_domains": []
        },
        "notifications": {
            "weekly_digest_enabled": true,
            "weekly_digest_day": "sunday"
        },
        "shortcuts": {
            "open_trace": "CommandOrControl+Shift+T"
        },
        "data": {
            "retention_months": null
        },
        "api_key": null
    }
"""

import json
import logging
import os
from pathlib import Path
from typing import Any

from src.core.paths import DATA_ROOT

logger = logging.getLogger(__name__)

# Config file path
CONFIG_PATH: Path = DATA_ROOT / "config.json"

# Default configuration values
DEFAULT_CONFIG: dict[str, Any] = {
    "appearance": {
        "show_in_dock": False,  # Default: OFF (menu bar only)
        "launch_at_login": True,  # Default: ON (start at login)
    },
    "capture": {
        "summarization_interval_minutes": 60,
        "daily_revision_hour": 3,
        "blocked_apps": [],
        "blocked_domains": [],
        "power_saving_enabled": True,  # Reduce capture frequency on battery (P13-05)
        "dedup_threshold": 5,  # Perceptual hash threshold for deduplication (P13-06)
        "jpeg_quality": 85,  # JPEG quality for screenshot compression (P13-07)
    },
    "models": {
        # P13-08: Model selection configuration
        "triage": "gpt-5-nano-2025-08-07",  # Fast model for frame triage
        "hourly": "gpt-5-mini-2025-08-07",  # Medium model for hourly summarization
        "daily": "gpt-5.2-2025-12-11",  # Full model for daily revision
        "chat": "gpt-5-mini-2025-08-07",  # Model for chat/query responses
    },
    "notifications": {
        "weekly_digest_enabled": True,
        "weekly_digest_day": "sunday",
    },
    "shortcuts": {
        "open_trace": "CommandOrControl+Shift+T",
    },
    "data": {
        "retention_months": None,  # None = keep forever
    },
    "api_key": None,
}

# Valid values for certain settings
VALID_SUMMARIZATION_INTERVALS = [30, 60, 120, 240]  # minutes
VALID_DAILY_REVISION_HOURS = list(range(24))  # 0-23
VALID_WEEKLY_DIGEST_DAYS = [
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
]
VALID_RETENTION_MONTHS = [None, 6, 12, 24]  # None = forever

# Valid model options (P13-08)
VALID_MODELS = {
    "triage": [
        "gpt-5-nano-2025-08-07",
        "gpt-4o-mini",
    ],
    "hourly": [
        "gpt-5-mini-2025-08-07",
        "gpt-4o-mini",
        "gpt-4o",
    ],
    "daily": [
        "gpt-5.2-2025-12-11",
        "gpt-4o",
        "gpt-5-mini-2025-08-07",
    ],
    "chat": [
        "gpt-5-mini-2025-08-07",
        "gpt-4o-mini",
        "gpt-4o",
    ],
}


def _deep_merge(base: dict, override: dict) -> dict:
    """Deep merge two dictionaries, preferring values from override."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config() -> dict[str, Any]:
    """
    Load configuration from file, merging with defaults.

    Returns:
        Complete configuration dictionary with defaults for missing values.
    """
    if not CONFIG_PATH.exists():
        logger.info(f"Config file not found, using defaults: {CONFIG_PATH}")
        return DEFAULT_CONFIG.copy()

    try:
        with open(CONFIG_PATH) as f:
            user_config = json.load(f)

        # Merge with defaults to ensure all keys exist
        config = _deep_merge(DEFAULT_CONFIG, user_config)
        logger.debug(f"Loaded config from {CONFIG_PATH}")
        return config
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in config file: {e}")
        return DEFAULT_CONFIG.copy()
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        return DEFAULT_CONFIG.copy()


def save_config(config: dict[str, Any]) -> bool:
    """
    Save configuration to file.

    Args:
        config: Configuration dictionary to save

    Returns:
        True if saved successfully, False otherwise
    """
    try:
        # Ensure parent directory exists
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)

        with open(CONFIG_PATH, "w") as f:
            json.dump(config, f, indent=2)

        logger.info(f"Saved config to {CONFIG_PATH}")
        return True
    except Exception as e:
        logger.error(f"Failed to save config: {e}")
        return False


def get_config_value(key_path: str, default: Any = None) -> Any:
    """
    Get a configuration value by dot-separated path.

    Args:
        key_path: Dot-separated path like "capture.summarization_interval_minutes"
        default: Default value if key doesn't exist

    Returns:
        The configuration value or default
    """
    config = load_config()
    keys = key_path.split(".")

    value = config
    for key in keys:
        if isinstance(value, dict) and key in value:
            value = value[key]
        else:
            return default

    return value


def set_config_value(key_path: str, value: Any) -> bool:
    """
    Set a configuration value by dot-separated path.

    Args:
        key_path: Dot-separated path like "capture.summarization_interval_minutes"
        value: Value to set

    Returns:
        True if saved successfully, False otherwise
    """
    config = load_config()
    keys = key_path.split(".")

    # Navigate to the parent of the target key
    current = config
    for key in keys[:-1]:
        if key not in current:
            current[key] = {}
        current = current[key]

    # Set the value
    current[keys[-1]] = value

    return save_config(config)


def get_api_key() -> str | None:
    """
    Get the OpenAI API key.

    Checks config first, then falls back to environment variable.

    Returns:
        API key string or None if not set
    """
    # First check config
    api_key = get_config_value("api_key")
    if api_key:
        return api_key

    # Fall back to environment variable
    return os.environ.get("OPENAI_API_KEY")


def set_api_key(api_key: str) -> bool:
    """
    Set the OpenAI API key.

    Saves to config and also sets the environment variable for current session.

    Args:
        api_key: The API key to set

    Returns:
        True if saved successfully
    """
    # Validate format
    import re

    if not re.match(r"^sk-(?:proj-)?[A-Za-z0-9_-]{20,}$", api_key):
        raise ValueError("Invalid API key format")

    # Save to config
    result = set_config_value("api_key", api_key)

    # Also set environment variable for current session
    if result:
        os.environ["OPENAI_API_KEY"] = api_key

    return result


def get_appearance_config() -> dict[str, Any]:
    """Get appearance settings."""
    return get_config_value("appearance", DEFAULT_CONFIG["appearance"])


def get_capture_config() -> dict[str, Any]:
    """Get capture settings."""
    return get_config_value("capture", DEFAULT_CONFIG["capture"])


def get_notifications_config() -> dict[str, Any]:
    """Get notification settings."""
    return get_config_value("notifications", DEFAULT_CONFIG["notifications"])


def get_shortcuts_config() -> dict[str, Any]:
    """Get shortcut settings."""
    return get_config_value("shortcuts", DEFAULT_CONFIG["shortcuts"])


def get_data_config() -> dict[str, Any]:
    """Get data management settings."""
    return get_config_value("data", DEFAULT_CONFIG["data"])


def get_models_config() -> dict[str, str]:
    """Get model selection settings (P13-08)."""
    return get_config_value("models", DEFAULT_CONFIG["models"])


def get_model(task: str) -> str:
    """
    Get the configured model for a specific task.

    Args:
        task: One of 'triage', 'hourly', 'daily', 'chat'

    Returns:
        Model name string
    """
    models = get_models_config()
    return models.get(task, DEFAULT_CONFIG["models"].get(task, "gpt-4o-mini"))


def validate_config(config: dict[str, Any]) -> list[str]:
    """
    Validate configuration values.

    Args:
        config: Configuration dictionary to validate

    Returns:
        List of validation error messages (empty if valid)
    """
    errors = []

    # Validate summarization interval
    interval = config.get("capture", {}).get("summarization_interval_minutes")
    if interval is not None and interval not in VALID_SUMMARIZATION_INTERVALS:
        errors.append(
            f"Invalid summarization_interval_minutes: {interval}. "
            f"Must be one of {VALID_SUMMARIZATION_INTERVALS}"
        )

    # Validate daily revision hour
    hour = config.get("capture", {}).get("daily_revision_hour")
    if hour is not None and hour not in VALID_DAILY_REVISION_HOURS:
        errors.append(f"Invalid daily_revision_hour: {hour}. Must be 0-23")

    # Validate weekly digest day
    day = config.get("notifications", {}).get("weekly_digest_day")
    if day is not None:
        if not isinstance(day, str):
            errors.append(f"weekly_digest_day must be a string, got {type(day).__name__}")
        elif day.lower() not in VALID_WEEKLY_DIGEST_DAYS:
            errors.append(
                f"Invalid weekly_digest_day: {day}. Must be one of {VALID_WEEKLY_DIGEST_DAYS}"
            )

    # Validate retention months
    retention = config.get("data", {}).get("retention_months")
    if retention is not None and retention not in VALID_RETENTION_MONTHS:
        errors.append(
            f"Invalid retention_months: {retention}. Must be one of {VALID_RETENTION_MONTHS}"
        )

    return errors


def reset_to_defaults() -> bool:
    """
    Reset configuration to default values.

    Returns:
        True if saved successfully
    """
    return save_config(DEFAULT_CONFIG.copy())


if __name__ == "__main__":
    import fire

    def show():
        """Show current configuration."""
        return load_config()

    def get(key_path: str):
        """Get a config value by path (e.g., 'capture.summarization_interval_minutes')."""
        return get_config_value(key_path)

    def set_value(key_path: str, value: Any):
        """Set a config value by path."""
        return set_config_value(key_path, value)

    def reset():
        """Reset to default configuration."""
        return reset_to_defaults()

    def validate():
        """Validate current configuration."""
        config = load_config()
        errors = validate_config(config)
        return {"valid": len(errors) == 0, "errors": errors}

    fire.Fire(
        {
            "show": show,
            "get": get,
            "set": set_value,
            "reset": reset,
            "validate": validate,
        }
    )
