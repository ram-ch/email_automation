from __future__ import annotations

import json

from app.services.pms import PMS


WRITE_TOOL_SCHEMAS: list[dict] = [
    {
        "name": "create_guest",
        "description": "Create a new guest profile. Requires first name, last name, email, phone, and nationality.",
        "input_schema": {
            "type": "object",
            "properties": {
                "first_name": {"type": "string", "description": "Guest first name"},
                "last_name": {"type": "string", "description": "Guest last name"},
                "email": {"type": "string", "description": "Guest email address"},
                "phone": {"type": "string", "description": "Guest phone number"},
                "nationality": {"type": "string", "description": "Two-letter nationality code (e.g. NO, ES, GB)"},
            },
            "required": ["first_name", "last_name", "email", "phone", "nationality"],
        },
    },
    {
        "name": "create_reservation",
        "description": "Create a new reservation for a guest. Returns error if the room type is unavailable for the requested dates.",
        "input_schema": {
            "type": "object",
            "properties": {
                "guest_id": {"type": "string", "description": "Guest ID (e.g. G001)"},
                "room_type_id": {"type": "string", "description": "Room type ID (e.g. RT001)"},
                "rate_plan_id": {"type": "string", "description": "Rate plan ID (e.g. RP001)"},
                "check_in": {"type": "string", "description": "Check-in date (YYYY-MM-DD)"},
                "check_out": {"type": "string", "description": "Check-out date (YYYY-MM-DD)"},
                "adults": {"type": "integer", "description": "Number of adults"},
                "children": {"type": "integer", "description": "Number of children", "default": 0},
            },
            "required": ["guest_id", "room_type_id", "rate_plan_id", "check_in", "check_out", "adults"],
        },
    },
    {
        "name": "modify_reservation",
        "description": "Modify an existing reservation. Pass only the fields to change. Returns error if unavailable or not found.",
        "input_schema": {
            "type": "object",
            "properties": {
                "reservation_id": {"type": "string", "description": "Reservation ID to modify"},
                "check_in": {"type": "string", "description": "New check-in date (YYYY-MM-DD)"},
                "check_out": {"type": "string", "description": "New check-out date (YYYY-MM-DD)"},
                "adults": {"type": "integer", "description": "New number of adults"},
                "children": {"type": "integer", "description": "New number of children"},
                "room_type_id": {"type": "string", "description": "New room type ID"},
                "rate_plan_id": {"type": "string", "description": "New rate plan ID"},
            },
            "required": ["reservation_id"],
        },
    },
    {
        "name": "cancel_reservation",
        "description": "Cancel an existing reservation. Returns error if not found or already cancelled.",
        "input_schema": {
            "type": "object",
            "properties": {
                "reservation_id": {"type": "string", "description": "Reservation ID to cancel"},
            },
            "required": ["reservation_id"],
        },
    },
]

WRITE_TOOL_NAMES: set[str] = {s["name"] for s in WRITE_TOOL_SCHEMAS}


def _create_guest(params: dict, pms: PMS) -> str:
    guest = pms.create_guest(
        first_name=params["first_name"],
        last_name=params["last_name"],
        email=params["email"],
        phone=params["phone"],
        nationality=params["nationality"],
    )
    return json.dumps({"guest": guest.model_dump()})


def _create_reservation(params: dict, pms: PMS) -> str:
    reservation = pms.create_reservation(
        guest_id=params["guest_id"],
        room_type_id=params["room_type_id"],
        rate_plan_id=params["rate_plan_id"],
        check_in=params["check_in"],
        check_out=params["check_out"],
        adults=params["adults"],
        children=params.get("children", 0),
    )
    if reservation is None:
        return json.dumps({"error": "Room unavailable for the requested dates."})
    return json.dumps({"reservation": reservation.model_dump()})


def _modify_reservation(params: dict, pms: PMS) -> str:
    reservation_id = params["reservation_id"]
    changes = {k: v for k, v in params.items() if k != "reservation_id"}
    reservation = pms.modify_reservation(reservation_id, **changes)
    if reservation is None:
        return json.dumps({"error": "Modification failed. Reservation not found or room unavailable."})
    return json.dumps({"reservation": reservation.model_dump()})


def _cancel_reservation(params: dict, pms: PMS) -> str:
    reservation = pms.cancel_reservation(params["reservation_id"])
    if reservation is None:
        return json.dumps({"error": "Cancellation failed. Reservation not found or already cancelled."})
    return json.dumps({"reservation": reservation.model_dump()})


WRITE_TOOL_HANDLERS = {
    "create_guest": _create_guest,
    "create_reservation": _create_reservation,
    "modify_reservation": _modify_reservation,
    "cancel_reservation": _cancel_reservation,
}
