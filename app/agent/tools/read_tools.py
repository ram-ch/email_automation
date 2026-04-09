from __future__ import annotations

import json
from datetime import date

from app.services.pms import PMS


READ_TOOL_SCHEMAS: list[dict] = [
    {
        "name": "search_guest",
        "description": "Search for a guest by their email address. Returns guest profile if found.",
        "input_schema": {
            "type": "object",
            "properties": {
                "email": {"type": "string", "description": "Guest email address"},
            },
            "required": ["email"],
        },
    },
    {
        "name": "get_reservation",
        "description": "Get details of a specific reservation by ID.",
        "input_schema": {
            "type": "object",
            "properties": {
                "reservation_id": {"type": "string", "description": "Reservation ID (e.g. RES001)"},
            },
            "required": ["reservation_id"],
        },
    },
    {
        "name": "get_guest_reservations",
        "description": "Get all reservations for a specific guest.",
        "input_schema": {
            "type": "object",
            "properties": {
                "guest_id": {"type": "string", "description": "Guest ID (e.g. G001)"},
            },
            "required": ["guest_id"],
        },
    },
    {
        "name": "check_availability",
        "description": "Check available rooms for a date range. Returns available room types with count per night and pricing.",
        "input_schema": {
            "type": "object",
            "properties": {
                "check_in": {"type": "string", "description": "Check-in date (YYYY-MM-DD)"},
                "check_out": {"type": "string", "description": "Check-out date (YYYY-MM-DD)"},
            },
            "required": ["check_in", "check_out"],
        },
    },
    {
        "name": "get_rate_plans",
        "description": "List all available rate plans with pricing modifiers and cancellation policies.",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "get_policies",
        "description": "Get hotel policies: cancellation, pets, breakfast, parking, extra beds, children.",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "get_hotel_info",
        "description": "Get hotel metadata: name, address, phone, check-in/out times, currency.",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
]


def _search_guest(params: dict, pms: PMS) -> str:
    guest = pms.search_guest(params["email"])
    if guest:
        return json.dumps({"found": True, "guest": guest.model_dump()})
    return json.dumps({"found": False, "message": "No guest found with that email."})


def _enrich_reservation(res_data: dict, pms: PMS) -> dict:
    """Add room type name and rate plan name to a reservation dict."""
    room = pms.get_room_type(res_data["room_type_id"])
    rate = pms.get_rate_plan(res_data["rate_plan_id"])
    res_data["room_type_name"] = room.name if room else res_data["room_type_id"]
    res_data["rate_plan_name"] = rate.name if rate else res_data["rate_plan_id"]
    return res_data


def _get_reservation(params: dict, pms: PMS) -> str:
    res = pms.get_reservation(params["reservation_id"])
    if res:
        return json.dumps({"reservation": _enrich_reservation(res.model_dump(), pms)})
    return json.dumps({"error": "Reservation not found."})


def _get_guest_reservations(params: dict, pms: PMS) -> str:
    reservations = pms.get_reservations(params["guest_id"])
    return json.dumps({
        "reservations": [_enrich_reservation(r.model_dump(), pms) for r in reservations]
    })


def _check_availability(params: dict, pms: PMS) -> str:
    ci = date.fromisoformat(params["check_in"])
    co = date.fromisoformat(params["check_out"])
    avail = pms.check_availability(ci, co)
    room_types = [rt.model_dump() for rt in pms.get_all_room_types()]
    return json.dumps({"availability": avail, "room_types": room_types})


def _get_rate_plans(params: dict, pms: PMS) -> str:
    plans = pms.get_rate_plans()
    return json.dumps({"rate_plans": [p.model_dump() for p in plans]})


def _get_policies(params: dict, pms: PMS) -> str:
    policies = pms.get_policies()
    return json.dumps(policies.model_dump())


def _get_hotel_info(params: dict, pms: PMS) -> str:
    hotel = pms.get_hotel_info()
    return json.dumps(hotel.model_dump())


READ_TOOL_HANDLERS: dict = {
    "search_guest": _search_guest,
    "get_reservation": _get_reservation,
    "get_guest_reservations": _get_guest_reservations,
    "check_availability": _check_availability,
    "get_rate_plans": _get_rate_plans,
    "get_policies": _get_policies,
    "get_hotel_info": _get_hotel_info,
}
