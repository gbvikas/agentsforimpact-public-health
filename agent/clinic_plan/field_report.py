"""Field Reporter: the van talks back.

After a Saturday, the nurse practitioner speaks (or types) a debrief. The Field Reporter agent turns it
into place-level facts, a code privacy gate strips anything that could identify a person, and the
result is appended to memory. Next month the Planner reads these reports: ground truth about travel
barriers and unlisted clinics that our federal data cannot see.

field_report_flow = SequentialAgent[field_reporter (LLM), privacy_and_save (code)]
Inputs arrive in session state: field_stop (text), field_geo_id, field_text.
"""
import os
import re

from google.adk.agents import LlmAgent, SequentialAgent

from . import memory
from .steps import parse_json, step

MODEL = os.environ.get("MODEL", "gemini-3.6-flash")

FIELD_INSTRUCTION = """You are the Field Reporter for a county mobile health clinic. A nurse practitioner
is debriefing after a Saturday stop. Your job is to listen and record what the PLACE taught us, so next
month's plan is better. You are curious and practical, not clinical.

Stop: {field_stop}
Debrief (spoken, may be messy): {field_text}

Record only place-level facts:
- turnout: number of people seen, if said
- barriers: what kept people from coming or made it hard (a highway, a bus route, parking, hours, safety)
- unlisted_clinics: free or low-cost care places nearby that the nurse mentioned (name + where)
- demand_signals: what people asked for, as counts or themes (e.g. "4 asked about Medicaid"), never who
- suggested_shift: where the van should go instead or next time, if the nurse suggested it
- follow_up_question: ONE question you would ask the nurse to make next month's plan better
  (for example "Would the parking lot one block north, across the expressway, have worked?")

Privacy is absolute. NEVER record names, ages, health conditions or any detail about an individual
person. If the nurse mentions one, leave it out and count it in dropped_personal_details.

Return ONLY JSON:
{{"turnout": 9, "barriers": ["..."], "unlisted_clinics": [{{"name": "...", "where": "..."}}],
  "demand_signals": ["..."], "suggested_shift": "...", "follow_up_question": "...",
  "dropped_personal_details": 0, "summary": "one sentence, place-level only"}}"""

field_reporter = LlmAgent(
    name="field_reporter",
    model=MODEL,
    description="Turns a nurse's spoken debrief into place-level facts; never records individuals.",
    instruction=FIELD_INSTRUCTION,
    include_contents="none",
    output_key="field_extract",
)

# Belt and braces after the LLM: anything that looks like a person is removed by code.
PERSONAL = [
    (re.compile(r"\b(Mr|Mrs|Ms|Miss|Dr|Señora?|Sra|Sr)\.?\s+[A-Z][a-zA-Z'-]+"), "[person removed]"),
    (re.compile(r"\b\d{1,3}[- ]?(year|yr)s?[- ]?old\b", re.I), "[age removed]"),
    (re.compile(r"\b(\+?1[ -]?)?\(?\d{3}\)?[ -]?\d{3}[ -]?\d{4}\b"), "[phone removed]"),
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b"), "[email removed]"),
]


def scrub(value, counter):
    if isinstance(value, str):
        for pat, repl in PERSONAL:
            value, n = pat.subn(repl, value)
            counter[0] += n
        return value
    if isinstance(value, list):
        return [scrub(v, counter) for v in value]
    if isinstance(value, dict):
        return {k: scrub(v, counter) for k, v in value.items()}
    return value


async def privacy_and_save(state):
    raw = parse_json(state.get("field_extract"))
    counter = [0]
    rec = scrub({k: raw.get(k) for k in ("turnout", "barriers", "unlisted_clinics", "demand_signals",
                                         "suggested_shift", "follow_up_question", "summary")}, counter)
    rec["dropped_personal_details"] = int(raw.get("dropped_personal_details") or 0) + counter[0]
    rec["geo_id"] = state.get("field_geo_id")
    rec["stop"] = state.get("field_stop")
    report_id = f"fr-{(rec['geo_id'] or 'x')[-6:]}-{len(memory.load().get('field_reports', [])) + 1}"
    rec["report_id"] = report_id
    memory.append([{"kind": "field_report", "payload": rec, "run_id": report_id}])
    return ({"field_record": rec},
            f"Field report {report_id} saved: {rec.get('summary') or 'no summary'} "
            f"({rec['dropped_personal_details']} personal detail(s) removed).")


field_report_flow = SequentialAgent(
    name="field_report",
    description="Records a nurse's post-visit debrief as place-level ground truth in memory.",
    sub_agents=[field_reporter, step("privacy_and_save", "Strips personal details and saves to memory.",
                                     privacy_and_save)],
)


def field_notes_and_claims(mem: dict) -> tuple[str, dict]:
    """For the Planner: one line per field report, plus a claim per report for citation."""
    lines, claims = [], {}
    for r in mem.get("field_reports", []):
        cid = r.get("report_id")
        parts = []
        if r.get("turnout") is not None:
            parts.append(f"turnout {r['turnout']}")
        if r.get("barriers"):
            parts.append("barriers: " + "; ".join(r["barriers"]))
        if r.get("unlisted_clinics"):
            parts.append("unlisted free/low-cost care nearby: " + "; ".join(
                f"{c.get('name')} ({c.get('where')})" for c in r["unlisted_clinics"] if isinstance(c, dict)))
        if r.get("demand_signals"):
            parts.append("asked for: " + "; ".join(r["demand_signals"]))
        if r.get("suggested_shift"):
            parts.append("nurse suggests: " + r["suggested_shift"])
        lines.append(f"- {cid} (tract {r.get('geo_id')}, {r.get('date')}): " + ", ".join(parts))
        claims[cid] = dict(claim_id=cid, geo_id=r.get("geo_id"), measure="field_report", value=r,
                           scale="field_observation", source="nurse debrief via Field Reporter",
                           as_of=r.get("date"), interval=None, null_state="ok",
                           caveats=["FIELD_OBSERVATION"], audit="not_reviewed")
    return ("\n".join(lines) or "- none yet"), claims
