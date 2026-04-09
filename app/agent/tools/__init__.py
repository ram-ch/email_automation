from __future__ import annotations

import json

from app.agent.tools.escalation import ESCALATION_TOOL_HANDLERS, ESCALATION_TOOL_SCHEMAS
from app.agent.tools.read_tools import READ_TOOL_HANDLERS, READ_TOOL_SCHEMAS
from app.agent.tools.write_tools import WRITE_TOOL_HANDLERS, WRITE_TOOL_NAMES, WRITE_TOOL_SCHEMAS
from app.services.pms import PMS

__all__ = ["get_tool_schemas", "execute_tool", "WRITE_TOOL_NAMES"]


def get_tool_schemas() -> list[dict]:
    return list(READ_TOOL_SCHEMAS) + list(WRITE_TOOL_SCHEMAS) + list(ESCALATION_TOOL_SCHEMAS)


def execute_tool(name: str, params: dict, pms: PMS) -> str:
    handlers = {**READ_TOOL_HANDLERS, **WRITE_TOOL_HANDLERS, **ESCALATION_TOOL_HANDLERS}
    handler = handlers.get(name)
    if not handler:
        return json.dumps({"error": f"Unknown tool: {name}"})
    return handler(params, pms)
