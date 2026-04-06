from __future__ import annotations

from pydantic import BaseModel
from fastapi import FastAPI

from app.agent.react_agent import process_email
from app.config import settings
from app.models import ActionStep
from app.services.pms import PMS

app = FastAPI(title="Hotel AI Email Agent", version="0.1.0")

# Single PMS instance for the app lifetime
_pms = PMS(settings.data_path)


class EmailRequest(BaseModel):
    email_body: str
    sender_email: str


class EmailResponse(BaseModel):
    draft_reply: str
    action_plan: list[ActionStep]
    requires_approval: bool
    risk_flag: str | None = None


class ApprovalRequest(BaseModel):
    approved: bool


@app.post("/process-email", response_model=EmailResponse)
def handle_email(request: EmailRequest):
    result = process_email(
        email_body=request.email_body,
        sender_email=request.sender_email,
        pms=_pms,
        settings=settings,
    )
    return EmailResponse(
        draft_reply=result.draft_reply,
        action_plan=result.action_plan,
        requires_approval=result.requires_approval,
        risk_flag=result.risk_flag,
    )


@app.get("/health")
def health():
    return {"status": "ok"}
