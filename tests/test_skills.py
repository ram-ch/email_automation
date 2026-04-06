from datetime import date


def test_book_room_produces_plan(pms):
    from app.agent.skills import book_room
    result = book_room(
        pms=pms,
        guest_email="erik.hansen@email.com",
        room_type_id="RT002",
        rate_plan_id="RP001",
        check_in="2025-04-24",
        check_out="2025-04-26",
        adults=2,
        children=0,
    )
    assert result.skill_name == "book_room"
    assert len(result.action_plan) > 0
    assert result.risk_flag is None
    assert "create_reservation" in [step.tool_call for step in result.action_plan]


def test_book_room_execute(pms):
    from app.agent.skills import book_room
    result = book_room(
        pms=pms,
        guest_email="erik.hansen@email.com",
        room_type_id="RT002",
        rate_plan_id="RP001",
        check_in="2025-04-24",
        check_out="2025-04-26",
        adults=2,
        children=0,
    )
    # Execute the pending actions
    executed = result.execute_actions(pms)
    assert executed is True

    # Verify reservation was created
    reservations = pms.get_reservations("G001")
    new_res = [r for r in reservations if r.check_in == "2025-04-24"]
    assert len(new_res) == 1
    assert new_res[0].room_type_id == "RT002"


def test_book_room_new_guest(pms):
    from app.agent.skills import book_room
    result = book_room(
        pms=pms,
        guest_email="new.person@email.com",
        room_type_id="RT001",
        rate_plan_id="RP001",
        check_in="2025-04-24",
        check_out="2025-04-26",
        adults=1,
        children=0,
        guest_first_name="New",
        guest_last_name="Person",
        guest_phone="+47 000 00 000",
        guest_nationality="NO",
    )
    assert result.skill_name == "book_room"
    # Should include create_guest step
    assert "create_guest" in [step.tool_call for step in result.action_plan]


def test_book_room_no_availability(pms):
    from app.agent.skills import book_room
    result = book_room(
        pms=pms,
        guest_email="erik.hansen@email.com",
        room_type_id="RT002",
        rate_plan_id="RP001",
        check_in="2025-04-22",
        check_out="2025-04-24",
        adults=2,
        children=0,
    )
    assert result.risk_flag is not None or "not available" in result.draft_reply.lower()


def test_cancel_reservation_standard(pms):
    from app.agent.skills import cancel_reservation
    result = cancel_reservation(pms=pms, reservation_id="RES001")
    assert result.skill_name == "cancel_reservation"
    assert result.risk_flag is None
    assert "cancel_reservation" in [step.tool_call for step in result.action_plan]

    executed = result.execute_actions(pms)
    assert executed is True

    res = pms.get_reservation("RES001")
    assert res.status == "cancelled"


def test_cancel_nonrefundable_escalates(pms):
    from app.agent.skills import cancel_reservation
    # RES002 is non-refundable (RP003)
    result = cancel_reservation(pms=pms, reservation_id="RES002")
    assert result.risk_flag is not None
    assert "non-refundable" in result.risk_flag.lower() or "non_refundable" in result.risk_flag.lower()


def test_escalate_to_human(pms):
    from app.agent.skills import escalate_to_human
    result = escalate_to_human(reason="Guest requesting exception to hotel policy")
    assert result.skill_name == "escalate_to_human"
    assert result.risk_flag is not None
    assert len(result.action_plan) == 0


def test_modify_reservation(pms):
    from app.agent.skills import modify_reservation
    result = modify_reservation(
        pms=pms,
        reservation_id="RES001",
        check_in="2025-04-24",
        check_out="2025-04-26",
    )
    assert result.skill_name == "modify_reservation"
    assert result.risk_flag is None

    executed = result.execute_actions(pms)
    assert executed is True

    res = pms.get_reservation("RES001")
    assert res.check_in == "2025-04-24"
