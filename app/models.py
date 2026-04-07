from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class Hotel(BaseModel):
    name: str
    address: str
    phone: str
    email: str
    check_in_time: str
    check_out_time: str
    currency: str
    timezone: str


class CancellationPolicies(BaseModel):
    standard: str
    non_refundable: str
    flexible: str


class Policies(BaseModel):
    cancellation: CancellationPolicies
    pets: str
    breakfast: str
    parking: str
    extra_bed: str
    children: str


class RoomType(BaseModel):
    id: str
    name: str
    description: str
    max_occupancy: int
    bed_type: str
    base_rate_per_night: int
    amenities: list[str]
    extra_bed_available: bool = False


class RatePlan(BaseModel):
    id: str
    name: str
    cancellation_policy: str
    includes_breakfast: bool
    rate_modifier: float
    breakfast_supplement_per_person: int = 0


class Guest(BaseModel):
    id: str
    first_name: str
    last_name: str
    email: str
    phone: str
    nationality: str
    created_at: str


class Reservation(BaseModel):
    id: str
    guest_id: str
    room_type_id: str
    rate_plan_id: str
    check_in: str
    check_out: str
    adults: int
    children: int
    status: Literal["confirmed", "cancelled", "modified"]
    total_amount: float
    notes: str
    created_at: str


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


class AgentResponse(BaseModel):
    draft_reply: str
    action_plan: list[ActionStep]
    requires_approval: bool = False
    risk_flag: str | None = None
    conversation_history: list = []
