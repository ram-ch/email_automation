from app.agent.react_agent import process_email
from app.config import load_settings
from app.services.pms import PMS
from unittest.mock import MagicMock, patch
import json


def test_logging_callback_receives_tool_calls(pms):
    """The logging callback is called for each tool invocation."""
    log_entries = []

    def log_callback(entry: dict):
        log_entries.append(entry)

    # Mock the Anthropic client to simulate a simple read-only flow:
    # Iteration 1: call get_hotel_info tool
    # Iteration 2: end_turn with text reply
    mock_client = MagicMock()

    tool_use_block = MagicMock()
    tool_use_block.type = "tool_use"
    tool_use_block.id = "tool_1"
    tool_use_block.name = "get_hotel_info"
    tool_use_block.input = {}

    response_1 = MagicMock()
    response_1.stop_reason = "tool_use"
    response_1.content = [tool_use_block]

    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = "Here is the hotel info."
    setattr(text_block, "text", "Here is the hotel info.")

    response_2 = MagicMock()
    response_2.stop_reason = "end_turn"
    response_2.content = [text_block]

    mock_client.messages.create.side_effect = [response_1, response_2]

    settings = load_settings(
        anthropic_api_key="fake-key",
        simulated_today="2025-04-15",
        config_path="nonexistent.toml",
    )

    with patch("app.agent.react_agent.anthropic.Anthropic", return_value=mock_client):
        result = process_email(
            email_body="What is this hotel?",
            sender_email="test@test.com",
            pms=pms,
            settings=settings,
            log_callback=log_callback,
        )

    # Should have logged the tool call
    assert len(log_entries) >= 1
    # Find the tool log entry (skip the "incoming" entry)
    tool_entries = [e for e in log_entries if e["type"] == "tool"]
    assert len(tool_entries) == 1
    assert tool_entries[0]["name"] == "get_hotel_info"


def test_process_email_works_without_callback(pms):
    """process_email still works when no callback is provided (backward compat)."""
    mock_client = MagicMock()

    text_block = MagicMock()
    text_block.type = "text"
    setattr(text_block, "text", "No rooms available.")

    response = MagicMock()
    response.stop_reason = "end_turn"
    response.content = [text_block]

    mock_client.messages.create.return_value = response

    settings = load_settings(
        anthropic_api_key="fake-key",
        simulated_today="2025-04-15",
        config_path="nonexistent.toml",
    )

    with patch("app.agent.react_agent.anthropic.Anthropic", return_value=mock_client):
        result = process_email(
            email_body="Hello",
            sender_email="test@test.com",
            pms=pms,
            settings=settings,
        )

    assert result.draft_reply == "No rooms available."
