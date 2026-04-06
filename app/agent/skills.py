from __future__ import annotations

from datetime import date

from app.models import ActionStep, SkillResult
from app.services.pms import PMS


class _PendingActions:
    """Holds deferred actions that can be executed against the PMS."""

    def __init__(self, actions: list[tuple[str, dict]]) -> None:
        self.actions = actions

    def __call__(self, pms: PMS) -> bool:
        created_guest_id: str | None = None
        for action_name, params in self.actions:
            if action_name == "create_guest":
                guest = pms.create_guest(**params)
                created_guest_id = guest.id
            elif action_name == "create_reservation":
                p = dict(params)
                if p.get("guest_id") == "__new_guest__" and created_guest_id:
                    p["guest_id"] = created_guest_id
                result = pms.create_reservation(**p)
                if result is None:
                    return False
            elif action_name == "cancel_reservation":
                result = pms.cancel_reservation(**params)
                if result is None:
                    return False
            elif action_name == "modify_reservation":
                result = pms.modify_reservation(**params)
                if result is None:
                    return False
        return True


def book_room(
    pms: PMS,
    guest_email: str,
    room_type_id: str,
    rate_plan_id: str,
    check_in: str,
    check_out: str,
    adults: int,
    children: int = 0,
    guest_first_name: str | None = None,
    guest_last_name: str | None = None,
    guest_phone: str | None = None,
    guest_nationality: str | None = None,
) -> SkillResult:
    steps: list[ActionStep] = []
    actions: list[tuple[str, dict]] = []

    # 1. Look up or plan guest creation
    guest = pms.search_guest(guest_email)
    if guest:
        guest_id = guest.id
    else:
        if not all([guest_first_name, guest_last_name, guest_phone, guest_nationality]):
            return SkillResult(
                skill_name="book_room",
                action_plan=[],
                draft_reply="I need the guest's first name, last name, phone, and nationality to create a new profile.",
                risk_flag="missing_guest_info",
            )
        guest_id = "__new_guest__"
        guest_params = {
            "first_name": guest_first_name,
            "last_name": guest_last_name,
            "email": guest_email,
            "phone": guest_phone,
            "nationality": guest_nationality,
        }
        steps.append(ActionStep(
            description=f"Create guest profile for {guest_first_name} {guest_last_name}",
            tool_call="create_guest",
            params=guest_params,
        ))
        actions.append(("create_guest", guest_params))

    # 2. Check availability
    ci = date.fromisoformat(check_in)
    co = date.fromisoformat(check_out)
    availability = pms.check_availability(ci, co)
    room_type = pms.get_room_type(room_type_id)
    room_name = room_type.name if room_type else room_type_id

    for date_str, rooms in availability.items():
        if rooms.get(room_type_id, 0) < 1:
            return SkillResult(
                skill_name="book_room",
                action_plan=[],
                draft_reply=f"Sorry, {room_name} is not available for the requested dates ({check_in} to {check_out}).",
                risk_flag=None,
            )

    # 3. Calculate cost info for reply
    rate_plan = pms.get_rate_plan(rate_plan_id)
    nights = (co - ci).days
    total = pms._calculate_total(room_type_id, rate_plan_id, check_in, check_out, adults)

    # 4. Plan reservation creation
    res_params = {
        "guest_id": guest_id,
        "room_type_id": room_type_id,
        "rate_plan_id": rate_plan_id,
        "check_in": check_in,
        "check_out": check_out,
        "adults": adults,
        "children": children,
    }
    steps.append(ActionStep(
        description=f"Create reservation for {room_name} from {check_in} to {check_out} ({nights} nights, {total:.0f} {pms.get_hotel_info().currency})",
        tool_call="create_reservation",
        params=res_params,
    ))
    actions.append(("create_reservation", res_params))

    rate_name = rate_plan.name if rate_plan else rate_plan_id
    draft = (
        f"I have prepared a booking for {room_name} ({rate_name}) "
        f"from {check_in} to {check_out} for {adults} adult(s). "
        f"Total: {total:.0f} NOK for {nights} night(s)."
    )

    result = SkillResult(
        skill_name="book_room",
        action_plan=steps,
        draft_reply=draft,
        requires_approval=True,
    )
    object.__setattr__(result, "execute_actions", _PendingActions(actions))
    return result


def cancel_reservation(pms: PMS, reservation_id: str) -> SkillResult:
    reservation = pms.get_reservation(reservation_id)
    if reservation is None:
        return SkillResult(
            skill_name="cancel_reservation",
            action_plan=[],
            draft_reply=f"Reservation {reservation_id} was not found.",
            risk_flag="reservation_not_found",
        )

    # Check if non-refundable
    rate_plan = pms.get_rate_plan(reservation.rate_plan_id)
    if rate_plan and rate_plan.cancellation_policy == "non_refundable":
        return SkillResult(
            skill_name="cancel_reservation",
            action_plan=[],
            draft_reply=(
                f"Reservation {reservation_id} is on a non-refundable rate plan ({rate_plan.name}). "
                "Cancellation would forfeit the full amount. This needs manager approval."
            ),
            risk_flag="non-refundable reservation - cancellation requires manager approval",
            requires_approval=True,
        )

    steps = [
        ActionStep(
            description=f"Cancel reservation {reservation_id}",
            tool_call="cancel_reservation",
            params={"reservation_id": reservation_id},
        )
    ]
    actions = [("cancel_reservation", {"reservation_id": reservation_id})]

    draft = f"I will cancel reservation {reservation_id} (check-in: {reservation.check_in}, check-out: {reservation.check_out})."

    result = SkillResult(
        skill_name="cancel_reservation",
        action_plan=steps,
        draft_reply=draft,
        requires_approval=True,
    )
    object.__setattr__(result, "execute_actions", _PendingActions(actions))
    return result


def modify_reservation(
    pms: PMS,
    reservation_id: str,
    check_in: str | None = None,
    check_out: str | None = None,
    adults: int | None = None,
    children: int | None = None,
    room_type_id: str | None = None,
    rate_plan_id: str | None = None,
) -> SkillResult:
    reservation = pms.get_reservation(reservation_id)
    if reservation is None:
        return SkillResult(
            skill_name="modify_reservation",
            action_plan=[],
            draft_reply=f"Reservation {reservation_id} was not found.",
            risk_flag="reservation_not_found",
        )

    # Check if non-refundable
    rate_plan = pms.get_rate_plan(reservation.rate_plan_id)
    if rate_plan and rate_plan.cancellation_policy == "non_refundable":
        return SkillResult(
            skill_name="modify_reservation",
            action_plan=[],
            draft_reply=(
                f"Reservation {reservation_id} is on a non-refundable rate plan ({rate_plan.name}). "
                "Modifications are not allowed. This needs manager approval."
            ),
            risk_flag="non-refundable reservation - modification requires manager approval",
            requires_approval=True,
        )

    changes: dict[str, str | int] = {}
    if check_in is not None:
        changes["check_in"] = check_in
    if check_out is not None:
        changes["check_out"] = check_out
    if adults is not None:
        changes["adults"] = adults
    if children is not None:
        changes["children"] = children
    if room_type_id is not None:
        changes["room_type_id"] = room_type_id
    if rate_plan_id is not None:
        changes["rate_plan_id"] = rate_plan_id

    modify_params = {"reservation_id": reservation_id, **changes}

    change_desc = ", ".join(f"{k}={v}" for k, v in changes.items())
    steps = [
        ActionStep(
            description=f"Modify reservation {reservation_id}: {change_desc}",
            tool_call="modify_reservation",
            params=modify_params,
        )
    ]
    actions = [("modify_reservation", modify_params)]

    draft = f"I will update reservation {reservation_id} with the following changes: {change_desc}."

    result = SkillResult(
        skill_name="modify_reservation",
        action_plan=steps,
        draft_reply=draft,
        requires_approval=True,
    )
    object.__setattr__(result, "execute_actions", _PendingActions(actions))
    return result


def escalate_to_human(reason: str) -> SkillResult:
    return SkillResult(
        skill_name="escalate_to_human",
        action_plan=[],
        draft_reply=f"I am escalating this to the hotel staff for further assistance. Reason: {reason}",
        risk_flag=f"Escalation: {reason}",
        requires_approval=False,
    )


def get_skill_schemas() -> list[dict]:
    """Return tool-use schemas for all skills, suitable for LLM function calling."""
    return [
        {
            "name": "book_room",
            "description": "Book a room for a guest. Searches for the guest by email, checks availability, and creates a reservation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "guest_email": {"type": "string", "description": "Guest email address"},
                    "room_type_id": {"type": "string", "description": "Room type ID (e.g. RT001)"},
                    "rate_plan_id": {"type": "string", "description": "Rate plan ID (e.g. RP001)"},
                    "check_in": {"type": "string", "description": "Check-in date (YYYY-MM-DD)"},
                    "check_out": {"type": "string", "description": "Check-out date (YYYY-MM-DD)"},
                    "adults": {"type": "integer", "description": "Number of adults"},
                    "children": {"type": "integer", "description": "Number of children", "default": 0},
                    "guest_first_name": {"type": "string", "description": "First name (required for new guests)"},
                    "guest_last_name": {"type": "string", "description": "Last name (required for new guests)"},
                    "guest_phone": {"type": "string", "description": "Phone (required for new guests)"},
                    "guest_nationality": {"type": "string", "description": "Nationality code (required for new guests)"},
                },
                "required": ["guest_email", "room_type_id", "rate_plan_id", "check_in", "check_out", "adults"],
            },
        },
        {
            "name": "cancel_reservation",
            "description": "Cancel an existing reservation. Checks if the reservation is non-refundable and escalates if so.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reservation_id": {"type": "string", "description": "Reservation ID to cancel"},
                },
                "required": ["reservation_id"],
            },
        },
        {
            "name": "modify_reservation",
            "description": "Modify an existing reservation (dates, guest count, room type, or rate plan).",
            "parameters": {
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
            "name": "escalate_to_human",
            "description": "Escalate the conversation to a human staff member when the request is outside policy or requires special approval.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {"type": "string", "description": "Reason for escalation"},
                },
                "required": ["reason"],
            },
        },
    ]


def execute_skill(name: str, params: dict, pms: PMS) -> SkillResult:
    """Dispatch a skill by name."""
    if name == "book_room":
        return book_room(pms=pms, **params)
    elif name == "cancel_reservation":
        return cancel_reservation(pms=pms, **params)
    elif name == "modify_reservation":
        return modify_reservation(pms=pms, **params)
    elif name == "escalate_to_human":
        return escalate_to_human(**params)
    else:
        raise ValueError(f"Unknown skill: {name}")
