from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Settings:
    anthropic_api_key: str = ""
    model: str = "claude-sonnet-4-20250514"
    approval_mode: str = "human_approval"
    max_iterations: int = 15
    data_path: str = "data/mock_hotel_data.json"
    simulated_today: str = ""
    host: str = "0.0.0.0"
    port: int = 8000


def _load_dotenv() -> None:
    """Load .env file into os.environ if it exists."""
    env_path = Path(".env")
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def _load_toml(config_path: str) -> dict:
    """Load config.toml and return a flat dict of settings."""
    path = Path(config_path)
    if not path.exists():
        return {}
    with open(path, "rb") as f:
        data = tomllib.load(f)
    # Flatten nested sections into a single dict
    flat: dict = {}
    for section in data.values():
        if isinstance(section, dict):
            flat.update(section)
    return flat


def load_settings(config_path: str = "config.toml", **overrides) -> Settings:
    """Load settings: .env for secrets, config.toml for app config, overrides win."""
    _load_dotenv()
    toml_values = _load_toml(config_path)

    def _get(key: str, default):
        # Overrides > toml > default
        if key in overrides:
            return overrides[key]
        if key in toml_values:
            return toml_values[key]
        return default

    defaults = Settings()
    return Settings(
        anthropic_api_key=overrides.get("anthropic_api_key", os.environ.get("ANTHROPIC_API_KEY", "")),
        model=_get("model", defaults.model),
        approval_mode=_get("approval_mode", defaults.approval_mode),
        max_iterations=int(_get("max_iterations", defaults.max_iterations)),
        data_path=_get("data_path", defaults.data_path),
        simulated_today=_get("simulated_today", defaults.simulated_today),
        host=_get("host", defaults.host),
        port=int(_get("port", defaults.port)),
    )
