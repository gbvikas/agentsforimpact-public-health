"""EquiVita dashboard: run the agent live and show its reasoning, audit and memory.

Run (from repo root, with Toolbox running):
    .venv/bin/python -m uvicorn dashboard.app:app --port 8090
"""
import asyncio
import glob
import json
import os
import sys
import time

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "agent"))

from google.adk.runners import InMemoryRunner  # noqa: E402
from google.genai import types  # noqa: E402

from clinic_plan import memory  # noqa: E402
from clinic_plan.agent import root_agent  # noqa: E402
from clinic_plan.steps import RUNS_DIR  # noqa: E402

app = FastAPI(title="EquiVita")
LIVE = {"running": False, "events": [], "run_id": None, "error": None}


def _event_record(ev) -> dict:
    parts = (ev.content.parts if ev.content else None) or []
    text = "".join(p.text or "" for p in parts if getattr(p, "text", None))
    calls = [p.function_call.name for p in parts if getattr(p, "function_call", None)]
    results = [p.function_response.name for p in parts if getattr(p, "function_response", None)]
    delta = list((ev.actions.state_delta or {}).keys()) if ev.actions else []
    return {"t": time.strftime("%H:%M:%S"), "author": ev.author, "text": text[:4000],
            "tool_calls": calls, "tool_results": results, "state_keys": delta,
            "escalate": bool(ev.actions and ev.actions.escalate)}


async def _run(prompt: str):
    LIVE.update(running=True, events=[], run_id=None, error=None)
    try:
        runner = InMemoryRunner(agent=root_agent, app_name="clinic_plan")
        session = await runner.session_service.create_session(app_name="clinic_plan", user_id="lead")
        msg = types.Content(role="user", parts=[types.Part(text=prompt)])
        async for ev in runner.run_async(user_id="lead", session_id=session.id, new_message=msg):
            LIVE["events"].append(_event_record(ev))
        s = await runner.session_service.get_session(app_name="clinic_plan", user_id="lead",
                                                     session_id=session.id)
        LIVE["run_id"] = s.state.get("run_id")
    except Exception as e:  # surface to the UI
        LIVE["error"] = f"{type(e).__name__}: {e}"
    finally:
        LIVE["running"] = False


class RunReq(BaseModel):
    prompt: str = "Plan next month's four Saturday stops for Cook County."


class ApproveReq(BaseModel):
    version: str
    reason: str


@app.get("/")
def lead_view():
    """Default: the outreach lead's view."""
    return FileResponse(os.path.join(os.path.dirname(__file__), "lead.html"))


@app.get("/console")
def console():
    """How we decided: the full engineering console."""
    return FileResponse(os.path.join(os.path.dirname(__file__), "index.html"))


@app.post("/api/run")
async def start_run(req: RunReq):
    if LIVE["running"]:
        raise HTTPException(409, "A run is already in progress")
    asyncio.create_task(_run(req.prompt))
    return {"started": True}


@app.get("/api/live")
def live():
    return LIVE


@app.get("/api/runs")
def runs():
    files = sorted(glob.glob(os.path.join(RUNS_DIR, "*.json")), reverse=True)
    return [os.path.basename(f)[:-5] for f in files]


@app.get("/api/runs/{run_id}")
def run(run_id: str):
    path = os.path.join(RUNS_DIR, f"{os.path.basename(run_id)}.json")
    if not os.path.exists(path):
        raise HTTPException(404)
    with open(path) as f:
        return json.load(f)


@app.get("/api/memory")
def get_memory():
    return memory.load()


@app.post("/api/approve")
def approve(req: ApproveReq):
    return memory.approve_config(req.version, req.reason)


class AckReq(BaseModel):
    reason: str


@app.post("/api/acknowledge")
def acknowledge(req: AckReq):
    return memory.acknowledge_flags(req.reason)


@app.post("/api/reset-memory")
def reset_memory():
    return memory.reset()
