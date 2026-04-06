from __future__ import annotations

import json
from datetime import date

import anthropic

from app.agent.prompts import get_system_prompt
from app.agent.skills import execute_skill, get_skill_schemas
from app.agent.tools import execute_tool, get_tool_schemas
from app.config import Settings
from app.models import AgentResponse
from app.services.pms import PMS


def process_email(
    email_body: str,
    sender_email: str,
    pms: PMS,
    settings: Settings,
) -> AgentResponse:
    """Process a guest email through the ReAct agent loop."""
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    all_tools = get_tool_schemas() + get_skill_schemas()

    # Determine today's date (support simulated date for demo with mock data)
    today = date.fromisoformat(settings.simulated_today) if settings.simulated_today else None

    messages = [
        {
            "role": "user",
            "content": f"From: {sender_email}\n\n{email_body}",
        }
    ]

    skill_result = None

    for _iteration in range(settings.max_iterations):
        response = client.messages.create(
            model=settings.model,
            max_tokens=4096,
            system=get_system_prompt(today=today),
            tools=all_tools,
            messages=messages,
        )

        # Check if the model wants to use tools
        if response.stop_reason == "tool_use":
            # Serialize assistant content blocks for the message history
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

            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    tool_name = block.name
                    tool_input = block.input

                    # Check if it's a skill or a tool
                    skill_names = {s["name"] for s in get_skill_schemas()}
                    if tool_name in skill_names:
                        skill_result = execute_skill(tool_name, tool_input, pms)
                        # Handle approval mode
                        if settings.approval_mode == "autonomous" and not skill_result.risk_flag:
                            if hasattr(skill_result, "execute_actions") and callable(skill_result.execute_actions):
                                skill_result.execute_actions(pms)
                                for step in skill_result.action_plan:
                                    if step.status == "pending":
                                        step.status = "executed"

                        tool_result_str = json.dumps({
                            "skill_name": skill_result.skill_name,
                            "action_plan": [s.model_dump() for s in skill_result.action_plan],
                            "draft_reply": skill_result.draft_reply,
                            "risk_flag": skill_result.risk_flag,
                        })
                    else:
                        tool_result_str = execute_tool(tool_name, tool_input, pms)

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": tool_result_str,
                    })

            messages.append({"role": "user", "content": tool_results})

        elif response.stop_reason == "end_turn":
            # Model is done — extract the text reply
            draft_reply = ""
            for block in response.content:
                if hasattr(block, "text"):
                    draft_reply += block.text

            # Build response
            action_plan = skill_result.action_plan if skill_result else []
            risk_flag = skill_result.risk_flag if skill_result else None
            requires_approval = False

            if skill_result:
                if risk_flag:
                    requires_approval = True
                elif settings.approval_mode == "human_approval":
                    # Check if there are pending write actions
                    has_writes = any(
                        step.status == "pending"
                        for step in action_plan
                        if step.tool_call in ("create_reservation", "cancel_reservation", "modify_reservation", "create_guest")
                    )
                    requires_approval = has_writes

            agent_response = AgentResponse(
                draft_reply=draft_reply,
                action_plan=action_plan,
                requires_approval=requires_approval,
                risk_flag=risk_flag,
                conversation_history=messages,
            )

            # Attach execute function if there are pending actions
            if skill_result and hasattr(skill_result, "execute_actions"):
                object.__setattr__(agent_response, "execute_pending", skill_result.execute_actions)

            return agent_response

        else:
            break

    # Max iterations reached
    return AgentResponse(
        draft_reply="I apologize, but I was unable to fully process your request. A team member will follow up shortly.",
        action_plan=[],
        requires_approval=True,
        risk_flag="max_iterations_reached",
        conversation_history=messages,
    )
