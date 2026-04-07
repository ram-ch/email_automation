from __future__ import annotations

import json

from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from app.agent.react_agent import process_email, _execute_action_plan
from app.config import Settings, load_settings
from app.models import AgentResponse, SkillResult
from app.services.pms import PMS
from app.templates import render_email_html, render_preview_html


REJECTION_TEXT = (
    "Thank you for contacting Grand Oslo Hotel. "
    "Your request is being reviewed by our reservations team, "
    "and we will follow up with you shortly."
)


class EmailRequest(BaseModel):
    sender_email: str
    body: str


class EmailResponse(BaseModel):
    email_html: str
    action_plan: list[dict]
    mode: str
    requires_approval: bool
    risk_flag: str | None
    status: str


def _get_hotel_info(pms: PMS) -> dict:
    """Get hotel info for the email template."""
    hotel = pms.get_hotel_info()
    return {
        "hotel_name": hotel.name,
        "hotel_address": hotel.address,
        "hotel_phone": hotel.phone,
        "hotel_email": hotel.email,
    }


def _terminal_log(entry: dict) -> None:
    """Print agent activity to the server terminal in real time."""
    t = entry.get("type", "")
    if t == "incoming":
        print(f"\n{'━' * 56}")
        print(f"  Incoming Email")
        print(f"  From: {entry['sender']}")
        body_preview = entry['body'][:100] + ('...' if len(entry['body']) > 100 else '')
        print(f"  Body: \"{body_preview}\"")
        print(f"{'━' * 56}")
    elif t in ("tool", "skill"):
        label = "skill" if t == "skill" else "tool"
        summary = entry.get("result_summary", "")
        try:
            parsed = json.loads(summary)
            if "found" in parsed:
                short = f"found={parsed['found']}"
            elif "availability" in parsed:
                short = "availability loaded"
            elif "rate_plans" in parsed:
                short = f"{len(parsed['rate_plans'])} plans"
            elif "skill_name" in parsed:
                short = "action plan ready"
            elif "reservation" in parsed:
                short = "reservation found"
            elif "reservations" in parsed:
                short = f"{len(parsed['reservations'])} reservations"
            elif "error" in parsed:
                short = parsed["error"]
            else:
                short = summary[:60]
        except Exception:
            short = summary[:60]
        print(f"  [iteration {entry.get('iteration', '?')}] {label}: {entry['name']} -> {short}")
    elif t == "result":
        if entry.get("risk_flag"):
            print(f"\n  ⚠️  Escalated: {entry['risk_flag']}")
        elif not entry.get("has_actions"):
            print(f"\n  ℹ️  Read-only request — no actions needed.")


def _prompt_approval(result: AgentResponse, pms: PMS, hotel_info: dict, mode: str) -> EmailResponse:
    """Block and prompt the operator for approval in the terminal."""
    print(f"\n  --- Action Plan ---")
    for i, step in enumerate(result.action_plan, 1):
        print(f"    {i}. {step.description}")
    print(f"\n  --- Mode: {mode} ---")

    while True:
        decision = input("  ⏳ Type 'approve' or 'reject': ").strip().lower()
        if decision in ("approve", "reject"):
            break
        print("    Please type 'approve' or 'reject'.")

    action_plan_out = [
        {"step": i + 1, "description": s.description}
        for i, s in enumerate(result.action_plan)
    ]

    if decision == "approve":
        skill_result = SkillResult(
            skill_name="approved",
            action_plan=result.action_plan,
            draft_reply=result.draft_reply,
        )
        _execute_action_plan(skill_result, pms)
        print("  ✅ Actions executed.")
        return EmailResponse(
            email_html=render_email_html(body_text=result.draft_reply, **hotel_info),
            action_plan=action_plan_out,
            mode=mode,
            requires_approval=True,
            risk_flag=result.risk_flag,
            status="approved",
        )
    else:
        print("  ❌ Actions rejected. No changes to PMS.")
        return EmailResponse(
            email_html=render_email_html(body_text=REJECTION_TEXT, **hotel_info),
            action_plan=action_plan_out,
            mode=mode,
            requires_approval=True,
            risk_flag=result.risk_flag,
            status="rejected",
        )


def create_app(settings: Settings | None = None, pms: PMS | None = None) -> FastAPI:
    """Create the FastAPI app. Accepts injected settings/pms for testing."""
    if settings is None:
        settings = load_settings()
    if pms is None:
        pms = PMS(settings.data_path)

    app = FastAPI(title="Grand Oslo Hotel — AI Email Agent")

    # Store on app.state so the endpoint can access them
    app.state.pms = pms
    app.state.settings = settings

    @app.post("/process-email", response_model=None)
    def handle_email(
        request: EmailRequest,
        response_format: str = Query(default="json", pattern="^(json|html)$"),
    ):
        _pms = app.state.pms
        _settings = app.state.settings
        hotel_info = _get_hotel_info(_pms)

        result = process_email(
            email_body=request.body,
            sender_email=request.sender_email,
            pms=_pms,
            settings=_settings,
            log_callback=_terminal_log,
        )

        action_plan_out = [
            {"step": i + 1, "description": s.description}
            for i, s in enumerate(result.action_plan)
        ]

        # Case 1: Escalated (risk flag, either mode)
        if result.risk_flag:
            print(f"  No PMS writes.")
            email_response = EmailResponse(
                email_html=render_email_html(body_text=result.draft_reply, **hotel_info),
                action_plan=action_plan_out,
                mode=_settings.approval_mode,
                requires_approval=False,
                risk_flag=result.risk_flag,
                status="escalated",
            )

        # Case 2: No actions (read-only)
        elif not result.action_plan:
            print(f"\n  No actions required.")
            email_response = EmailResponse(
                email_html=render_email_html(body_text=result.draft_reply, **hotel_info),
                action_plan=[],
                mode=_settings.approval_mode,
                requires_approval=False,
                risk_flag=None,
                status="completed",
            )

        # Case 3: Autonomous mode, no risk — already executed by the agent loop
        elif _settings.approval_mode == "autonomous":
            print(f"\n  --- Action Plan (auto-executed) ---")
            for i, step in enumerate(result.action_plan, 1):
                print(f"    {i}. {step.description}")
            print(f"  ✅ Actions auto-executed (autonomous mode).")
            email_response = EmailResponse(
                email_html=render_email_html(body_text=result.draft_reply, **hotel_info),
                action_plan=action_plan_out,
                mode="autonomous",
                requires_approval=False,
                risk_flag=None,
                status="completed",
            )

        # Case 4: Human approval mode with actions — block for approval
        else:
            email_response = _prompt_approval(result, _pms, hotel_info, _settings.approval_mode)

        # Return HTML preview or JSON based on response_format
        if response_format == "html":
            return HTMLResponse(content=render_preview_html(
                email_html=email_response.email_html,
                action_plan=email_response.action_plan,
                mode=email_response.mode,
                status=email_response.status,
                risk_flag=email_response.risk_flag,
            ))

        return email_response

    return app


# Entry point: uvicorn app.main:app
def _create_default_app() -> FastAPI:
    settings = load_settings()
    pms = PMS(settings.data_path)
    print(f"\n{'=' * 56}")
    print(f"  Grand Oslo Hotel — AI Email Agent")
    print(f"{'=' * 56}")
    print(f"  Mode: {settings.approval_mode}")
    print(f"  Model: {settings.model}")
    print(f"  Simulated date: {settings.simulated_today or 'real date'}")
    print(f"{'=' * 56}\n")
    return create_app(settings=settings, pms=pms)


app = _create_default_app()
