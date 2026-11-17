"""Call MCP Toolbox tools from deterministic (non-LLM) workflow steps.

Locally Toolbox runs on http://127.0.0.1 with no auth. On Cloud Run it is a private service, so
every request carries a Google identity token minted for the Toolbox URL by the metadata server.
"""
import json
import os

from toolbox_core import ToolboxClient

TOOLBOX_URL = os.environ.get("TOOLBOX_URL", "http://127.0.0.1:5055")


def _id_token() -> str:
    from google.auth.transport.requests import Request
    from google.oauth2 import id_token
    return "Bearer " + id_token.fetch_id_token(Request(), TOOLBOX_URL)


def auth_headers() -> dict:
    """Headers for Toolbox: an identity token when Toolbox is a private https service."""
    return {"Authorization": _id_token} if TOOLBOX_URL.startswith("https://") else {}


async def call_tool(name: str, **params) -> list[dict]:
    """Run one Toolbox tool and return its rows. A no-rows reply comes back as []."""
    async with ToolboxClient(TOOLBOX_URL, client_headers=auth_headers()) as client:
        tool = await client.load_tool(name)
        out = await tool(**params)
    if isinstance(out, str):
        out = out.strip()
        if not out.startswith(("[", "{")):
            return []
        out = json.loads(out)
    return out if isinstance(out, list) else [out]
