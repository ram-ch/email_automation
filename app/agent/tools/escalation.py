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
