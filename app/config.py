from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Settings:
    anthropic_api_key: str = ""
    model: str = "claude-sonnet-4-20250514"
    approval_mode: str = "human_approval"  # "human_approval" or "autonomous"
    max_iterations: int = 15
    data_path: str = "data/mock_hotel_data.json"
    simulated_today: str = ""  # Override today's date for demo (YYYY-MM-DD)


def _load_dotenv() -> None:
    """Load .env file into os.environ if it exists. No dependencies."""
    env_path = Path(".env")
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def load_settings(**overrides) -> Settings:
    """Load settings from environment variables, with optional overrides."""
    _load_dotenv()
    return Settings(
        anthropic_api_key=overrides.get("anthropic_api_key", os.environ.get("ANTHROPIC_API_KEY", "")),
        model=overrides.get("model", os.environ.get("MODEL", "claude-sonnet-4-20250514")),
        approval_mode=overrides.get("approval_mode", os.environ.get("APPROVAL_MODE", "human_approval")),
        max_iterations=int(overrides.get("max_iterations", os.environ.get("MAX_ITERATIONS", "15"))),
        data_path=overrides.get("data_path", os.environ.get("DATA_PATH", "data/mock_hotel_data.json")),
        simulated_today=overrides.get("simulated_today", os.environ.get("SIMULATED_TODAY", "")),
    )
