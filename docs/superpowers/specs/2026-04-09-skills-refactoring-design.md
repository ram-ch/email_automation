# Skills Refactoring — Standard Agent Architecture

## Goal

Refactor agent internals to follow standard agent architecture: **skills instruct, tools execute, the LLM orchestrates**. External API (`/process-email` endpoint, response shape, terminal output) stays the same.

## Project Structure (After Refactoring)

```
hotel_aiemail/
├── pyproject.toml
├── config.toml
├── data/
│   └── mock_hotel_data.json
├── app/
│   ├── __init__.py
│   ├── config.py
│   ├── models.py                    # Remove SkillResult/ActionStep, add PendingAction
│   ├── main.py                      # Updated to replay intercepted tool calls
│   ├── templates.py
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── react_agent.py           # Write tool interception + approval gating
│   │   ├── prompts.py               # Persona + guardrails + skill loader
│   │   ├── skills/                   # NEW — markdown workflow instructions
│   │   │   ├── book_room.md
│   │   │   ├── cancel_reservation.md
│   │   │   ├── modify_reservation.md
│   │   │   └── escalate.md
│   │   └── tools/                    # REPLACES tools.py — Python package
│   │       ├── __init__.py           # get_tool_schemas(), execute_tool()
│   │       ├── read_tools.py         # 7 read tool schemas + handlers
│   │       ├── write_tools.py        # 4 write tool schemas + handlers
│   │       └── escalation.py         # escalate_to_human schema + handler
│   └── services/
│       ├── __init__.py
│       └── pms.py                    # Unchanged
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_pms.py                   # Unchanged
│   ├── test_tools.py                 # Extended with write + escalation tool tests
│   └── test_agent.py                 # Expanded from 3 to 8 scenarios
└── README.md
```

**Deleted files:** `app/agent/skills.py`, `app/agent/tools.py`, `tests/test_skills.py`

## Architecture

### Skills — Markdown Workflow Instructions

Skills become `.md` files in `app/agent/skills/`. Each file describes a workflow the LLM follows when handling a specific type of request. All skill files are loaded at startup and injected into the system prompt under a `SKILLS` heading.

```
app/agent/skills/
  book_room.md
  cancel_reservation.md
  modify_reservation.md
  escalate.md
```

**Example — `skills/book_room.md`:**

```markdown
# Book Room

When a guest wants to book a room:

1. Search for the guest by email using `search_guest`
2. Check availability for the requested dates using `check_availability`
3. If unavailable, inform the guest and suggest available alternatives — do NOT book a different room without asking
4. Get rate plans using `get_rate_plans`
5. If no rate plan specified, use Standard Rate (RP001) unless guest mentions breakfast (RP002) or flexibility (RP004)
6. If the guest is new (not found), collect their first name, last name, phone, and nationality — create their profile using `create_guest`
7. Call `create_reservation` with all gathered parameters
```

The LLM reads these instructions and follows them step by step, calling tools at each point. Skills guide — they don't execute.

### Tools — Read and Write Operations

12 total tools: 7 existing read tools unchanged, 4 new write tools, and 1 escalation tool.

**New write tools:**

| Tool | PMS Method | Returns |
|---|---|---|
| `create_guest` | `pms.create_guest(...)` | `{"guest": {...}}` or `{"error": "..."}` |
| `create_reservation` | `pms.create_reservation(...)` | `{"reservation": {...}}` or `{"error": "Room unavailable"}` |
| `modify_reservation` | `pms.modify_reservation(...)` | `{"reservation": {...}}` or `{"error": "..."}` |
| `cancel_reservation` | `pms.cancel_reservation(...)` | `{"reservation": {...}}` or `{"error": "..."}` |

Write tools follow the same pattern as read tools: receive params, call PMS, return JSON string. No action plans, no draft replies, no special handling.

**Escalation tool:**

| Tool | Behavior | Returns |
|---|---|---|
| `escalate_to_human` | Sets risk flag on the response, no PMS writes | `{"escalated": true, "reason": "..."}` |

`escalate_to_human` is NOT a write tool — it executes immediately in both modes. It does not get intercepted for approval. It signals that the request needs human staff attention and sets the `risk_flag` on the `AgentResponse`.

**Directory structure:** Tools move from a single `tools.py` into an `app/agent/tools/` package:

```
app/agent/tools/
  __init__.py          # get_tool_schemas(), execute_tool() — public API
  read_tools.py        # 7 read tool schemas + handlers
  write_tools.py       # 4 write tool schemas + handlers
  escalation.py        # escalate_to_human schema + handler
```

`__init__.py` re-exports `get_tool_schemas()` and `execute_tool()` so existing imports (`from app.agent.tools import ...`) continue to work unchanged.

**Deleted:**
- `app/agent/skills.py` — entirely removed, replaced by `app/agent/skills/*.md`
- `app/agent/tools.py` — replaced by `app/agent/tools/` package
- `get_skill_schemas()` / `execute_skill()` — gone
- `SkillResult` model — gone
- `ActionStep` model — gone

### Orchestrator — Write Tool Interception

`react_agent.py` handles the ReAct loop with a new dispatch pattern:

```
LLM calls any tool → is it a write tool?
  → No: execute immediately, return result to LLM
  → Yes + human_approval mode: DON'T execute, record it, return "pending approval" to LLM
  → Yes + autonomous mode: execute immediately, return result to LLM
  → Yes + guardrail violation: DON'T execute, record it, return "escalated" to LLM
```

**Write tool detection:** `WRITE_TOOLS = {"create_guest", "create_reservation", "modify_reservation", "cancel_reservation"}`

**Action plan assembly:** The orchestrator builds the action plan from intercepted write tool calls during the loop. Each intercepted call becomes a `PendingAction` entry (tool name, params, human-readable description). This replaces `ActionStep`.

**Multi-step writes:** When the LLM calls multiple write tools (e.g., `create_guest` then `create_reservation` for a new guest booking), all are intercepted and collected. The full set is presented to the operator as one action plan at the end.

**`AgentResponse` stays the same shape** but is populated differently:
- `draft_reply` — from the LLM's final text output (unchanged)
- `action_plan` — built from intercepted write tool calls
- `requires_approval` — `True` if any write tools were intercepted in `human_approval` mode
- `risk_flag` — set if a guardrail was triggered

### Replacement model for `ActionStep`:

```python
class PendingAction(BaseModel):
    tool_name: str
    params: dict
    description: str  # human-readable, generated by orchestrator
```

### System Prompt Restructuring

The system prompt is restructured into clear sections:

**Stays in the system prompt:**
- **Persona** — identity, tone, sign-off style
- **Context** — today's date, approval mode
- **Guardrails** — explicit rules for costly mistake prevention (see below)
- **Formatting** — bold headings, no markdown headers, past tense, email body only
- **Skills** — loaded from `skills/*.md` files at startup

**Moves out:**
- The WORKFLOW section (currently lines 15-19) — moves to skill `.md` files
- The TOOL vs SKILL distinction — gone (there are only tools now)
- Tool-specific instructions like "first check_availability, then get_rate_plans" — moves to `skills/book_room.md`

### Guardrails

Scenarios where the LLM could make a costly mistake, identified by tracing every business rule currently in `skills.py` and every constraint in the system prompt.

**Financial guardrails:**
- NEVER cancel a non-refundable reservation. Always escalate to human staff.
- NEVER modify a non-refundable reservation. Always escalate to human staff.
- NEVER call `create_reservation` without first calling `check_availability` for the exact dates and confirming the room type has count > 0.

**Data integrity guardrails:**
- NEVER invent data. Only use information returned by tools. Never fabricate guest IDs, reservation IDs, room type IDs, or pricing.
- NEVER book a different room type than requested. If unavailable, inform the guest and suggest alternatives. Do NOT substitute without explicit consent.
- Before cancelling or modifying a reservation, verify the sender's email matches the guest on the reservation. If it does not match, refuse and ask them to contact the hotel directly.

**Completeness guardrails:**
- Before calling `create_guest`, you must have first name, last name, phone, and nationality. If any are missing, ask the guest.
- If the guest requests multiple actions in one email (e.g., two bookings), handle each one. Do not stop after the first.

**Escalation guardrails:**
- If you cannot determine what the guest wants, escalate using `escalate_to_human`.
- If the guest asks for something outside standard hotel policy (special discounts, fee waivers, late checkout beyond policy), escalate.
- If you are unsure how to proceed, escalate.

### Safety Stack

The safety model for this architecture has three layers. No tool-level validation is needed beyond what the PMS already provides.

| Layer | What it catches | Applies in |
|---|---|---|
| **Skills** (`.md` instructions) | LLM follows correct workflow order | Both modes |
| **Guardrails** (system prompt rules) | LLM avoids costly mistakes (non-refundable cancellation, booking without availability check) | Both modes |
| **Approval gate** (orchestrator intercepts write tools) | Human reviews before write executes | `human_approval` mode |
| **PMS validation** (data layer) | Rejects impossible writes (no rooms available, already cancelled) | Both modes |

## Testing Strategy

**`test_skills.py` — deleted.** No more Python skill functions to test.

**`test_tools.py` — extended with write tool tests:**
- `create_guest` — returns guest JSON with generated ID
- `create_reservation` — returns reservation JSON for valid input
- `create_reservation` — returns error when room unavailable
- `modify_reservation` — returns updated reservation
- `modify_reservation` — returns error when unavailable after change
- `cancel_reservation` — returns cancelled reservation
- `cancel_reservation` — returns error for already-cancelled reservation
- Unknown tool still returns error JSON
- `escalate_to_human` — returns escalation JSON with reason
- Schema list now contains all 12 tools

**`test_agent.py` — expanded to cover orchestration:**

Existing 3 scenarios stay (with updated mocked LLM responses):
- Scenario 1: Read-only inquiry — no writes, no approval
- Scenario 2: Booking — LLM calls `check_availability` then `create_reservation`, approval required in human mode
- Scenario 3: Non-refundable cancellation — LLM escalates based on guardrails

New scenarios:
- Scenario 4: New guest booking — LLM calls `create_guest` then `create_reservation`, both intercepted for approval
- Scenario 5: Modification — LLM calls `modify_reservation`, intercepted for approval
- Scenario 6: Unavailable room — LLM checks availability, gets zero count, suggests alternatives (no write tools called)
- Scenario 7: Autonomous mode — write tools execute immediately, no approval needed
- Scenario 8: Multiple actions in one email — LLM calls write tools for each, all collected in action plan

All agent tests use mocked LLM responses.

## File Changes

**New files:**
```
app/agent/skills/book_room.md
app/agent/skills/cancel_reservation.md
app/agent/skills/modify_reservation.md
app/agent/skills/escalate.md
app/agent/tools/__init__.py
app/agent/tools/read_tools.py
app/agent/tools/write_tools.py
app/agent/tools/escalation.py
```

**Modified files:**

| File | Change |
|---|---|
| `app/agent/prompts.py` | Restructure to persona + guardrails + skill loader (reads `app/agent/skills/*.md`) |
| `app/agent/react_agent.py` | Remove skill dispatch, add write tool interception, build action plan from intercepted calls |
| `app/models.py` | Remove `SkillResult`, `ActionStep`, add `PendingAction` |
| `app/main.py` | Update `_execute_action_plan` to replay intercepted tool calls, update `_summarize_result` |
| `tests/test_tools.py` | Add write tool + escalation tool tests |
| `tests/test_agent.py` | Update existing 3 scenarios, add 5 new scenarios |

**Deleted files:**

| File | Reason |
|---|---|
| `app/agent/skills.py` | Replaced by `app/agent/skills/*.md` + `app/agent/tools/write_tools.py` |
| `app/agent/tools.py` | Replaced by `app/agent/tools/` package |
| `tests/test_skills.py` | Covered by expanded `test_tools.py` and `test_agent.py` |

**Unchanged files:**
- `app/services/pms.py`
- `app/config.py`
- `data/mock_hotel_data.json`
- `app/templates.py`
