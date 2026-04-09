"""Tests for agent scenarios using mocked LLM responses."""
import json
from unittest.mock import MagicMock, patch

import pytest

from app.agent.react_agent import execute_pending_actions, process_email
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


class TestScenarioBooking:
    """Scenario 2: Guest wants to book — LLM calls check_availability then create_reservation."""

    def test_booking_with_approval(self, pms):
        settings = Settings(anthropic_api_key="test-key", approval_mode="human_approval")

        call_1 = _make_response("tool_use", [
            _make_tool_use_block("tu_1", "check_availability", {
                "check_in": "2025-04-24", "check_out": "2025-04-26",
            })
        ])
        call_2 = _make_response("tool_use", [
            _make_tool_use_block("tu_2", "create_reservation", {
                "guest_id": "G001",
                "room_type_id": "RT002",
                "rate_plan_id": "RP002",
                "check_in": "2025-04-24",
                "check_out": "2025-04-26",
                "adults": 2,
                "children": 0,
            })
        ])
        call_3 = _make_response("end_turn", [
            _make_text_block(
                "Dear Erik,\n\nYour reservation has been confirmed for a Standard Double room "
                "from April 24-26 with breakfast included.\n\nTotal: 4,600 NOK"
            )
        ])

        with patch("app.agent.react_agent.anthropic.Anthropic") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            mock_client.messages.create.side_effect = [call_1, call_2, call_3]

            result = process_email(
                email_body="We'd like to book a double room with breakfast for 2 adults for April 24th-26th.",
                sender_email="erik.hansen@email.com",
                pms=pms,
                settings=settings,
            )

        assert result.requires_approval is True
        assert result.risk_flag is None
        assert len(result.action_plan) == 1
        assert result.action_plan[0].tool_name == "create_reservation"

        # Verify no reservation created yet (human approval mode — write was intercepted)
        reservations = pms.get_reservations("G001")
        original_count = len(reservations)

        # Simulate operator approval
        execute_pending_actions(result.action_plan, pms)
        new_reservations = pms.get_reservations("G001")
        assert len(new_reservations) == original_count + 1


class TestScenarioEscalation:
    """Scenario 3: Non-refundable cancellation — LLM follows guardrail and escalates."""

    def test_nonrefundable_escalates(self, pms):
        settings = Settings(anthropic_api_key="test-key", approval_mode="autonomous")

        call_1 = _make_response("tool_use", [
            _make_tool_use_block("tu_1", "search_guest", {"email": "maria.gonzalez@email.com"})
        ])
        call_2 = _make_response("tool_use", [
            _make_tool_use_block("tu_2", "get_guest_reservations", {"guest_id": "G002"})
        ])
        call_3 = _make_response("tool_use", [
            _make_tool_use_block("tu_3", "escalate_to_human", {
                "reason": "Guest requesting cancellation of non-refundable booking RES002"
            })
        ])
        call_4 = _make_response("end_turn", [
            _make_text_block(
                "Dear Maria,\n\nI understand you'd like to cancel your booking. "
                "Your reservation RES002 is on a non-refundable rate. "
                "I've forwarded this to our team for review."
            )
        ])

        with patch("app.agent.react_agent.anthropic.Anthropic") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            mock_client.messages.create.side_effect = [call_1, call_2, call_3, call_4]

            result = process_email(
                email_body="I want to cancel my booking.",
                sender_email="maria.gonzalez@email.com",
                pms=pms,
                settings=settings,
            )

        assert result.risk_flag is not None
        assert "non-refundable" in result.risk_flag.lower()
        assert result.requires_approval is True
        assert len(result.action_plan) == 0

        # Verify reservation was NOT cancelled
        res = pms.get_reservation("RES002")
        assert res.status == "confirmed"


class TestScenarioNewGuestBooking:
    """Scenario 4: New guest booking — create_guest + create_reservation, both intercepted."""

    def test_new_guest_booking(self, pms):
        settings = Settings(anthropic_api_key="test-key", approval_mode="human_approval")

        call_1 = _make_response("tool_use", [
            _make_tool_use_block("tu_1", "search_guest", {"email": "new.person@email.com"})
        ])
        call_2 = _make_response("tool_use", [
            _make_tool_use_block("tu_2", "check_availability", {
                "check_in": "2025-04-24", "check_out": "2025-04-26",
            })
        ])
        call_3 = _make_response("tool_use", [
            _make_tool_use_block("tu_3", "create_guest", {
                "first_name": "New",
                "last_name": "Person",
                "email": "new.person@email.com",
                "phone": "+47 000 00 000",
                "nationality": "NO",
            })
        ])
        call_4 = _make_response("tool_use", [
            _make_tool_use_block("tu_4", "create_reservation", {
                "guest_id": "__pending_guest__",
                "room_type_id": "RT001",
                "rate_plan_id": "RP001",
                "check_in": "2025-04-24",
                "check_out": "2025-04-26",
                "adults": 1,
            })
        ])
        call_5 = _make_response("end_turn", [
            _make_text_block("Your reservation has been confirmed.")
        ])

        with patch("app.agent.react_agent.anthropic.Anthropic") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            mock_client.messages.create.side_effect = [call_1, call_2, call_3, call_4, call_5]

            result = process_email(
                email_body="I'd like to book a single room April 24-26. Name: New Person, phone: +47 000 00 000, nationality: NO.",
                sender_email="new.person@email.com",
                pms=pms,
                settings=settings,
            )

        assert result.requires_approval is True
        assert len(result.action_plan) == 2
        assert result.action_plan[0].tool_name == "create_guest"
        assert result.action_plan[1].tool_name == "create_reservation"

        # No guest or reservation created yet
        assert pms.search_guest("new.person@email.com") is None

        # Approve — execute_pending_actions resolves __pending_guest__
        execute_pending_actions(result.action_plan, pms)
        guest = pms.search_guest("new.person@email.com")
        assert guest is not None
        reservations = pms.get_reservations(guest.id)
        assert len(reservations) == 1
        assert reservations[0].room_type_id == "RT001"


class TestScenarioModification:
    """Scenario 5: Modify reservation — intercepted for approval."""

    def test_modify_dates(self, pms):
        settings = Settings(anthropic_api_key="test-key", approval_mode="human_approval")

        call_1 = _make_response("tool_use", [
            _make_tool_use_block("tu_1", "search_guest", {"email": "erik.hansen@email.com"})
        ])
        call_2 = _make_response("tool_use", [
            _make_tool_use_block("tu_2", "get_guest_reservations", {"guest_id": "G001"})
        ])
        call_3 = _make_response("tool_use", [
            _make_tool_use_block("tu_3", "modify_reservation", {
                "reservation_id": "RES001",
                "check_in": "2025-04-24",
                "check_out": "2025-04-26",
            })
        ])
        call_4 = _make_response("end_turn", [
            _make_text_block("Your reservation has been updated to April 24-26.")
        ])

        with patch("app.agent.react_agent.anthropic.Anthropic") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            mock_client.messages.create.side_effect = [call_1, call_2, call_3, call_4]

            result = process_email(
                email_body="Can you change my booking to April 24-26?",
                sender_email="erik.hansen@email.com",
                pms=pms,
                settings=settings,
            )

        assert result.requires_approval is True
        assert len(result.action_plan) == 1
        assert result.action_plan[0].tool_name == "modify_reservation"

        # Verify not yet modified
        res = pms.get_reservation("RES001")
        assert res.check_in == "2025-04-20"

        # Approve
        execute_pending_actions(result.action_plan, pms)
        res = pms.get_reservation("RES001")
        assert res.check_in == "2025-04-24"


class TestScenarioUnavailable:
    """Scenario 6: Room unavailable — LLM suggests alternatives, no write tools called."""

    def test_unavailable_suggests_alternatives(self, pms):
        settings = Settings(anthropic_api_key="test-key", approval_mode="human_approval")

        call_1 = _make_response("tool_use", [
            _make_tool_use_block("tu_1", "check_availability", {
                "check_in": "2025-04-22", "check_out": "2025-04-24",
            })
        ])
        call_2 = _make_response("end_turn", [
            _make_text_block(
                "Unfortunately, Standard Double rooms are not available for April 22-24. "
                "We do have Superior Double rooms and Junior Suites available for those dates."
            )
        ])

        with patch("app.agent.react_agent.anthropic.Anthropic") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            mock_client.messages.create.side_effect = [call_1, call_2]

            result = process_email(
                email_body="I'd like a double room April 22-24.",
                sender_email="someone@email.com",
                pms=pms,
                settings=settings,
            )

        assert result.requires_approval is False
        assert len(result.action_plan) == 0
        assert "not available" in result.draft_reply.lower() or "unavailable" in result.draft_reply.lower()


class TestScenarioAutonomous:
    """Scenario 7: Autonomous mode — write tools execute immediately."""

    def test_autonomous_booking(self, pms):
        settings = Settings(anthropic_api_key="test-key", approval_mode="autonomous")

        call_1 = _make_response("tool_use", [
            _make_tool_use_block("tu_1", "check_availability", {
                "check_in": "2025-04-24", "check_out": "2025-04-26",
            })
        ])
        call_2 = _make_response("tool_use", [
            _make_tool_use_block("tu_2", "create_reservation", {
                "guest_id": "G001",
                "room_type_id": "RT002",
                "rate_plan_id": "RP001",
                "check_in": "2025-04-24",
                "check_out": "2025-04-26",
                "adults": 2,
            })
        ])
        call_3 = _make_response("end_turn", [
            _make_text_block("Your reservation has been confirmed.")
        ])

        with patch("app.agent.react_agent.anthropic.Anthropic") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            mock_client.messages.create.side_effect = [call_1, call_2, call_3]

            reservations_before = len(pms.get_reservations("G001"))

            result = process_email(
                email_body="Book a double room April 24-26 for 2 adults.",
                sender_email="erik.hansen@email.com",
                pms=pms,
                settings=settings,
            )

        # In autonomous mode: executed immediately, no approval needed
        assert result.requires_approval is False
        assert len(result.action_plan) == 1
        reservations_after = len(pms.get_reservations("G001"))
        assert reservations_after == reservations_before + 1


class TestScenarioMultipleActions:
    """Scenario 8: Multiple actions in one email — all collected in action plan."""

    def test_two_bookings(self, pms):
        settings = Settings(anthropic_api_key="test-key", approval_mode="human_approval")

        call_1 = _make_response("tool_use", [
            _make_tool_use_block("tu_1", "check_availability", {
                "check_in": "2025-04-24", "check_out": "2025-04-26",
            })
        ])
        call_2 = _make_response("tool_use", [
            _make_tool_use_block("tu_2", "create_reservation", {
                "guest_id": "G001",
                "room_type_id": "RT001",
                "rate_plan_id": "RP001",
                "check_in": "2025-04-24",
                "check_out": "2025-04-25",
                "adults": 1,
            })
        ])
        call_3 = _make_response("tool_use", [
            _make_tool_use_block("tu_3", "create_reservation", {
                "guest_id": "G001",
                "room_type_id": "RT002",
                "rate_plan_id": "RP001",
                "check_in": "2025-04-24",
                "check_out": "2025-04-25",
                "adults": 2,
            })
        ])
        call_4 = _make_response("end_turn", [
            _make_text_block("Both reservations have been confirmed.")
        ])

        with patch("app.agent.react_agent.anthropic.Anthropic") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            mock_client.messages.create.side_effect = [call_1, call_2, call_3, call_4]

            result = process_email(
                email_body="I need two rooms for April 24-25: a single for me and a double for my colleagues.",
                sender_email="erik.hansen@email.com",
                pms=pms,
                settings=settings,
            )

        assert result.requires_approval is True
        assert len(result.action_plan) == 2
        assert all(a.tool_name == "create_reservation" for a in result.action_plan)
