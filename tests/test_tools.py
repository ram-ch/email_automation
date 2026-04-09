import json


def test_execute_search_guest_found(pms):
    from app.agent.tools import execute_tool
    result = json.loads(execute_tool("search_guest", {"email": "erik.hansen@email.com"}, pms))
    assert result["found"] is True
    assert result["guest"]["first_name"] == "Erik"


def test_execute_search_guest_not_found(pms):
    from app.agent.tools import execute_tool
    result = json.loads(execute_tool("search_guest", {"email": "nobody@test.com"}, pms))
    assert result["found"] is False


def test_execute_check_availability(pms):
    from app.agent.tools import execute_tool
    result = json.loads(execute_tool("check_availability", {
        "check_in": "2025-04-20",
        "check_out": "2025-04-22",
    }, pms))
    assert "2025-04-20" in result["availability"]
    assert len(result["room_types"]) == 4


def test_execute_get_rate_plans(pms):
    from app.agent.tools import execute_tool
    result = json.loads(execute_tool("get_rate_plans", {}, pms))
    assert len(result["rate_plans"]) == 4


def test_execute_get_policies(pms):
    from app.agent.tools import execute_tool
    result = json.loads(execute_tool("get_policies", {}, pms))
    assert "cancellation" in result


def test_execute_get_guest_reservations(pms):
    from app.agent.tools import execute_tool
    result = json.loads(execute_tool("get_guest_reservations", {"guest_id": "G001"}, pms))
    assert len(result["reservations"]) == 2


def test_execute_get_reservation(pms):
    from app.agent.tools import execute_tool
    result = json.loads(execute_tool("get_reservation", {"reservation_id": "RES001"}, pms))
    assert result["reservation"]["guest_id"] == "G001"


def test_execute_unknown_tool(pms):
    from app.agent.tools import execute_tool
    result = json.loads(execute_tool("nonexistent_tool", {}, pms))
    assert "error" in result


def test_get_tool_schemas():
    from app.agent.tools import get_tool_schemas
    schemas = get_tool_schemas()
    names = [s["name"] for s in schemas]
    assert len(schemas) == 12
    # Read tools
    assert "search_guest" in names
    assert "check_availability" in names
    assert "get_rate_plans" in names
    assert "get_policies" in names
    assert "get_hotel_info" in names
    assert "get_guest_reservations" in names
    assert "get_reservation" in names
    # Write tools
    assert "create_guest" in names
    assert "create_reservation" in names
    assert "modify_reservation" in names
    assert "cancel_reservation" in names
    # Escalation
    assert "escalate_to_human" in names


def test_execute_create_guest(pms):
    from app.agent.tools import execute_tool
    result = json.loads(execute_tool("create_guest", {
        "first_name": "Test",
        "last_name": "User",
        "email": "test.user@email.com",
        "phone": "+47 000 00 000",
        "nationality": "NO",
    }, pms))
    assert "guest" in result
    assert result["guest"]["first_name"] == "Test"
    assert result["guest"]["id"].startswith("G")


def test_execute_create_reservation(pms):
    from app.agent.tools import execute_tool
    result = json.loads(execute_tool("create_reservation", {
        "guest_id": "G001",
        "room_type_id": "RT002",
        "rate_plan_id": "RP001",
        "check_in": "2025-04-24",
        "check_out": "2025-04-26",
        "adults": 2,
    }, pms))
    assert "reservation" in result
    assert result["reservation"]["guest_id"] == "G001"
    assert result["reservation"]["room_type_id"] == "RT002"


def test_execute_create_reservation_unavailable(pms):
    from app.agent.tools import execute_tool
    result = json.loads(execute_tool("create_reservation", {
        "guest_id": "G001",
        "room_type_id": "RT002",
        "rate_plan_id": "RP001",
        "check_in": "2025-04-22",
        "check_out": "2025-04-24",
        "adults": 2,
    }, pms))
    assert "error" in result


def test_execute_modify_reservation(pms):
    from app.agent.tools import execute_tool
    result = json.loads(execute_tool("modify_reservation", {
        "reservation_id": "RES001",
        "check_in": "2025-04-24",
        "check_out": "2025-04-26",
    }, pms))
    assert "reservation" in result
    assert result["reservation"]["check_in"] == "2025-04-24"


def test_execute_cancel_reservation(pms):
    from app.agent.tools import execute_tool
    result = json.loads(execute_tool("cancel_reservation", {
        "reservation_id": "RES001",
    }, pms))
    assert "reservation" in result
    assert result["reservation"]["status"] == "cancelled"


def test_execute_cancel_already_cancelled(pms):
    from app.agent.tools import execute_tool
    result = json.loads(execute_tool("cancel_reservation", {
        "reservation_id": "RES006",
    }, pms))
    assert "error" in result


def test_execute_escalate_to_human(pms):
    from app.agent.tools import execute_tool
    result = json.loads(execute_tool("escalate_to_human", {
        "reason": "Guest requesting exception to hotel policy",
    }, pms))
    assert result["escalated"] is True
    assert "policy" in result["reason"].lower()
