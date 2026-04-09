# Hotel AI Email Agent

An AI-powered email agent for Grand Oslo Hotel that handles guest emails — answering questions, making bookings, modifying or cancelling reservations — using Claude with a ReAct (Reason-Act-Observe) loop.

## How to Run

```bash
# Install dependencies
uv sync

# Set your API key
echo "ANTHROPIC_API_KEY=your-key-here" > .env

# Run tests (no API key needed)
uv run pytest tests/ -v

# Start the server
uv run uvicorn app.main:app --reload
```

### Testing with Postman

1. Open Postman and create a new request
2. Set method to **POST** and URL to `http://localhost:8000/process-email?response_format=html`
3. Go to **Body** tab, select **raw**, choose **JSON** from the dropdown
4. Paste a scenario body:
   ```json
   {
     "sender_email": "someone@email.com",
     "body": "Do you have any available rooms April 20th-22nd?"
   }
   ```
5. Click **Send**
6. In the response area, click the **Preview** tab to see the rendered guest email
7. Check the server terminal for agent reasoning, tool calls, and action plans

In `human_approval` mode, the Postman request will wait while the server terminal prompts for `approve` or `reject`. Type your decision in the terminal and the response will appear in Postman.

For the JSON response with full metadata (action plan, status, mode, risk flag), use the URL without the query parameter: `http://localhost:8000/process-email`

See `scenarios.md` for all 15 test scenarios with ready-to-paste JSON bodies.

### Configuration

Secrets go in `.env`, app settings in `config.toml`:

```toml
# config.toml
[agent]
model = "claude-sonnet-4-20250514"
approval_mode = "human_approval"   # "human_approval" or "autonomous"
max_iterations = 15

[hotel]
data_path = "data/mock_hotel_data.json"
simulated_today = "2025-04-15"

[server]
host = "0.0.0.0"
port = 8000
```

Change `approval_mode` and restart the server to switch modes.

## Architecture

```
Guest Email (Postman) --> FastAPI Endpoint --> ReAct Agent Loop --> Draft Reply + Action Plan
                                                    |
                                          +---------+---------+
                                          |         |         |
                                        Skills    Tools    Guardrails
                                       (.md)    (read+write)  (prompt)
                                          |         |         |
                                          +---------+---------+
                                                    |
                                               Mock PMS
                                          (in-memory JSON)
```

### Skills, Tools, and Guardrails

The agent follows standard agent architecture with three layers:

**Skills** are markdown instruction files (`app/agent/skills/*.md`) that guide the LLM on how to handle each type of request. When a guest wants to book a room, the LLM reads the booking skill and follows its steps: search the guest, check availability, get rate plans, then call the write tool. Skills instruct — they don't execute.

**Tools** are all the operations the LLM can call — both read and write. There are 12 tools total:

| Tool | Type | Purpose |
|------|------|---------|
| `search_guest` | Read | Find guest by email |
| `get_reservation` | Read | Get reservation details |
| `get_guest_reservations` | Read | List guest's reservations |
| `check_availability` | Read | Available rooms for a date range |
| `get_rate_plans` | Read | Rate plans with pricing |
| `get_policies` | Read | Hotel policies |
| `get_hotel_info` | Read | Hotel metadata |
| `create_guest` | Write | Create a guest profile |
| `create_reservation` | Write | Book a room |
| `modify_reservation` | Write | Change a reservation |
| `cancel_reservation` | Write | Cancel a reservation |
| `escalate_to_human` | Escalation | Flag for human staff |

**Guardrails** are explicit rules in the system prompt that prevent costly LLM mistakes: never cancel a non-refundable booking (escalate instead), never book without checking availability first, never substitute a room type without asking, verify sender identity before modifying reservations.

### How the LLM Orchestrates

The LLM drives the workflow. It reads the skill instructions, calls tools step by step, reasons about each result, and composes the final email. The orchestrator (`react_agent.py`) handles the mechanics: dispatching tool calls, intercepting writes for approval, and assembling the response.

For example, when a guest asks to book a room:
1. LLM calls `search_guest` — finds the guest
2. LLM calls `check_availability` — sees rooms available
3. LLM calls `get_rate_plans` — picks the right rate
4. LLM calls `create_reservation` — orchestrator intercepts this write
5. LLM composes the confirmation email
6. Operator approves or rejects the action plan

### Approval Modes

**Human approval mode** (`human_approval`): Write tools are intercepted — they don't execute until the operator approves. The server terminal displays the action plan and prompts for `approve` or `reject`. Read tools execute freely.

**Autonomous mode** (`autonomous`): All tools execute immediately. However, escalations (via `escalate_to_human`) still flag the response for human review — the agent never silently processes risky requests.

**Escalation** (both modes): When the LLM follows a guardrail and calls `escalate_to_human`, the response gets a risk flag. No PMS writes happen. The guest receives an email explaining their request has been forwarded to staff.

### Safety Stack

Four layers prevent bad writes, no single layer is solely responsible:

| Layer | What it catches |
|-------|----------------|
| **Skills** (.md instructions) | LLM follows the correct workflow order |
| **Guardrails** (system prompt) | LLM avoids costly mistakes (non-refundable cancellation, booking without availability check) |
| **Approval gate** (orchestrator) | Human reviews write tools before execution (human_approval mode only) |
| **PMS validation** (data layer) | Rejects impossible writes (no rooms available, already cancelled) |

### ReAct Loop

The agent runs a Reason-Act-Observe cycle:

1. Claude receives the guest email + system prompt (persona, guardrails, skills) + all 12 tool schemas
2. Claude reasons about what's needed and calls a tool
3. The tool result is fed back as an observation
4. Claude reasons again — repeat until it produces a final text response
5. The text response becomes the draft reply to the guest

Max 15 iterations. The server terminal shows real-time agent reasoning, tool calls, and results.

### Presentation Layer

- **Postman** shows the guest-facing output: JSON with the HTML email + metadata, or rendered HTML via `?response_format=html`
- **Server terminal** shows the operator view: agent thinking, tool calls (labeled `[tool]` for reads, `[write]` for writes), action plans, and approval prompts

## Project Structure

```
hotel_aiemail/
├── app/
│   ├── main.py              # FastAPI app, POST /process-email, terminal logging, approval flow
│   ├── config.py            # Settings from .env (secrets) + config.toml (app config)
│   ├── models.py            # Pydantic models (Guest, Reservation, PendingAction, AgentResponse)
│   ├── templates.py         # HTML email rendering with markdown-to-HTML conversion
│   ├── agent/
│   │   ├── react_agent.py   # ReAct loop, write tool interception, approval gating
│   │   ├── prompts.py       # System prompt (persona + guardrails) + skill loader
│   │   ├── skills/          # Markdown workflow instructions
│   │   │   ├── book_room.md
│   │   │   ├── cancel_reservation.md
│   │   │   ├── modify_reservation.md
│   │   │   └── escalate.md
│   │   └── tools/           # All 12 tool schemas + handlers
│   │       ├── __init__.py  # get_tool_schemas(), execute_tool(), WRITE_TOOL_NAMES
│   │       ├── read_tools.py
│   │       ├── write_tools.py
│   │       └── escalation.py
│   └── services/
│       └── pms.py           # In-memory PMS (mock hotel data)
├── data/
│   └── mock_hotel_data.json # Mock PMS data (rooms, guests, reservations, availability)
├── tests/                   # 60 tests, all run without an API key
├── config.toml              # App configuration (mode, model, simulated date)
├── scenarios.md             # 15 test scenarios with ready-to-paste Postman bodies
└── pyproject.toml           # Dependencies (anthropic, pydantic, fastapi, uvicorn)
```

## Design Decisions

### Standard Agent Architecture

The agent follows the standard pattern: **skills instruct, tools execute, the LLM orchestrates**. Skills are markdown files that describe workflows. Tools handle both reads and writes. The LLM reasons through each step, calling tools as needed. The orchestrator intercepts write tools for approval gating.

### Write Tool Interception

Instead of building a custom action-plan framework, the orchestrator intercepts write tool calls at the dispatch level. In human approval mode, write tools return a "pending approval" stub to the LLM and get recorded as `PendingAction` entries. After the LLM finishes reasoning, the collected actions are presented to the operator. This keeps the LLM in control of orchestration while the system controls execution.

### Guardrails Over Code Validation

Business rules (don't cancel non-refundable bookings, always check availability before booking) are enforced as guardrails in the system prompt rather than as validation logic inside tools. This keeps tools thin and composable. The approval gate and PMS validation provide additional safety layers.

### Single Agent, Not Multi-Agent

One agent with skills, tools, and guardrails handles all scenarios. A supervisor + specialist architecture would add complexity without benefit at this scale.

### Raw Anthropic SDK

No LangChain, no LangGraph. The ReAct loop is straightforward Python using the Anthropic SDK directly. Tool dispatch, approval gating, and conversation management are visible in the code without framework abstractions.

## Testing

```bash
uv run pytest tests/ -v
```

**60 tests total**, all run without an API key:

| Suite | Tests | What it covers |
|-------|-------|---------------|
| `test_pms.py` | 19 | PMS read/write operations, availability math, pricing |
| `test_tools.py` | 16 | All 12 tools: read, write, escalation, schema validation, error handling |
| `test_agent.py` | 8 | Full ReAct loop with mocked LLM: booking, cancellation, escalation, modification, autonomous mode, multi-action |
| `test_api.py` | 5 | FastAPI endpoint, JSON/HTML response formats, validation |
| `test_templates.py` | 7 | HTML rendering, markdown conversion, To/From display |
| `test_config.py` | 3 | TOML config loading, defaults, override precedence |
| `test_logging_callback.py` | 2 | Logging callback mechanism |
