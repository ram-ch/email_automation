from __future__ import annotations

from datetime import date

from app.models import ActionStep, SkillResult
from app.services.pms import PMS


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

    # 1. Resolve guest: prefer provided details over PMS lookup
    # This order ensures multi-booking works — both calls plan a create_guest step,
    # and _execute_action_plan deduplicates at execution time.
    has_all_details = all([guest_first_name, guest_last_name, guest_phone, guest_nationality])
    if has_all_details:
        guest_id = "__new_guest__"
        steps.append(ActionStep(
            description=f"Create guest profile for {guest_first_name} {guest_last_name}",
            tool_call="create_guest",
            params={
                "first_name": guest_first_name,
                "last_name": guest_last_name,
                "email": guest_email,
                "phone": guest_phone,
                "nationality": guest_nationality,
            },
        ))
    else:
        guest = pms.search_guest(guest_email)
        if guest:
            guest_id = guest.id
        else:
            return SkillResult(
                skill_name="book_room",
                action_plan=[],
                draft_reply="I need the guest's first name, last name, phone, and nationality to create a new profile.",
                risk_flag="missing_guest_info",
            )

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
            )

    # 3. Calculate cost
    rate_plan = pms.get_rate_plan(rate_plan_id)
    nights = (co - ci).days
    total = pms._calculate_total(room_type_id, rate_plan_id, check_in, check_out, adults)

    # 4. Plan reservation creation
    steps.append(ActionStep(
        description=f"Create reservation: {room_name}, {check_in} to {check_out}, {nights} night(s), {total:.0f} NOK",
        tool_call="create_reservation",
        params={
            "guest_id": guest_id,
            "room_type_id": room_type_id,
            "rate_plan_id": rate_plan_id,
            "check_in": check_in,
            "check_out": check_out,
            "adults": adults,
            "children": children,
        },
    ))

    rate_name = rate_plan.name if rate_plan else rate_plan_id
    draft = (
        f"I have prepared a booking for {room_name} ({rate_name}) "
        f"from {check_in} to {check_out} for {adults} adult(s). "
        f"Total: {total:.0f} NOK for {nights} night(s)."
    )

    return SkillResult(
        skill_name="book_room",
        action_plan=steps,
        draft_reply=draft,
        requires_approval=True,
    )


def cancel_reservation(pms: PMS, reservation_id: str) -> SkillResult:
    reservation = pms.get_reservation(reservation_id)
    if reservation is None:
        return SkillResult(
            skill_name="cancel_reservation",
            action_plan=[],
            draft_reply=f"Reservation {reservation_id} was not found.",
            risk_flag="reservation_not_found",
        )

    # Non-refundable → escalate
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

    return SkillResult(
        skill_name="cancel_reservation",
        action_plan=[
            ActionStep(
                description=f"Cancel reservation {reservation_id}",
                tool_call="cancel_reservation",
                params={"reservation_id": reservation_id},
            )
        ],
        draft_reply=f"I will cancel reservation {reservation_id} (check-in: {reservation.check_in}, check-out: {reservation.check_out}).",
        requires_approval=True,
    )


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

    # Non-refundable → can't modify
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

    # If room type is changing, validate availability for the new room type
    effective_room = changes.get("room_type_id", reservation.room_type_id)
    effective_ci = changes.get("check_in", reservation.check_in)
    effective_co = changes.get("check_out", reservation.check_out)
    effective_adults = changes.get("adults", reservation.adults)
    effective_rate = changes.get("rate_plan_id", reservation.rate_plan_id)

    ci = date.fromisoformat(str(effective_ci))
    co = date.fromisoformat(str(effective_co))

    if room_type_id is not None or check_in is not None or check_out is not None:
        avail = pms.check_availability(ci, co)
        for date_str, rooms in avail.items():
            # Add 1 back for current reservation's room on its original dates
            available = rooms.get(str(effective_room), 0)
            if (str(effective_room) == reservation.room_type_id
                and date_str >= reservation.check_in
                and date_str < reservation.check_out):
                available += 1
            if available < 1:
                new_room = pms.get_room_type(str(effective_room))
                room_name = new_room.name if new_room else effective_room
                return SkillResult(
                    skill_name="modify_reservation",
                    action_plan=[],
                    draft_reply=f"Sorry, {room_name} is not available for the requested dates ({effective_ci} to {effective_co}).",
                )

    # Calculate new total
    new_total = pms._calculate_total(
        str(effective_room), str(effective_rate), str(effective_ci), str(effective_co), int(effective_adults)
    )

    change_desc = ", ".join(f"{k}={v}" for k, v in changes.items())
    new_room_type = pms.get_room_type(str(effective_room))
    room_name = new_room_type.name if new_room_type else effective_room

    return SkillResult(
        skill_name="modify_reservation",
        action_plan=[
            ActionStep(
                description=f"Modify reservation {reservation_id}: {change_desc} (new total: {new_total:.0f} NOK)",
                tool_call="modify_reservation",
                params={"reservation_id": reservation_id, **changes},
            )
        ],
        draft_reply=f"I will update reservation {reservation_id}: {change_desc}. The new total will be {new_total:.0f} NOK for {room_name}.",
        requires_approval=True,
    )


def escalate_to_human(reason: str) -> SkillResult:
    return SkillResult(
        skill_name="escalate_to_human",
        action_plan=[],
        draft_reply=f"I am escalating this to the hotel staff for further assistance. Reason: {reason}",
        risk_flag=f"Escalation: {reason}",
    )


def get_skill_schemas() -> list[dict]:
    """Return tool-use schemas for all skills."""
    return [
        {
            "name": "book_room",
            "description": "Book a room for a guest. Checks availability and creates a reservation.",
            "input_schema": {
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
            "description": "Cancel an existing reservation. Escalates if non-refundable.",
            "input_schema": {
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
            "name": "escalate_to_human",
            "description": "Escalate to human when the request is ambiguous, involves a non-refundable refund, requires a policy exception, or you are unsure.",
            "input_schema": {
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
