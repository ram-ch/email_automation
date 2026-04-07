from app.config import load_settings


def test_load_settings_from_toml(tmp_path, monkeypatch):
    """Settings load from config.toml when it exists."""
    toml_content = """
[agent]
model = "claude-test-model"
approval_mode = "autonomous"
max_iterations = 5

[hotel]
data_path = "data/mock_hotel_data.json"
simulated_today = "2025-04-15"

[server]
host = "127.0.0.1"
port = 9000
"""
    toml_file = tmp_path / "config.toml"
    toml_file.write_text(toml_content)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")

    settings = load_settings(config_path=str(toml_file))

    assert settings.model == "claude-test-model"
    assert settings.approval_mode == "autonomous"
    assert settings.max_iterations == 5
    assert settings.simulated_today == "2025-04-15"
    assert settings.host == "127.0.0.1"
    assert settings.port == 9000
    assert settings.anthropic_api_key == "sk-test-key"


def test_load_settings_defaults_when_no_toml(monkeypatch):
    """Settings use defaults when config.toml does not exist."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")

    settings = load_settings(config_path="nonexistent.toml")

    assert settings.model == "claude-sonnet-4-20250514"
    assert settings.approval_mode == "human_approval"
    assert settings.max_iterations == 15
    assert settings.host == "0.0.0.0"
    assert settings.port == 8000


def test_load_settings_overrides_take_precedence(tmp_path, monkeypatch):
    """Keyword overrides beat config.toml values."""
    toml_content = """
[agent]
model = "claude-test-model"
approval_mode = "autonomous"
max_iterations = 5

[hotel]
data_path = "data/mock_hotel_data.json"
simulated_today = "2025-04-15"

[server]
host = "127.0.0.1"
port = 9000
"""
    toml_file = tmp_path / "config.toml"
    toml_file.write_text(toml_content)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")

    settings = load_settings(config_path=str(toml_file), approval_mode="human_approval")

    assert settings.approval_mode == "human_approval"
    assert settings.model == "claude-test-model"
