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

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "agent"))

from google.adk.runners import InMemoryRunner  # noqa: E402
from google.genai import types  # noqa: E402

from clinic_plan import memory  # noqa: E402
from clinic_plan.agent import root_agent  # noqa: E402
from clinic_plan.field_report import field_report_flow  # noqa: E402
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


class FieldReq(BaseModel):
    geo_id: str
    stop: str = ""
    text: str


@app.get("/field")
def field_page():
    """Nurse-facing page: speak or type the post-visit debrief."""
    return FileResponse(os.path.join(os.path.dirname(__file__), "field.html"))


@app.post("/api/field-report")
async def field_report(req: FieldReq):
    if len(req.text.strip()) < 10:
        raise HTTPException(400, "Debrief is too short")
    runner = InMemoryRunner(agent=field_report_flow, app_name="field_report")
    session = await runner.session_service.create_session(
        app_name="field_report", user_id="nurse",
        state={"field_geo_id": req.geo_id, "field_stop": req.stop or req.geo_id, "field_text": req.text})
    msg = types.Content(role="user", parts=[types.Part(text="Record this debrief.")])
    trace = []
    async for ev in runner.run_async(user_id="nurse", session_id=session.id, new_message=msg):
        trace.append(_event_record(ev))
    s = await runner.session_service.get_session(app_name="field_report", user_id="nurse", session_id=session.id)
    return {"record": s.state.get("field_record"), "trace": trace}


def _speech_level(wav: bytes) -> float:
    """Fraction of 16-bit samples louder than ~3% of full scale (a crude voice-activity check)."""
    import array
    i = wav.find(b"data")
    pcm = array.array("h", wav[i + 8 if i >= 0 else 44:][: (len(wav) // 2) * 2 - 2])
    return sum(1 for x in pcm[::4] if abs(x) > 1000) / max(len(pcm) // 4, 1)


@app.post("/api/transcribe")
async def transcribe(request: Request):
    """Voice for the Field Reporter in any browser: the page records 16 kHz mono WAV, Gemini transcribes."""
    audio = await request.body()
    if not audio or len(audio) > 15_000_000:
        raise HTTPException(400, "Send 1 byte to 15 MB of audio/wav")
    from google import genai
    client = genai.Client()
    # 16 kHz mono 16-bit WAV is 32 KB per second; under ~0.75 s there is nothing to transcribe.
    if len(audio) < 24_000:
        return {"text": "", "note": "Recording too short. Hold Speak and talk for a few seconds."}
    # Deterministic loudness gate: an LLM will happily "transcribe" silence, so check for sound first.
    if _speech_level(audio) < 0.01:
        return {"text": "", "note": "No speech heard. Check the microphone and try again."}
    resp = await client.aio.models.generate_content(
        model=os.environ.get("MODEL", "gemini-3.6-flash"),
        contents=[types.Part.from_bytes(data=audio, mime_type=request.headers.get("content-type", "audio/wav")),
                  "Transcribe the speech in this audio verbatim, in the language spoken (English or Spanish). "
                  "Write only words you actually hear. Never invent, complete or summarize content. If there is "
                  "no clear speech, reply with exactly NO_SPEECH. Return only the transcript."],
        config=types.GenerateContentConfig(temperature=0))
    text = (resp.text or "").strip()
    if text == "NO_SPEECH":
        return {"text": "", "note": "No clear speech heard. Try again closer to the microphone."}
    return {"text": text}


class AckReq(BaseModel):
    reason: str


@app.post("/api/acknowledge")
def acknowledge(req: AckReq):
    return memory.acknowledge_flags(req.reason)


@app.post("/api/reset-memory")
def reset_memory():
    return memory.reset()
