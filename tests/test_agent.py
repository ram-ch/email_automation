"""Tests for the 3 required scenarios using mocked LLM responses."""
import json
from unittest.mock import MagicMock, patch

import pytest

from app.agent.react_agent import process_email
from app.config import Settings


def _make_text_block(text: str):
    block = MagicMock()
    block.type = "text"
    block.text = text
    return block


def _make_tool_use_block(tool_id: str, name: str, input_data: dict):
    block = MagicMock()
    block.type = "tool_use"
    block.id = tool_id
    block.name = name
    block.input = input_data
    return block


def _make_response(stop_reason: str, content: list):
    response = MagicMock()
    response.stop_reason = stop_reason
    response.content = content
    return response


class TestScenarioReadOnlyLookup:
    """Scenario 1: Guest asks about room availability — read-only, no writes."""

    def test_availability_lookup(self, pms):
        settings = Settings(anthropic_api_key="test-key", approval_mode="human_approval")

        # LLM calls check_availability, then responds with text
        call_1 = _make_response("tool_use", [
            _make_tool_use_block("tu_1", "check_availability", {
                "check_in": "2025-04-20", "check_out": "2025-04-22",
            })
        ])
        call_2 = _make_response("end_turn", [
            _make_text_block(
                "We have availability for April 20-22. Standard Single at 1,200 NOK/night, "
                "Superior Double at 2,500 NOK/night."
            )
        ])

        with patch("app.agent.react_agent.anthropic.Anthropic") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            mock_client.messages.create.side_effect = [call_1, call_2]

            result = process_email(
                email_body="Do you have any available rooms April 20th-22nd?",
                sender_email="someone@email.com",
                pms=pms,
                settings=settings,
            )

        assert "availability" in result.draft_reply.lower() or "available" in result.draft_reply.lower()
        assert result.requires_approval is False
        assert result.risk_flag is None
        assert len(result.action_plan) == 0


class TestScenarioBookingAction:
    """Scenario 2: Guest wants to book a room — invokes book_room skill."""

    def test_booking_with_approval(self, pms):
        settings = Settings(anthropic_api_key="test-key", approval_mode="human_approval")

        # LLM first checks availability, then gets rate plans, then calls book_room skill
        call_1 = _make_response("tool_use", [
            _make_tool_use_block("tu_1", "check_availability", {
                "check_in": "2025-04-24", "check_out": "2025-04-26",
            })
        ])
        call_2 = _make_response("tool_use", [
            _make_tool_use_block("tu_2", "get_rate_plans", {})
        ])
        call_3 = _make_response("tool_use", [
            _make_tool_use_block("tu_3", "book_room", {
                "guest_email": "erik.hansen@email.com",
                "room_type_id": "RT002",
                "rate_plan_id": "RP002",
                "check_in": "2025-04-24",
                "check_out": "2025-04-26",
                "adults": 2,
                "children": 0,
            })
        ])
        call_4 = _make_response("end_turn", [
            _make_text_block(
                "Dear Erik,\n\nI've prepared a booking for a Standard Double room "
                "from April 24-26 with breakfast included.\n\nTotal: 4,600 NOK"
            )
        ])

        with patch("app.agent.react_agent.anthropic.Anthropic") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            mock_client.messages.create.side_effect = [call_1, call_2, call_3, call_4]

            result = process_email(
                email_body="We'd like to book a double room with breakfast for 2 adults for April 24th-26th.",
                sender_email="erik.hansen@email.com",
                pms=pms,
                settings=settings,
            )

        assert result.requires_approval is True
        assert result.risk_flag is None
        assert len(result.action_plan) > 0

        # Verify no reservation created yet (human approval mode)
        reservations = pms.get_reservations("G001")
        original_count = len(reservations)

        # Simulate approval — agent loop's _execute_action_plan does this
        from app.agent.react_agent import _execute_action_plan
        from app.models import SkillResult
        skill_result = SkillResult(
            skill_name="book_room",
            action_plan=result.action_plan,
            draft_reply=result.draft_reply,
        )
        _execute_action_plan(skill_result, pms)
        new_reservations = pms.get_reservations("G001")
        assert len(new_reservations) == original_count + 1


class TestScenarioAmbiguousEscalation:
    """Scenario 3: Non-refundable refund request — must escalate."""

    def test_nonrefundable_refund_escalates(self, pms):
        settings = Settings(anthropic_api_key="test-key", approval_mode="autonomous")

        # LLM searches for guest, gets reservations, then tries to cancel
        call_1 = _make_response("tool_use", [
            _make_tool_use_block("tu_1", "search_guest", {"email": "maria.gonzalez@email.com"})
        ])
        call_2 = _make_response("tool_use", [
            _make_tool_use_block("tu_2", "get_guest_reservations", {"guest_id": "G002"})
        ])
        call_3 = _make_response("tool_use", [
            _make_tool_use_block("tu_3", "cancel_reservation", {"reservation_id": "RES002"})
        ])
        call_4 = _make_response("end_turn", [
            _make_text_block(
                "Dear Maria,\n\nI understand you'd like a refund on your booking. "
                "Your reservation RES002 is on a non-refundable rate. "
                "I've forwarded this to our team for review."
            )
        ])

        with patch("app.agent.react_agent.anthropic.Anthropic") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            mock_client.messages.create.side_effect = [call_1, call_2, call_3, call_4]

            result = process_email(
                email_body="I want a refund on my non-refundable booking.",
                sender_email="maria.gonzalez@email.com",
                pms=pms,
                settings=settings,
            )

        assert result.risk_flag is not None
        assert "non-refundable" in result.risk_flag.lower() or "non_refundable" in result.risk_flag.lower()
        assert result.requires_approval is True

        # Verify reservation was NOT cancelled
        res = pms.get_reservation("RES002")
        assert res.status == "confirmed"
