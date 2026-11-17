"""Call MCP Toolbox tools from deterministic (non-LLM) workflow steps."""
import json
import os

from toolbox_core import ToolboxClient

TOOLBOX_URL = os.environ.get("TOOLBOX_URL", "http://127.0.0.1:5055")


async def call_tool(name: str, **params) -> list[dict]:
    """Run one Toolbox tool and return its rows. A no-rows reply comes back as []."""
    async with ToolboxClient(TOOLBOX_URL) as client:
        tool = await client.load_tool(name)
        out = await tool(**params)
    if isinstance(out, str):
        out = out.strip()
        if not out.startswith(("[", "{")):
            return []
        out = json.loads(out)
    return out if isinstance(out, list) else [out]
