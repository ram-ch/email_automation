# Hotel AI Email Agent

An AI-powered email agent for Grand Oslo Hotel that handles guest emails — answering questions, making bookings, modifying or cancelling reservations — using Claude Opus with a ReAct (Reason-Act-Observe) loop.

## Quick Start

```bash
# Install dependencies
uv sync

# Set your API key
echo "ANTHROPIC_API_KEY=your-key-here" > .env

# Run tests (no API key needed)
uv run pytest tests/ -v

# Run live demo (requires API key)
uv run python run_scenarios.py

# Start FastAPI server
uv run uvicorn app.main:app --reload
```

## Architecture Overview

```
Guest Email → ReAct Agent Loop → Draft Reply + Action Plan
                    │
          ┌─────────┴─────────┐
          │                   │
       Tools               Skills
    (read-only)        (write workflows)
          │                   │
          └─────────┬─────────┘
                    │
               Mock PMS
          (in-memory JSON)
```

### Two-Layer Action System

The agent has access to **tools** and **skills** — this is the core architectural decision:

- **Tools** are atomic, read-only PMS lookups: `search_guest`, `check_availability`, `get_rate_plans`, `get_policies`, `get_hotel_info`, `get_reservation`, `get_guest_reservations`. The agent calls these freely to gather information.

- **Skills** are composed, multi-step workflows that perform writes: `book_room`, `modify_reservation`, `cancel_reservation`, `escalate_to_human`. Each skill produces an **action plan** (list of steps) and a **draft reply** before executing any writes.

This separation enables clean approval gating — writes only happen through skills, and skills can be paused for human review.

### Approval Modes

Configured via `APPROVAL_MODE` environment variable:

- **`human_approval`** (default): The agent gathers information and produces a plan + draft reply. Write actions are deferred until explicitly approved. The `AgentResponse` includes an `execute_pending` callable.

- **`autonomous`**: The agent executes the full workflow end-to-end. However, requests flagged as risky (e.g., refund on non-refundable booking) are still blocked and escalated for human review.

### ReAct Loop

The agent runs a Reason → Act → Observe cycle:

1. Claude receives the guest email + system prompt + all tool/skill schemas
2. Claude reasons about what's needed and calls a tool or skill
3. The tool/skill result is fed back as an observation
4. Claude reasons again — repeat until it produces a final text response
5. The text response becomes the draft reply to the guest

Max 15 iterations to prevent runaway loops.

## Project Structure

```
hotel_aiemail/
├── app/
│   ├── main.py              # FastAPI app + POST /process-email
│   ├── config.py            # Settings (approval mode, model, API key)
│   ├── models.py            # Pydantic models
│   ├── agent/
│   │   ├── react_agent.py   # ReAct loop + LLM interaction
│   │   ├── prompts.py       # System prompt
│   │   ├── tools.py         # Read-only tool definitions + dispatcher
│   │   └── skills.py        # Write workflow implementations
│   └── services/
│       └── pms.py           # In-memory PMS (mock hotel data)
├── data/
│   └── mock_hotel_data.json # Mock PMS data
├── tests/
│   ├── test_pms.py          # 19 tests — PMS read/write operations
│   ├── test_tools.py        # 9 tests — tool dispatch
│   ├── test_skills.py       # 8 tests — skill orchestration
│   └── test_agent.py        # 3 tests — full scenarios with mocked LLM
├── run_scenarios.py          # Live demo runner
└── pyproject.toml
```

## Key Design Decisions

### Tools vs Skills

The evaluator explicitly called out "the usage of skills vs tools and how it performs full workflows" as critical. Rather than giving the LLM a flat list of CRUD operations, the system separates:

- **Tools** for information gathering (no side effects, call freely)
- **Skills** for actions (produce a reviewable plan, then execute)

This means the LLM decides *what* skill to invoke and *with what parameters*, but the skill itself orchestrates the multi-step PMS workflow. The LLM doesn't need to remember to "first check availability, then create guest, then create reservation" — the `book_room` skill handles that sequence.

### Single Agent, Not Multi-Agent

A supervisor + specialist agent architecture would add complexity without real benefit at this scale. One agent with the right tools/skills handles all three scenarios cleanly. The task says "we do not care about over-engineering."

### Deferred Execution via SkillResult

Skills return a `SkillResult` with:
- `action_plan`: Human-readable list of what will happen
- `draft_reply`: Email text for the guest
- `execute_actions`: A callable that performs the actual PMS writes

This pattern makes approval gating trivial — in `human_approval` mode, the agent returns the plan without calling `execute_actions`. The caller can inspect the plan, then call `execute_actions(pms)` to proceed.

### Escalation as a Skill

`escalate_to_human` is a skill, not a special-case. This means the LLM treats escalation the same as any other action — it decides to escalate based on the system prompt's guidance, and the skill produces a standard `SkillResult` with a `risk_flag`. Additionally, `cancel_reservation` auto-escalates for non-refundable bookings, providing a safety net even if the LLM misjudges.

### Raw Anthropic SDK

No LangChain, no LangGraph. The ReAct loop is ~80 lines of Python. The evaluator can see exactly how tool dispatch, approval gating, and conversation management work. Nothing is hidden behind framework abstractions.

## Testing

```bash
uv run pytest tests/ -v
```

**39 tests total**, all run without an API key:

| Suite | Tests | What it covers |
|-------|-------|---------------|
| `test_pms.py` | 19 | PMS read/write operations, availability math, pricing |
| `test_tools.py` | 9 | Tool dispatch, schema validation, error handling |
| `test_skills.py` | 8 | Skill orchestration, escalation rules, execution |
| `test_agent.py` | 3 | Full ReAct loop with mocked LLM for all 3 required scenarios |

## API

```bash
# Start server
uv run uvicorn app.main:app --reload

# Process an email
curl -X POST http://localhost:8000/process-email \
  -H "Content-Type: application/json" \
  -d '{"email_body": "Do you have rooms April 20-22?", "sender_email": "guest@email.com"}'

# Health check
curl http://localhost:8000/health
```

## What I Would Improve Next

1. **Conversation threading**: Track email threads so follow-up emails have context from prior exchanges
2. **Persistent PMS**: Replace in-memory JSON with a proper database for production use
3. **Streaming responses**: Use Claude's streaming API for real-time feedback during long workflows
4. **Structured logging**: Add logging to track agent reasoning steps, tool calls, and decisions for debugging
5. **Rate plan recommendation**: Add a skill that suggests the best rate plan based on guest preferences and stay length
6. **Multi-language support**: Detect guest language and respond accordingly (relevant for an Oslo hotel)
