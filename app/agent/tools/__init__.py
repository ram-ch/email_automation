from __future__ import annotations

import json

from app.agent.tools.read_tools import READ_TOOL_HANDLERS, READ_TOOL_SCHEMAS
from app.services.pms import PMS

WRITE_TOOL_NAMES: set[str] = set()


def get_tool_schemas() -> list[dict]:
    return list(READ_TOOL_SCHEMAS)


def execute_tool(name: str, params: dict, pms: PMS) -> str:
    handlers = {**READ_TOOL_HANDLERS}
    handler = handlers.get(name)
    if not handler:
        return json.dumps({"error": f"Unknown tool: {name}"})
    return handler(params, pms)
