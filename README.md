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

Then send requests via Postman or curl:

```bash
# JSON response (action plan + metadata + email HTML)
curl -X POST http://localhost:8000/process-email \
  -H "Content-Type: application/json" \
  -d '{"sender_email": "someone@email.com", "body": "Do you have rooms April 20-22?"}'

# HTML response (rendered email, viewable in Postman Preview tab)
curl -X POST "http://localhost:8000/process-email?response_format=html" \
  -H "Content-Type: application/json" \
  -d '{"sender_email": "someone@email.com", "body": "Do you have rooms April 20-22?"}'
```

See `scenarios.md` for all test scenarios with ready-to-paste JSON bodies.

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

## Architecture Overview

```
Guest Email (Postman) --> FastAPI Endpoint --> ReAct Agent Loop --> Draft Reply + Action Plan
                                                    |
                                          +---------+---------+
                                          |                   |
                                       Tools               Skills
                                    (read-only)        (write workflows)
                                          |                   |
                                          +---------+---------+
                                                    |
                                               Mock PMS
                                          (in-memory JSON)
```

### Two-Layer Action System

The agent has access to **tools** and **skills** — this is the core architectural decision:

- **Tools** are atomic, read-only PMS lookups: `search_guest`, `check_availability`, `get_rate_plans`, `get_policies`, `get_hotel_info`, `get_reservation`, `get_guest_reservations`. The agent calls these freely to gather information.

- **Skills** are composed, multi-step workflows that perform writes: `book_room`, `modify_reservation`, `cancel_reservation`, `escalate_to_human`. Each skill validates inputs, checks preconditions, and produces an **action plan** (list of steps) and a **draft reply** before executing any writes.

This separation enables clean approval gating — writes only happen through skills, and skills can be paused for human review.

### Approval Modes

Configured via `approval_mode` in `config.toml`:

**Human approval mode** (`human_approval`): The agent gathers information using tools, then invokes skills to produce an action plan and draft reply. No write actions are executed. The server terminal displays the action plan and prompts the operator to type `approve` or `reject`. Only after approval does the system execute PMS writes and return the final email.

**Fully autonomous mode** (`autonomous`): The agent executes the full workflow end-to-end without human confirmation. However, requests flagged as risky (e.g., refund on non-refundable booking) are automatically escalated — no PMS writes happen and the guest receives an escalation email.

**Escalation behavior** (both modes): When a risk flag is present, the system never executes PMS writes. The agent drafts an escalation email to the guest ("we've forwarded this to our team") and the terminal logs the escalation reason. There is no override mechanism — risky requests always require human follow-up outside the system.

### ReAct Loop

The agent runs a Reason-Act-Observe cycle:

1. Claude receives the guest email + system prompt + all tool/skill schemas
2. Claude reasons about what's needed and calls a tool or skill
3. The tool/skill result is fed back as an observation
4. Claude reasons again — repeat until it produces a final text response
5. The text response becomes the draft reply to the guest

Max 15 iterations to prevent runaway loops. The server terminal shows real-time agent reasoning, tool calls, and results as each iteration executes.

### Presentation Layer

- **Postman** shows the guest-facing output: JSON with the HTML email + metadata, or just the rendered HTML email via `?response_format=html`
- **Server terminal** shows the operator view: agent thinking, tool/skill calls, action plans, and approval prompts

## Project Structure

```
hotel_aiemail/
├── app/
│   ├── main.py              # FastAPI app, POST /process-email, terminal logging, approval flow
│   ├── config.py            # Settings from .env (secrets) + config.toml (app config)
│   ├── models.py            # Pydantic models (Guest, Reservation, ActionStep, SkillResult, etc.)
│   ├── templates.py         # HTML email rendering with markdown-to-HTML conversion
│   ├── agent/
│   │   ├── react_agent.py   # ReAct loop, LLM interaction, action plan execution
│   │   ├── prompts.py       # System prompt template
│   │   ├── tools.py         # 7 read-only tool definitions + dispatcher
│   │   └── skills.py        # 4 write workflow implementations + dispatcher
│   └── services/
│       └── pms.py           # In-memory PMS (mock hotel data)
├── data/
│   └── mock_hotel_data.json # Mock PMS data (rooms, guests, reservations, availability)
├── tests/                   # 56 tests, all run without an API key
│   ├── test_pms.py          # 19 tests — PMS read/write operations, availability, pricing
│   ├── test_tools.py        # 9 tests — tool dispatch, error handling
│   ├── test_skills.py       # 8 tests — skill orchestration, escalation rules
│   ├── test_agent.py        # 3 tests — full ReAct loop with mocked LLM (all 3 required scenarios)
│   ├── test_api.py          # 5 tests — FastAPI endpoint, response formats, validation
│   ├── test_config.py       # 3 tests — TOML loading, defaults, overrides
│   ├── test_templates.py    # 7 tests — HTML rendering, markdown conversion, To/From
│   └── test_logging_callback.py # 2 tests — logging callback, backward compatibility
├── config.toml              # App configuration (mode, model, simulated date)
├── scenarios.md             # 15 test scenarios with ready-to-paste Postman bodies
└── pyproject.toml           # Dependencies (anthropic, pydantic, fastapi, uvicorn)
```

## Key Design Decisions

### Tools vs Skills

The task spec calls out "the usage of skills vs tools and how it performs full workflows" as critical. Rather than giving the LLM a flat list of CRUD operations, the system separates:

- **Tools** for information gathering (no side effects, call freely)
- **Skills** for actions (validate, produce a reviewable plan, then execute)

This means the LLM decides *what* skill to invoke and *with what parameters*, but the skill itself orchestrates the multi-step PMS workflow. The LLM doesn't need to remember to "first check availability, then create guest, then create reservation" — the `book_room` skill handles that sequence, validates preconditions, and calculates pricing.

### Deferred Execution via SkillResult

Skills return a `SkillResult` containing:
- `action_plan`: List of `ActionStep` objects describing what will happen
- `draft_reply`: Email text for the guest
- `risk_flag`: If set, blocks execution even in autonomous mode

In human approval mode, the agent loop returns the plan without executing it. The FastAPI endpoint then blocks on terminal input until the operator approves or rejects. In autonomous mode, the agent loop executes the plan immediately (unless risk-flagged).

### Escalation as a Skill

`escalate_to_human` is a skill, not a special case. The LLM treats escalation the same as any other action. Additionally, `cancel_reservation` and `modify_reservation` auto-escalate for non-refundable bookings at the skill level, providing a safety net even if the LLM misjudges.

### Single Agent, Not Multi-Agent

A supervisor + specialist agent architecture would add complexity without benefit at this scale. One agent with the right tools/skills handles all scenarios cleanly. The task spec says "we do not care about over-engineering."

### Raw Anthropic SDK

No LangChain, no LangGraph. The ReAct loop is straightforward Python using the Anthropic SDK directly. The evaluator can see exactly how tool dispatch, approval gating, and conversation management work. Nothing is hidden behind framework abstractions.

## Testing

```bash
uv run pytest tests/ -v
```

**56 tests total**, all run without an API key:

| Suite | Tests | What it covers |
|-------|-------|---------------|
| `test_pms.py` | 19 | PMS read/write operations, availability math, pricing |
| `test_tools.py` | 9 | Tool dispatch, schema validation, error handling |
| `test_skills.py` | 8 | Skill orchestration, escalation rules, execution |
| `test_agent.py` | 3 | Full ReAct loop with mocked LLM for all 3 required scenarios |
| `test_api.py` | 5 | FastAPI endpoint, JSON/HTML response formats, validation |
| `test_config.py` | 3 | TOML config loading, defaults, override precedence |
| `test_templates.py` | 7 | HTML rendering, markdown conversion, To/From display |
| `test_logging_callback.py` | 2 | Logging callback mechanism, backward compatibility |

## What I Would Improve Next

1. **Conversation threading**: Track email threads so follow-up emails have context from prior exchanges, enabling multi-turn guest conversations
2. **Persistent PMS**: Replace in-memory JSON with a database so PMS state survives server restarts
3. **Streaming responses**: Use Claude's streaming API for real-time feedback during long workflows
4. **Rate plan recommendation**: Add a skill that suggests the best rate plan based on guest preferences and stay length
5. **Multi-language support**: Detect guest language and respond accordingly (relevant for an Oslo hotel with international guests)
