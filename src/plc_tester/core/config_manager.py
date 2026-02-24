"""Configuration manager for persisting application settings to JSON.

Saves and loads S7 and OPC UA tab settings including connection parameters
and variable table contents.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Default config location: next to the user's working directory
_CONFIG_DIR = Path.home() / ".plc_tester"
_CONFIG_FILE = _CONFIG_DIR / "config.json"


def _default_config() -> dict[str, Any]:
    """Return default configuration structure."""
    return {
        "s7": {
            "ip": "192.168.0.1",
            "rack": 0,
            "slot": 1,
            "interval_ms": 1000,
            "cyclic_active": False,
            "variables": [
                {"type": "INT", "area": "DB", "address": "DB1.DBW0"}
                for _ in range(10)
            ],
        },
        "opcua": {
            "url": "opc.tcp://192.168.0.1:4840",
            "username": "",
            "password": "",
            "interval_ms": 1000,
            "cyclic_active": False,
            "nodes": [
                {"node_id": ""}
                for _ in range(10)
            ],
        },
    }


def load_config() -> dict[str, Any]:
    """Load configuration from disk, returning defaults if file is missing.

    Returns:
        Configuration dictionary with ``s7`` and ``opcua`` sections.
    """
    if not _CONFIG_FILE.exists():
        logger.info("Config file not found at %s – using defaults.", _CONFIG_FILE)
        return _default_config()

    try:
        with _CONFIG_FILE.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        logger.info("Config loaded from %s", _CONFIG_FILE)
        # Merge with defaults to ensure all keys exist
        defaults = _default_config()
        for section in ("s7", "opcua"):
            if section not in data:
                data[section] = defaults[section]
            else:
                for key, value in defaults[section].items():
                    data[section].setdefault(key, value)
        return data
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to load config: %s – using defaults.", exc)
        return _default_config()


def save_config(config: dict[str, Any]) -> None:
    """Save configuration dictionary to disk.

    Args:
        config: Configuration dictionary to persist.
    """
    try:
        _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with _CONFIG_FILE.open("w", encoding="utf-8") as fh:
            json.dump(config, fh, indent=2, ensure_ascii=False)
        logger.info("Config saved to %s", _CONFIG_FILE)
    except OSError as exc:
        logger.error("Failed to save config: %s", exc)
