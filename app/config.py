from __future__ import annotations

from typing import Literal

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    anthropic_api_key: str = ""
    model: str = "claude-opus-4-20250514"
    approval_mode: Literal["human_approval", "autonomous"] = "human_approval"
    max_iterations: int = 15
    data_path: str = "data/mock_hotel_data.json"
    simulated_today: str = ""  # Override today's date for demo (YYYY-MM-DD), empty = use real date

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
