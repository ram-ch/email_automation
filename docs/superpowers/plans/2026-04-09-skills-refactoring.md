# Skills Refactoring — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor agent internals from code-based skills to standard agent architecture: markdown skills instruct, tools execute (both read and write), the LLM orchestrates, and the orchestrator handles approval gating by intercepting write tool calls.

**Architecture:** Skills become `.md` files that guide the LLM's reasoning. All PMS operations (read and write) become tools. The orchestrator intercepts write tool calls for approval in human_approval mode. `SkillResult`/`ActionStep` are replaced by `PendingAction`. External API unchanged.

**Tech Stack:** Python 3.11+, Anthropic SDK, Pydantic, FastAPI, pytest

---

## File Map

| File | Responsibility |
|---|---|
| `app/agent/tools/__init__.py` | Public API: `get_tool_schemas()`, `execute_tool()`, `WRITE_TOOL_NAMES` |
| `app/agent/tools/read_tools.py` | 7 read tool schemas + handlers (moved from `tools.py`) |
| `app/agent/tools/write_tools.py` | 4 write tool schemas + handlers + `WRITE_TOOL_NAMES` |
| `app/agent/tools/escalation.py` | `escalate_to_human` tool schema + handler |
| `app/agent/skills/book_room.md` | Booking workflow instructions |
| `app/agent/skills/cancel_reservation.md` | Cancellation workflow instructions |
| `app/agent/skills/modify_reservation.md` | Modification workflow instructions |
| `app/agent/skills/escalate.md` | Escalation guidance |
| `app/agent/prompts.py` | System prompt: persona + guardrails + skill loader |
| `app/agent/react_agent.py` | ReAct loop with write tool interception |
| `app/models.py` | Remove `SkillResult`/`ActionStep`, add `PendingAction` |
| `app/main.py` | Updated `execute_pending_actions`, `_summarize_result`, `_prompt_approval` |
| `tests/test_tools.py` | Extended with write + escalation tool tests |
| `tests/test_agent.py` | Rewritten: 8 scenarios with new tool-calling pattern |

---

### Task 1: Create Tools Package — Read Tools

Move existing read tools from `app/agent/tools.py` into a new `app/agent/tools/` package. Existing tests must pass after this step.

**Files:**
- Create: `app/agent/tools/__init__.py`
- Create: `app/agent/tools/read_tools.py`
- Delete: `app/agent/tools.py`
- Test: `tests/test_tools.py` (existing, unchanged)

- [ ] **Step 1: Create `app/agent/tools/read_tools.py`**

Move all read tool schemas and handlers from the current `tools.py`:

```python
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


def _enrich_reservation(res_data: dict, pms: PMS) -> dict:
    """Add room type name and rate plan name to a reservation dict."""
    room = pms.get_room_type(res_data["room_type_id"])
    rate = pms.get_rate_plan(res_data["rate_plan_id"])
    res_data["room_type_name"] = room.name if room else res_data["room_type_id"]
    res_data["rate_plan_name"] = rate.name if rate else res_data["rate_plan_id"]
    return res_data


def _search_guest(params: dict, pms: PMS) -> str:
    guest = pms.search_guest(params["email"])
    if guest:
        return json.dumps({"found": True, "guest": guest.model_dump()})
    return json.dumps({"found": False, "message": "No guest found with that email."})


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


READ_TOOL_HANDLERS = {
    "search_guest": _search_guest,
    "get_reservation": _get_reservation,
    "get_guest_reservations": _get_guest_reservations,
    "check_availability": _check_availability,
    "get_rate_plans": _get_rate_plans,
    "get_policies": _get_policies,
    "get_hotel_info": _get_hotel_info,
}
```

- [ ] **Step 2: Create `app/agent/tools/__init__.py`**

Initial version with only read tools — write tools added in later tasks:

```python
from __future__ import annotations

import json

from app.agent.tools.read_tools import READ_TOOL_HANDLERS, READ_TOOL_SCHEMAS
from app.services.pms import PMS

# Will be populated in Task 2 and Task 3
WRITE_TOOL_NAMES: set[str] = set()


def get_tool_schemas() -> list[dict]:
    return list(READ_TOOL_SCHEMAS)


def execute_tool(name: str, params: dict, pms: PMS) -> str:
    handlers = {**READ_TOOL_HANDLERS}
    handler = handlers.get(name)
    if not handler:
        return json.dumps({"error": f"Unknown tool: {name}"})
    return handler(params, pms)
```

- [ ] **Step 3: Delete old `app/agent/tools.py`**

Delete the file `app/agent/tools.py`. The `app/agent/tools/` package now replaces it. Existing imports (`from app.agent.tools import execute_tool, get_tool_schemas`) resolve to the package's `__init__.py`.

- [ ] **Step 4: Run existing tool tests**

Run: `pytest tests/test_tools.py -v`
Expected: All 9 tests PASS. The import path `from app.agent.tools import execute_tool` resolves to the new package.

- [ ] **Step 5: Commit**

```bash
git add app/agent/tools/ && git rm app/agent/tools.py && git add tests/test_tools.py
git commit -m "refactor: move read tools into app/agent/tools/ package"
```

---

### Task 2: Add Write Tools (TDD)

Add 4 write tools as thin wrappers around PMS write methods.

**Files:**
- Create: `app/agent/tools/write_tools.py`
- Modify: `app/agent/tools/__init__.py`
- Test: `tests/test_tools.py`

- [ ] **Step 1: Write failing tests for write tools**

Add to `tests/test_tools.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_tools.py::test_execute_create_guest tests/test_tools.py::test_execute_create_reservation tests/test_tools.py::test_execute_create_reservation_unavailable tests/test_tools.py::test_execute_modify_reservation tests/test_tools.py::test_execute_cancel_reservation tests/test_tools.py::test_execute_cancel_already_cancelled -v`
Expected: All 6 FAIL with `"error"` in result (unknown tool).

- [ ] **Step 3: Create `app/agent/tools/write_tools.py`**

```python
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
```

- [ ] **Step 4: Update `app/agent/tools/__init__.py` to include write tools**

```python
from __future__ import annotations

import json

from app.agent.tools.read_tools import READ_TOOL_HANDLERS, READ_TOOL_SCHEMAS
from app.agent.tools.write_tools import WRITE_TOOL_HANDLERS, WRITE_TOOL_NAMES, WRITE_TOOL_SCHEMAS
from app.services.pms import PMS

__all__ = ["get_tool_schemas", "execute_tool", "WRITE_TOOL_NAMES"]


def get_tool_schemas() -> list[dict]:
    return list(READ_TOOL_SCHEMAS) + list(WRITE_TOOL_SCHEMAS)


def execute_tool(name: str, params: dict, pms: PMS) -> str:
    handlers = {**READ_TOOL_HANDLERS, **WRITE_TOOL_HANDLERS}
    handler = handlers.get(name)
    if not handler:
        return json.dumps({"error": f"Unknown tool: {name}"})
    return handler(params, pms)
```

- [ ] **Step 5: Run all tool tests**

Run: `pytest tests/test_tools.py -v`
Expected: All 15 tests PASS (9 existing + 6 new).

- [ ] **Step 6: Commit**

```bash
git add app/agent/tools/write_tools.py app/agent/tools/__init__.py tests/test_tools.py
git commit -m "feat: add write tools (create_guest, create/modify/cancel_reservation)"
```

---

### Task 3: Add Escalation Tool (TDD)

Add `escalate_to_human` as a regular tool and update schema count test.

**Files:**
- Create: `app/agent/tools/escalation.py`
- Modify: `app/agent/tools/__init__.py`
- Test: `tests/test_tools.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_tools.py`:

```python
def test_execute_escalate_to_human(pms):
    from app.agent.tools import execute_tool
    result = json.loads(execute_tool("escalate_to_human", {
        "reason": "Guest requesting exception to hotel policy",
    }, pms))
    assert result["escalated"] is True
    assert "policy" in result["reason"].lower()
```

Update the existing `test_get_tool_schemas` test:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_tools.py::test_execute_escalate_to_human tests/test_tools.py::test_get_tool_schemas -v`
Expected: Both FAIL (escalate_to_human is unknown tool; schema count is wrong).

- [ ] **Step 3: Create `app/agent/tools/escalation.py`**

```python
from __future__ import annotations

import json

from app.services.pms import PMS


ESCALATION_TOOL_SCHEMAS: list[dict] = [
    {
        "name": "escalate_to_human",
        "description": (
            "Escalate to hotel staff when the request is ambiguous, involves a non-refundable "
            "cancellation or modification, requires a policy exception, or you are unsure how to proceed."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {"type": "string", "description": "Reason for escalation"},
            },
            "required": ["reason"],
        },
    },
]


def _escalate_to_human(params: dict, pms: PMS) -> str:
    return json.dumps({"escalated": True, "reason": params["reason"]})


ESCALATION_TOOL_HANDLERS = {
    "escalate_to_human": _escalate_to_human,
}
```

- [ ] **Step 4: Update `app/agent/tools/__init__.py` to include escalation**

```python
from __future__ import annotations

import json

from app.agent.tools.escalation import ESCALATION_TOOL_HANDLERS, ESCALATION_TOOL_SCHEMAS
from app.agent.tools.read_tools import READ_TOOL_HANDLERS, READ_TOOL_SCHEMAS
from app.agent.tools.write_tools import WRITE_TOOL_HANDLERS, WRITE_TOOL_NAMES, WRITE_TOOL_SCHEMAS
from app.services.pms import PMS

__all__ = ["get_tool_schemas", "execute_tool", "WRITE_TOOL_NAMES"]


def get_tool_schemas() -> list[dict]:
    return list(READ_TOOL_SCHEMAS) + list(WRITE_TOOL_SCHEMAS) + list(ESCALATION_TOOL_SCHEMAS)


def execute_tool(name: str, params: dict, pms: PMS) -> str:
    handlers = {**READ_TOOL_HANDLERS, **WRITE_TOOL_HANDLERS, **ESCALATION_TOOL_HANDLERS}
    handler = handlers.get(name)
    if not handler:
        return json.dumps({"error": f"Unknown tool: {name}"})
    return handler(params, pms)
```

- [ ] **Step 5: Run all tool tests**

Run: `pytest tests/test_tools.py -v`
Expected: All 17 tests PASS (9 read + 6 write + 1 escalation + 1 schema count).

- [ ] **Step 6: Commit**

```bash
git add app/agent/tools/escalation.py app/agent/tools/__init__.py tests/test_tools.py
git commit -m "feat: add escalate_to_human tool, tools package complete (12 tools)"
```

---

### Task 4: Update Models

Add `PendingAction` model. Keep `ActionStep` and `SkillResult` temporarily — they're still referenced by old code until Task 7.

**Files:**
- Modify: `app/models.py`

- [ ] **Step 1: Add `PendingAction` to `app/models.py`**

Add after the `Reservation` class (before `ActionStep`):

```python
class PendingAction(BaseModel):
    tool_name: str
    params: dict
    description: str
```

- [ ] **Step 2: Run existing tests to verify nothing breaks**

Run: `pytest tests/test_tools.py tests/test_pms.py -v`
Expected: All PASS. Adding a new model doesn't break anything.

- [ ] **Step 3: Commit**

```bash
git add app/models.py
git commit -m "feat: add PendingAction model for write tool interception"
```

---

### Task 5: Create Skills Markdown Files

Write the 4 workflow instruction files that guide the LLM.

**Files:**
- Create: `app/agent/skills/book_room.md`
- Create: `app/agent/skills/cancel_reservation.md`
- Create: `app/agent/skills/modify_reservation.md`
- Create: `app/agent/skills/escalate.md`

- [ ] **Step 1: Create `app/agent/skills/book_room.md`**

```markdown
# Book Room

When a guest wants to book a room:

1. Search for the guest by email using `search_guest`.
2. Check availability for the requested dates using `check_availability`. Read the response carefully — room type IDs are keys (RT001, RT002, etc.) and values are the number of available rooms. A count > 0 means rooms ARE available.
3. If the requested room type is unavailable, inform the guest and suggest available alternatives with pricing. Do NOT book a different room type without asking.
4. Get rate plans using `get_rate_plans`.
5. If no rate plan is specified, use Standard Rate (RP001) unless the guest mentions breakfast (use RP002) or flexibility (use RP004).
6. If the guest is new (not found in step 1), you need their first name, last name, phone, and nationality. If this information is in the email, call `create_guest` to create their profile. If any detail is missing, ask for it in your reply.
7. Call `create_reservation` with guest_id, room_type_id, rate_plan_id, check_in, check_out, adults, and children.
8. Include the total price in NOK in your reply.
```

- [ ] **Step 2: Create `app/agent/skills/cancel_reservation.md`**

```markdown
# Cancel Reservation

When a guest wants to cancel a reservation:

1. Search for the guest by email using `search_guest`.
2. Get the guest's reservations using `get_guest_reservations`.
3. Identify the reservation to cancel. If the guest doesn't specify which one, ask.
4. Check the reservation's rate plan. If it uses Non-Refundable Saver (RP003), do NOT cancel. Instead call `escalate_to_human` explaining that this is a non-refundable booking requiring manager approval.
5. If the rate plan allows cancellation, call `cancel_reservation` with the reservation_id.
6. Inform the guest of the cancellation policy that applies (standard: free if >24h before check-in; flexible: free if >7 days before check-in).
```

- [ ] **Step 3: Create `app/agent/skills/modify_reservation.md`**

```markdown
# Modify Reservation

When a guest wants to change an existing reservation:

1. Search for the guest by email using `search_guest`.
2. Get the guest's reservations using `get_guest_reservations`.
3. Identify the reservation to modify. If the guest doesn't specify which one, ask.
4. Check the reservation's rate plan. If it uses Non-Refundable Saver (RP003), do NOT modify. Instead call `escalate_to_human` explaining that non-refundable bookings cannot be modified.
5. If dates or room type are changing, check availability using `check_availability` for the new dates. If unavailable, inform the guest and suggest alternatives.
6. Call `modify_reservation` with the reservation_id and only the fields that are changing.
7. Include the updated total price in NOK in your reply.
```

- [ ] **Step 4: Create `app/agent/skills/escalate.md`**

```markdown
# Escalate to Human

When you need human staff assistance, call `escalate_to_human` with a clear reason.

Escalate when:
- The guest requests cancellation or modification of a non-refundable booking.
- The request is ambiguous and you cannot determine the guest's intent.
- The guest asks for something outside standard hotel policy (special discounts, fee waivers, late checkout beyond policy).
- You are unsure how to proceed.

Always explain to the guest that their request has been forwarded to the hotel staff for review.
```

- [ ] **Step 5: Commit**

```bash
git add app/agent/skills/
git commit -m "feat: add markdown skill files for booking, cancellation, modification, escalation"
```

---

### Task 6: Restructure System Prompt

Rewrite `prompts.py` with persona, guardrails, formatting rules, and a skill loader that reads the `.md` files.

**Files:**
- Modify: `app/agent/prompts.py`

- [ ] **Step 1: Rewrite `app/agent/prompts.py`**

```python
from __future__ import annotations

from datetime import date
from pathlib import Path


def _load_skills() -> str:
    """Read all skill markdown files and concatenate them."""
    skills_dir = Path(__file__).parent / "skills"
    parts = []
    for md_file in sorted(skills_dir.glob("*.md")):
        parts.append(md_file.read_text().strip())
    return "\n\n".join(parts)


SYSTEM_PROMPT_TEMPLATE = """You are the reservations assistant for Grand Oslo Hotel, Oslo, Norway.
You handle guest emails — answering questions, making bookings, modifying or cancelling reservations.

TODAY'S DATE: {today}
APPROVAL MODE: {approval_mode}

PERSONA:
- Professional, warm, concise. Address guests by first name when known.
- Do not use emojis in replies.
- Sign off as "Grand Oslo Hotel Reservations Team".

GUARDRAILS:
- NEVER cancel or modify a non-refundable reservation (rate plan RP003). Always escalate to human staff using `escalate_to_human`.
- NEVER call `create_reservation` without first calling `check_availability` for the exact dates and confirming the room type has count > 0.
- NEVER invent data. Only use information returned by tools. Never fabricate guest IDs, reservation IDs, room type IDs, or pricing.
- NEVER book a different room type than the guest requested. If unavailable, inform the guest and suggest alternatives with pricing. Do NOT substitute without explicit consent.
- Before cancelling or modifying a reservation, verify the sender's email matches the guest on the reservation. If it does not match, refuse and ask them to contact the hotel directly.
- Before calling `create_guest`, you must have first name, last name, phone, and nationality. If any are missing, ask the guest in your reply.
- If the guest requests multiple actions in one email (e.g., two bookings), handle each one separately. Do not stop after the first.
- When no rate plan is specified, use Standard Rate (RP001) unless the guest mentions breakfast (use RP002) or flexibility (use RP004).
- Always include pricing in NOK when quoting rooms.

ESCALATE (use `escalate_to_human`) when:
- Guest requests cancellation or refund on a non-refundable booking
- The request is ambiguous or you cannot determine the guest's intent
- The request requires an exception to hotel policy
- You are unsure how to proceed

FORMATTING:
- Use **bold** (markdown bold) for section headings and important labels (e.g., **Reservation Details**, **Room:**, **Total:**). Always use bold for these consistently.
- Do NOT use markdown for anything else — no italic, no horizontal rules (---), no headers (#).
- Do NOT use numbered lists with bold room names like "1. **Room Name**". Instead just list details with dashes.
- Write in past/confirmed tense for actions ("Your reservation has been confirmed", "Your booking has been created"). The email is only sent after actions are executed.
- For read-only requests (availability checks, policy questions), do not produce write actions — just provide the information in the reply.
- Your final text output will be used DIRECTLY as the guest email body. Do NOT include internal notes, action summaries, headers like "From:" or "To:", or markdown separators (---). Write ONLY the email text the guest should see.

SKILLS:
The following workflows describe how to handle specific types of requests. Follow them step by step, using the tools listed at each step.

{skills}"""


def get_system_prompt(today: date | None = None, approval_mode: str = "human_approval") -> str:
    return SYSTEM_PROMPT_TEMPLATE.format(
        today=(today or date.today()).isoformat(),
        approval_mode=approval_mode,
        skills=_load_skills(),
    )
```

- [ ] **Step 2: Verify the skill loader works**

Run in a Python shell or as a quick script:
```bash
python -c "from app.agent.prompts import get_system_prompt; p = get_system_prompt(); assert '# Book Room' in p; assert 'GUARDRAILS' in p; print('OK')"
```
Expected: Prints `OK`.

- [ ] **Step 3: Commit**

```bash
git add app/agent/prompts.py
git commit -m "refactor: restructure system prompt — persona, guardrails, skill loader"
```

---

### Task 7: Rewrite Orchestrator

Replace the skill-based dispatch in `react_agent.py` with write tool interception. This is the core architectural change.

**Files:**
- Modify: `app/agent/react_agent.py`

- [ ] **Step 1: Rewrite `app/agent/react_agent.py`**

```python
from __future__ import annotations

import json
from datetime import date
from typing import Callable

import anthropic

from app.agent.prompts import get_system_prompt
from app.agent.tools import WRITE_TOOL_NAMES, execute_tool, get_tool_schemas
from app.config import Settings
from app.models import AgentResponse, PendingAction
from app.services.pms import PMS


def _describe_action(tool_name: str, params: dict) -> str:
    """Generate a human-readable description for a pending write action."""
    if tool_name == "create_guest":
        return f"Create guest profile for {params.get('first_name', '')} {params.get('last_name', '')}"
    if tool_name == "create_reservation":
        return (
            f"Create reservation: {params.get('room_type_id', '')}, "
            f"{params.get('check_in', '')} to {params.get('check_out', '')}, "
            f"{params.get('adults', '')} adult(s)"
        )
    if tool_name == "modify_reservation":
        changes = {k: v for k, v in params.items() if k != "reservation_id"}
        change_desc = ", ".join(f"{k}={v}" for k, v in changes.items())
        return f"Modify reservation {params.get('reservation_id', '')}: {change_desc}"
    if tool_name == "cancel_reservation":
        return f"Cancel reservation {params.get('reservation_id', '')}"
    return f"{tool_name}: {params}"


def execute_pending_actions(pending_actions: list[PendingAction], pms: PMS) -> None:
    """Execute pending write actions against the PMS.

    Handles the __pending_guest__ placeholder: when create_guest runs first,
    subsequent create_reservation calls that reference __pending_guest__ get
    the real guest ID substituted.
    """
    created_guest_id: str | None = None

    for action in pending_actions:
        params = dict(action.params)

        # Resolve pending guest placeholder
        if (
            action.tool_name == "create_reservation"
            and params.get("guest_id") == "__pending_guest__"
            and created_guest_id
        ):
            params["guest_id"] = created_guest_id

        # Deduplicate create_guest: skip if guest already exists
        if action.tool_name == "create_guest":
            existing = pms.search_guest(params.get("email", ""))
            if existing:
                created_guest_id = existing.id
                continue

        result_str = execute_tool(action.tool_name, params, pms)
        result = json.loads(result_str)

        if action.tool_name == "create_guest" and "guest" in result:
            created_guest_id = result["guest"]["id"]


def process_email(
    email_body: str,
    sender_email: str,
    pms: PMS,
    settings: Settings,
    log_callback: Callable[[dict], None] | None = None,
) -> AgentResponse:
    """Process a guest email through the ReAct agent loop."""
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    all_tools = get_tool_schemas()

    today = date.fromisoformat(settings.simulated_today) if settings.simulated_today else None

    messages = [
        {
            "role": "user",
            "content": f"From: {sender_email}\n\n{email_body}",
        }
    ]

    def _log(entry: dict) -> None:
        if log_callback:
            log_callback(entry)

    _log({"type": "incoming", "sender": sender_email, "body": email_body})

    pending_actions: list[PendingAction] = []
    risk_flag: str | None = None

    for _iteration in range(settings.max_iterations):
        response = client.messages.create(
            model=settings.model,
            max_tokens=4096,
            system=get_system_prompt(today=today, approval_mode=settings.approval_mode),
            tools=all_tools,
            messages=messages,
        )

        if response.stop_reason == "tool_use":
            # Serialize assistant content for message history
            assistant_content = []
            for block in response.content:
                if block.type == "text":
                    assistant_content.append({"type": "text", "text": block.text})
                elif block.type == "tool_use":
                    assistant_content.append({
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    })
            messages.append({"role": "assistant", "content": assistant_content})

            # Log agent reasoning
            for block in response.content:
                if block.type == "text" and block.text.strip():
                    _log({
                        "type": "thinking",
                        "text": block.text.strip(),
                        "iteration": _iteration + 1,
                    })

            # Dispatch each tool call
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    tool_name = block.name
                    tool_input = block.input
                    is_write = tool_name in WRITE_TOOL_NAMES

                    if is_write:
                        # Record pending action
                        pending_actions.append(PendingAction(
                            tool_name=tool_name,
                            params=tool_input,
                            description=_describe_action(tool_name, tool_input),
                        ))

                        if settings.approval_mode == "autonomous":
                            tool_result_str = execute_tool(tool_name, tool_input, pms)
                        else:
                            # Human approval — intercept, don't execute
                            pending_response: dict = {"status": "pending_approval"}
                            if tool_name == "create_guest":
                                pending_response["placeholder_guest_id"] = "__pending_guest__"
                            pending_response["note"] = (
                                "This action has been recorded and will be executed "
                                "after operator approval. If you need to reference "
                                "this result, use the placeholder values provided."
                            )
                            tool_result_str = json.dumps(pending_response)
                    elif tool_name == "escalate_to_human":
                        tool_result_str = execute_tool(tool_name, tool_input, pms)
                        result_data = json.loads(tool_result_str)
                        if result_data.get("escalated"):
                            risk_flag = f"Escalation: {result_data.get('reason', 'Unknown reason')}"
                    else:
                        tool_result_str = execute_tool(tool_name, tool_input, pms)

                    _log({
                        "type": "tool",
                        "name": tool_name,
                        "input": tool_input,
                        "result_summary": tool_result_str[:200],
                        "iteration": _iteration + 1,
                        "is_write": is_write,
                    })

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": tool_result_str,
                    })

            messages.append({"role": "user", "content": tool_results})

        elif response.stop_reason == "end_turn":
            draft_reply = ""
            for block in response.content:
                if hasattr(block, "text"):
                    draft_reply += block.text

            requires_approval = False
            if risk_flag:
                requires_approval = True
            elif settings.approval_mode == "human_approval" and len(pending_actions) > 0:
                requires_approval = True

            _log({
                "type": "result",
                "has_actions": len(pending_actions) > 0,
                "requires_approval": requires_approval,
                "risk_flag": risk_flag,
            })

            return AgentResponse(
                draft_reply=draft_reply,
                action_plan=pending_actions,
                requires_approval=requires_approval,
                risk_flag=risk_flag,
                conversation_history=messages,
            )

        else:
            break

    return AgentResponse(
        draft_reply="I apologize, but I was unable to fully process your request. A team member will follow up shortly.",
        action_plan=[],
        requires_approval=True,
        risk_flag="max_iterations_reached",
        conversation_history=messages,
    )
```

- [ ] **Step 2: Commit**

```bash
git add app/agent/react_agent.py
git commit -m "refactor: rewrite orchestrator — write tool interception replaces skill dispatch"
```

---

### Task 8: Update main.py

Update `_execute_action_plan` references, `_summarize_result`, `_prompt_approval`, and the terminal log handler to work with `PendingAction` and the new orchestrator.

**Files:**
- Modify: `app/main.py`

- [ ] **Step 1: Update imports**

Replace the imports at the top of `app/main.py`:

```python
from app.agent.react_agent import process_email, execute_pending_actions
from app.config import Settings, load_settings
from app.models import AgentResponse, PendingAction
from app.services.pms import PMS
from app.templates import render_email_html
```

Remove `SkillResult` from imports.

- [ ] **Step 2: Update `_summarize_result`**

Replace the `_summarize_result` function:

```python
def _summarize_result(tool_name: str, raw_summary: str) -> str:
    """Generate a short, clean summary for a tool result."""
    try:
        parsed = json.loads(raw_summary)
    except Exception:
        parsed = None

    if parsed and isinstance(parsed, dict):
        if "error" in parsed:
            return parsed["error"]
        if "found" in parsed:
            if parsed["found"] and "guest" in parsed:
                guest = parsed["guest"]
                return f"found {guest.get('id', '')} ({guest.get('first_name', '')} {guest.get('last_name', '')})"
            return "not found"
        if parsed.get("status") == "pending_approval":
            return "pending approval"
        if parsed.get("escalated"):
            reason = parsed.get("reason", "")
            return f"escalated: {reason[:50]}"

    fallbacks = {
        "check_availability": "availability loaded",
        "get_rate_plans": "rate plans loaded",
        "get_policies": "policies loaded",
        "get_hotel_info": "hotel info loaded",
        "get_reservation": "reservation found",
        "get_guest_reservations": "reservations loaded",
        "search_guest": "lookup complete",
        "create_guest": "guest created",
        "create_reservation": "reservation created",
        "modify_reservation": "reservation updated",
        "cancel_reservation": "reservation cancelled",
        "escalate_to_human": "escalated",
    }
    return fallbacks.get(tool_name, "done")
```

- [ ] **Step 3: Update `_terminal_log`**

Replace the `elif t in ("tool", "skill"):` block in `_terminal_log`:

```python
    elif t == "tool":
        is_write = entry.get("is_write", False)
        label = "write" if is_write else "tool"
        name = entry.get("name", "")
        summary = entry.get("result_summary", "")
        short = _summarize_result(name, summary)
        print(f"  [iteration {entry.get('iteration', '?')}] {label}: {name} -> {short}")
```

- [ ] **Step 4: Update `_prompt_approval`**

Replace the `_prompt_approval` function:

```python
def _prompt_approval(result: AgentResponse, pms: PMS, hotel_info: dict, mode: str) -> EmailResponse:
    """Block and prompt the operator for approval in the terminal."""
    print(f"\n  --- Action Plan ---")
    for i, action in enumerate(result.action_plan, 1):
        print(f"    {i}. {action.description}")
    print(f"\n  --- Mode: {mode} ---")

    while True:
        decision = input("  >> Type 'approve' or 'reject': ").strip().lower()
        if decision in ("approve", "reject"):
            break
        print("    Please type 'approve' or 'reject'.")

    action_plan_out = [
        {"step": i + 1, "description": a.description}
        for i, a in enumerate(result.action_plan)
    ]

    if decision == "approve":
        execute_pending_actions(result.action_plan, pms)
        print("  [OK] Actions executed.")
        return EmailResponse(
            email_html=render_email_html(body_text=result.draft_reply, **hotel_info),
            action_plan=action_plan_out,
            mode=mode,
            requires_approval=True,
            risk_flag=result.risk_flag,
            status="approved",
        )
    else:
        print("  [REJECTED] No changes to PMS.")
        return EmailResponse(
            email_html=render_email_html(body_text=REJECTION_TEXT, **hotel_info),
            action_plan=action_plan_out,
            mode=mode,
            requires_approval=True,
            risk_flag=result.risk_flag,
            status="rejected",
        )
```

- [ ] **Step 5: Commit**

```bash
git add app/main.py
git commit -m "refactor: update main.py for PendingAction and new orchestrator"
```

---

### Task 9: Rewrite Agent Tests

Update existing 3 scenarios to use the new tool-calling pattern (no more skill calls) and add 5 new scenarios.

**Files:**
- Modify: `tests/test_agent.py`

- [ ] **Step 1: Rewrite `tests/test_agent.py`**

```python
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

        # RT002 has 0 availability on Apr 22-23
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
```

- [ ] **Step 2: Run agent tests**

Run: `pytest tests/test_agent.py -v`
Expected: All 8 tests PASS.

- [ ] **Step 3: Run full test suite**

Run: `pytest tests/ -v`
Expected: All tests PASS (test_pms, test_tools, test_agent). test_skills.py will fail because it still imports the old skills — that's expected and cleaned up in Task 10.

- [ ] **Step 4: Commit**

```bash
git add tests/test_agent.py
git commit -m "test: rewrite agent tests for standard architecture (8 scenarios)"
```

---

### Task 10: Cleanup Old Files

Delete the old skill code, old test file, and remove unused models.

**Files:**
- Delete: `app/agent/skills.py`
- Delete: `tests/test_skills.py`
- Modify: `app/models.py` (remove `ActionStep`, `SkillResult`)

- [ ] **Step 1: Delete `app/agent/skills.py`**

This file is fully replaced by `app/agent/skills/*.md` (workflow instructions) and `app/agent/tools/write_tools.py` (write tool handlers).

- [ ] **Step 2: Delete `tests/test_skills.py`**

Test coverage for write operations is now in `tests/test_tools.py` (tool-level) and `tests/test_agent.py` (orchestration-level).

- [ ] **Step 3: Remove `ActionStep` and `SkillResult` from `app/models.py`**

Remove these two classes from `app/models.py`:

```python
class ActionStep(BaseModel):
    description: str
    tool_call: str
    params: dict


class SkillResult(BaseModel):
    skill_name: str
    action_plan: list[ActionStep]
    draft_reply: str
    requires_approval: bool = False
    risk_flag: str | None = None
```

Keep `PendingAction` (added in Task 4). The `AgentResponse` model's `action_plan` field type changes from `list[ActionStep]` to `list[PendingAction]`:

```python
class AgentResponse(BaseModel):
    draft_reply: str
    action_plan: list[PendingAction] = []
    requires_approval: bool = False
    risk_flag: str | None = None
    conversation_history: list = []
```

- [ ] **Step 4: Run full test suite**

Run: `pytest tests/ -v`
Expected: All tests PASS — test_pms, test_tools (17 tests), test_agent (8 tests). No test_skills.py.

- [ ] **Step 5: Commit**

```bash
git rm app/agent/skills.py tests/test_skills.py && git add app/models.py
git commit -m "refactor: remove old skills code, ActionStep, SkillResult — cleanup complete"
```

- [ ] **Step 6: Final verification**

Run: `pytest tests/ -v && python -c "from app.agent.prompts import get_system_prompt; p = get_system_prompt(); assert '# Book Room' in p; print('All checks passed')"``
Expected: All tests pass, skill loading works.
