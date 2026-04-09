import json
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.models import AgentResponse, PendingAction


@pytest.fixture
def client():
    """Create a test client with mocked PMS and settings."""
    from app.main import create_app
    from app.config import load_settings
    from app.services.pms import PMS
    import os

    data_path = os.path.join(os.path.dirname(__file__), "..", "data", "mock_hotel_data.json")
    settings = load_settings(
        config_path="nonexistent.toml",
        anthropic_api_key="fake-key",
        simulated_today="2025-04-15",
        approval_mode="autonomous",
    )
    pms = PMS(data_path)
    app = create_app(settings=settings, pms=pms)
    return TestClient(app)


def test_process_email_readonly(client):
    """Read-only request returns completed status with HTML email."""
    mock_response = AgentResponse(
        draft_reply="We have rooms available for those dates.",
        action_plan=[],
        requires_approval=False,
        risk_flag=None,
    )

    with patch("app.main.process_email", return_value=mock_response):
        resp = client.post("/process-email", json={
            "sender_email": "test@test.com",
            "body": "Do you have rooms available?",
        })

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert "email_html" in data
    assert "rooms available" in data["email_html"]
    assert data["action_plan"] == []


def test_process_email_autonomous_with_actions(client):
    """Autonomous mode with actions returns completed status."""
    mock_response = AgentResponse(
        draft_reply="Your room has been booked.",
        action_plan=[
            PendingAction(
                description="Create reservation: Standard Double",
                tool_name="create_reservation",
                params={"guest_id": "G001"},
            )
        ],
        requires_approval=False,
        risk_flag=None,
    )

    with patch("app.main.process_email", return_value=mock_response):
        resp = client.post("/process-email", json={
            "sender_email": "test@test.com",
            "body": "Book a room.",
        })

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert len(data["action_plan"]) == 1


def test_process_email_escalated(client):
    """Risk-flagged request returns escalated status."""
    mock_response = AgentResponse(
        draft_reply="I have forwarded this to our team.",
        action_plan=[],
        requires_approval=True,
        risk_flag="non-refundable cancellation",
    )

    with patch("app.main.process_email", return_value=mock_response):
        resp = client.post("/process-email", json={
            "sender_email": "test@test.com",
            "body": "Refund my booking.",
        })

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "escalated"
    assert data["risk_flag"] == "non-refundable cancellation"
    assert data["requires_approval"] is False


def test_process_email_missing_fields(client):
    """Missing required fields return 422."""
    resp = client.post("/process-email", json={"sender_email": "test@test.com"})
    assert resp.status_code == 422


def test_process_email_html_format(client):
    """response_format=html returns the email HTML directly."""
    mock_response = AgentResponse(
        draft_reply="We have rooms available for those dates.",
        action_plan=[],
        requires_approval=False,
        risk_flag=None,
    )

    with patch("app.main.process_email", return_value=mock_response):
        resp = client.post(
            "/process-email?response_format=html",
            json={
                "sender_email": "test@test.com",
                "body": "Do you have rooms available?",
            },
        )

    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    html = resp.text
    assert "rooms available" in html
    assert "<!DOCTYPE html>" in html
