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
