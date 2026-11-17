"""Run clinic_plan once from the command line: .venv/bin/python agent/run_once.py"""
import asyncio
import sys

sys.path.insert(0, __import__("os").path.dirname(__file__))
from google.adk.runners import InMemoryRunner  # noqa: E402
from google.genai import types  # noqa: E402

from clinic_plan.agent import root_agent  # noqa: E402


async def main():
    runner = InMemoryRunner(agent=root_agent, app_name="clinic_plan")
    session = await runner.session_service.create_session(app_name="clinic_plan", user_id="lead")
    msg = types.Content(role="user", parts=[types.Part(text="Plan next month's four Saturday stops for Cook County.")])
    async for ev in runner.run_async(user_id="lead", session_id=session.id, new_message=msg):
        for p in (ev.content.parts if ev.content else []) or []:
            if p.text:
                print(f"\n[{ev.author}] {p.text[:1500]}")
            elif p.function_call:
                print(f"\n[{ev.author}] -> tool {p.function_call.name}({dict(p.function_call.args or {})})"[:300])


asyncio.run(main())
