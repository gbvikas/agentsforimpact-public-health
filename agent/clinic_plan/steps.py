"""Deterministic (code) steps of the clinic_plan workflow, plus the Auditor's check_plan tool.

Each step reads session.state and returns (state_delta, message). Nothing here calls an LLM.
"""
import json
import os
import re
from datetime import datetime
from typing import Any, AsyncGenerator, Awaitable, Callable

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.adk.tools import ToolContext
from google.genai import types

from . import memory
from .scoring import SCORE_CONFIGS, km_between, score_need
from .toolbox_bridge import call_tool

COUNTY_FIPS = os.environ.get("COUNTY_FIPS", "17031")
MIN_KM_BETWEEN_STOPS = 5.0
DISPARITY_THRESHOLD_PTS = 25.0   # [COUNTY THRESHOLD] placeholder, set by the county
MAX_ROUNDS = 2
RUNS_DIR = os.path.join(os.path.dirname(__file__), "..", "runs")

LIMIT_TEXT = {
    "STRAIGHT_LINE_KM": ("How long the trip really takes.", "Distances are straight-line, not travel time."),
    "FEDERAL_SITES_ONLY": ("Whether a closer free or county clinic exists.",
                           "Only federally recognized sites are in the data, so every distance is an upper bound."),
    "MODELED_PREVALENCE": ("How many people in a tract are actually uninsured or sick.",
                           "CDC PLACES figures are modeled estimates, not counts."),
    "SURVEY_ESTIMATE": ("Exact car and language figures.", "These are Census survey estimates with sampling error."),
    "NO_INTERVAL": ("Whether one tract needs a stop more than a close runner-up.",
                    "Confidence intervals are not loaded; tracts in the same tie band cannot honestly be ordered."),
    "WITHIN_COUNTY_RANK": ("How these tracts compare with other counties.", "Ranks are within this county only."),
    "HPSA_MAX_OF_DESIGNATIONS": ("A single federal shortage score per tract.",
                                 "Some tracts carry several designations; we report the highest."),
    "AIR_COUNTY_SCALE": ("Which neighborhoods have worse air.",
                         "PM2.5 is modeled on a 12 km grid; it describes the county and bad days only."),
    "TREND_REGION_SCALE": ("Whether respiratory illness is rising in a neighborhood.",
                           "The weekly trend covers a multi-county Health Service Area."),
    "STOPS_TOO_CLOSE": ("—", "Two stops were within 5 km of each other in a draft plan."),
    "NOT_A_CANDIDATE": ("—", "A draft plan chose a tract that score_need did not rank."),
    "UNKNOWN_CLAIM": ("—", "A draft plan cited a claim that is not in the ledger."),
    "SCALE_MISUSE": ("—", "A draft reason used a county or regional figure to justify a neighborhood."),
    "OVERCLAIM_TIE": ("—", "A draft reason ranked a tract (e.g. '#1', 'highest') although its score is "
                           "tied with tracts not chosen. Describe tied tracts as comparable."),
    "DEMOGRAPHIC_DISPARITY": ("Whether the plan reaches the same people as the county's highest-need tracts.",
                              "The audit found a gap above the county threshold; a human must decide."),
    "LANGUAGE_UNSPECIFIED": ("Which languages residents need.",
                             "The data counts limited-English households but not their language; we default to Spanish."),
    "NOT_AUDITED": ("Whether this plan passed audit.", "The audit did not finish."),
    "FIELD_OBSERVATION": ("How typical one Saturday was.",
                          "Field reports are one nurse's observations from one day, not a measurement."),
}


class Step(BaseAgent):
    """Wraps an async function (state) -> (state_delta, message[, escalate]) as an ADK agent."""
    fn: Any = None

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        result = await self.fn(dict(ctx.session.state))
        delta, msg = result[0], result[1]
        escalate = len(result) > 2 and result[2]
        yield Event(invocation_id=ctx.invocation_id, author=self.name,
                    content=types.Content(role="model", parts=[types.Part(text=msg)]),
                    actions=EventActions(state_delta=delta, escalate=escalate or None))


def step(name: str, description: str, fn: Callable[[dict], Awaitable[tuple]]) -> Step:
    return Step(name=name, description=description, fn=fn)


def parse_json(text: Any) -> dict:
    if isinstance(text, dict):
        return text
    m = re.search(r"\{.*\}", str(text or ""), re.S)
    try:
        return json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        return {}


# ------------------------------------------------------------------ steps
async def recall_memory(state):
    mem = memory.load()
    lessons = "\n".join(f"- ({l['source']}, {l['date']}) {l['text']}" for l in mem["lessons"]) or "- none yet"
    visited = sorted({v["geo_id"] for v in mem["visits"]})
    from .field_report import field_notes_and_claims  # local import: field_report imports this module
    field_notes, field_claims = field_notes_and_claims(mem)
    return ({"score_config_version": mem["approved_config"], "past_lessons": lessons,
             "recent_visits": ", ".join(visited) or "none", "memory_snapshot": mem,
             "field_notes": field_notes, "field_claims": field_claims,
             "round": 0, "rounds": [], "revise_request": "none (first draft)"},
            f"Memory: score config {mem['approved_config']}, {len(mem['lessons'])} lessons, "
            f"{len(visited)} previously visited tracts, {len(field_claims)} field report(s).")


async def lookup_tracts(state):
    rows = await call_tool("tract_features", min_pop=500)
    return ({"ev_tracts": rows},
            f"burden + access lookup: {len(rows)} tracts (scale: tract) via MCP Toolbox `tract_features`.")


async def lookup_context(state):
    air = await call_tool("county_air_context")
    resp = await call_tool("regional_respiratory_trend", weeks=4)
    claims = {}
    if air:
        claims["c-ctx-air"] = dict(claim_id="c-ctx-air", geo_id=None, measure="county_air", value=air[0],
                                   scale="county", source="exposure_tracts (12 km grid)", as_of="EPA/CDC daily PM2.5",
                                   interval=None, null_state="ok", caveats=["AIR_COUNTY_SCALE"], audit="not_reviewed")
    if resp:
        all_null = all(r.get("percent_visits_covid") is None for r in resp)
        claims["c-ctx-resp"] = dict(claim_id="c-ctx-resp", geo_id=None, measure="respiratory_trend",
                                    value=resp[0], scale="health_service_area", source="disease_weekly",
                                    as_of=str(resp[0].get("week_end")), interval=None,
                                    null_state="all-null" if all_null else "ok",
                                    caveats=["TREND_REGION_SCALE"], audit="not_reviewed")
    return ({"ev_context": {"air": air, "respiratory": resp}, "context_claims": claims},
            f"context lookup: county air (scale: county) and {len(resp)} weeks of respiratory trend "
            f"(scale: health service area).")


async def run_score_need(state):
    version = state["score_config_version"]
    out = score_need(state["ev_tracts"], version)
    claims = {**out["claims"], **state.get("context_claims", {}), **state.get("field_claims", {})}
    lines = ["rank | tract (place) | score | rank band | uninsured% | no-vehicle% | km to safety net "
             "| shortage score | claim ids"]
    for c in out["candidates"]:
        ids = c["claim_ids"]
        lines.append(f"{c['rank']} | {c['geo_id']} ({c.get('label')}) | {c['score']} | {c['rank_band'][0]}-{c['rank_band'][1]} | "
                     f"{c['pct_uninsured']} | {c['pct_no_vehicle']} | "
                     f"{c['km_to_safety_net']} | {c['hpsa_score']} | "
                     f"{ids['pct_uninsured']}, {ids['pct_no_vehicle']}, "
                     f"{ids['km_to_safety_net']}, {ids['hpsa_score']}, {ids['score']}")
    lines.append("context claims (NOT tract-level): c-ctx-air (scale: county), c-ctx-resp (scale: health service area)")
    return ({"candidates": out["candidates"], "claims": claims, "score_meta": out["meta"],
             "all_scores": out["all_scores"], "candidates_table": "\n".join(lines)},
            f"score_need {version}: scored {out['meta']['n_scored']} tracts, top {len(out['candidates'])} "
            f"candidates passed to the Planner. Formula: {out['meta']['formula']}.")


async def audit_gate(state):
    """Code, not LLM: merges deterministic checks with the Auditor's verdict, strips anything
    demographic from what goes back to the Planner, and decides whether the loop continues."""
    rnd = state.get("round", 0) + 1
    verdict = parse_json(state.get("audit_verdict"))
    checks = state.get("audit_checks", {})
    flags = list(checks.get("flags", []))
    for f in verdict.get("flags", []):
        if f.get("code") and f["code"] not in {x["code"] for x in flags}:
            flags.append({"code": f["code"], "claim_ids": f.get("claim_ids", []),
                          "route": "human" if f["code"] == "DEMOGRAPHIC_DISPARITY" else f.get("route", "revise"),
                          "detail": f.get("message", "")})
    revise = [f for f in flags if f["route"] == "revise"]
    human = [f for f in flags if f["route"] == "human"]
    passed = not revise
    claims = dict(state["claims"])
    for f in flags:
        for cid in f.get("claim_ids", []):
            if cid in claims:
                claims[cid] = {**claims[cid], "audit": "flagged",
                               "flags": sorted(set(claims[cid].get("flags", []) + [f["code"]]))}
    # The Planner sees only codes, tract IDs, claim IDs and the rule. Never demographic detail.
    # Details are only forwarded for flags computed by code from non-demographic fields.
    safe_detail = {"STOPS_TOO_CLOSE", "NOT_A_CANDIDATE", "OVERCLAIM_TIE", "UNKNOWN_CLAIM"}
    revise_request = "\n".join(
        f"- {f['code']}: {LIMIT_TEXT.get(f['code'], ('', ''))[1]} "
        + (f"({f['detail']}) " if f["code"] in safe_detail and f.get("detail") else "")
        + f"Claims/tracts: {', '.join(f.get('claim_ids', [])) or 'n/a'}"
        for f in revise) or "none"
    rounds = list(state.get("rounds", [])) + [{
        "round": rnd, "draft_plan": parse_json(state.get("draft_plan")),
        "verdict": "pass" if passed else "revise", "flags": flags,
        "auditor_summary": verdict.get("summary", ""), "demographics": checks.get("demographics")}]
    done = passed or rnd >= MAX_ROUNDS
    # One verdict for the UI. "passed" only means no revise flags are left; a human flag is still open.
    status = "revise" if revise else ("needs_human" if human else "cleared")
    rounds[-1]["status"] = status
    msg = (f"Audit gate, round {rnd}: {'PASS' if passed else 'REVISE'} "
           f"({len(revise)} revise flag(s), {len(human)} for the human). "
           + ("Loop ends." if done else "Sending revise request back to the Planner (no demographic detail)."))
    return ({"round": rnd, "rounds": rounds, "claims": claims, "revise_request": revise_request,
             "human_flags": human, "audit_passed": passed, "audit_status": status}, msg, done)


async def finalize_plan(state):
    rounds = state["rounds"]
    final = rounds[-1]["draft_plan"] if rounds else parse_json(state.get("draft_plan"))
    audited = bool(rounds)
    claims = dict(state["claims"])
    cands = {c["geo_id"]: c for c in state["candidates"]}
    scores = state["all_scores"]
    stop_ids = [s.get("geo_id") for s in final.get("stops", [])]
    brief, details = [], []
    for s in final.get("stops", []):
        g = s.get("geo_id")
        cited = [cid for cid in s.get("claim_ids", []) if cid in claims and claims[cid]["scale"] == "tract"]
        for cid in cited:
            if claims[cid]["audit"] != "flagged" and audited:
                claims[cid] = {**claims[cid], "audit": "cleared"}
        cleared = [claims[cid] for cid in cited if claims[cid]["audit"] == "cleared"]
        if not cleared:
            brief.append(f"Saturday {s.get('saturday')}: tract {g}: NO CLEARED CLAIMS, write no flyer text.")
            continue
        sites = await call_tool("nearest_safety_net_sites", geo_id=g, n=1)
        me = cands.get(g) or next((r for r in scores if r["geo_id"] == g), None)
        nxt = None
        if me:
            others = [r for r in scores if r["geo_id"] not in stop_ids]
            nxt = min(others, key=lambda r: km_between(me, r)) if others else None
        site = sites[0] if sites else {}
        facts = "; ".join(f"{c['measure']} = {c['value']}" for c in cleared)
        nd = (f"Nearest tract not chosen: {nxt.get('label', nxt['geo_id'])} ({km_between(me, nxt):.1f} km away): "
              f"uninsured {nxt['pct_uninsured']}%, no vehicle {nxt['pct_no_vehicle']}%, "
              f"km to a free/sliding-scale clinic {nxt['km_to_safety_net']}, need-score rank {nxt['rank']}."
              if nxt else "")
        brief.append(f"Saturday {s.get('saturday')}: {(me or {}).get('label', 'tract ' + str(g))}. Cleared facts: {facts}. "
                     f"Nearest free/sliding-scale clinic: {site.get('name', 'unknown')} at "
                     f"{site.get('address', '?')}, {site.get('km_straight_line', '?')} km straight-line, "
                     f"{site.get('hours_per_week') or 'unpublished'} hours/week. {nd}")
        details.append({"saturday": s.get("saturday"), "geo_id": g, "clinic": site,
                        "next_door": ({**nxt, "km_away": round(km_between(me, nxt), 1)} if nxt else None)})
    return ({"final_plan": final, "claims": claims, "cleared_brief": "\n".join(brief),
             "stop_details": details},
            f"Final plan: {len(stop_ids)} stops. Cleared claims, nearest clinic and 'next door' "
            f"comparison prepared for the Explainer.")


async def limits_and_persist(state):
    claims = state["claims"]
    final = state.get("final_plan", {})
    cited = {cid for s in final.get("stops", []) for cid in s.get("claim_ids", [])} | {"c-ctx-air", "c-ctx-resp"}
    codes: dict[str, set] = {}
    for cid in cited:
        c = claims.get(cid)
        if not c:
            continue
        for code in c.get("caveats", []) + c.get("flags", []):
            codes.setdefault(code, set()).add(cid)
        if c["null_state"] != "ok":
            codes.setdefault("NULL_" + c["null_state"].upper(), set()).add(cid)
    for r in state.get("rounds", []):
        for f in r["flags"]:
            codes.setdefault(f["code"], set()).update(f.get("claim_ids", []))
    for p in state.get("channel_plan", []):          # outreach claims are cited by the channel plan, not the stops
        for c in p["channels"]:
            cl = claims.get(c.get("claim_id") or "")
            for code in (cl or {}).get("caveats", []):
                codes.setdefault(code, set()).add(cl["claim_id"])
        lang = claims.get(f"c-{p['geo_id'][-6:]}-limited_english")
        if lang:
            codes.setdefault("LANGUAGE_UNSPECIFIED", set()).add(lang["claim_id"])
    if not state.get("rounds"):
        codes.setdefault("NOT_AUDITED", set())
    limits = [{"code": k, "what": LIMIT_TEXT.get(k, (k, ""))[0], "why": LIMIT_TEXT.get(k, ("", k))[1],
               "claim_ids": sorted(v)} for k, v in sorted(codes.items())]
    if not limits:
        raise RuntimeError("Empty limits list is an error, not 'nothing to report'.")

    # memory: remember visits and learn from this run's revise flags (codes and rules only)
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    month = datetime.now().strftime("%Y-%m")
    known = {l["text"] for l in memory.load()["lessons"]}
    events = [{"kind": "visit", "payload": {"month": month, "geo_id": s.get("geo_id"), "saturday": s.get("saturday")}}
              for s in final.get("stops", [])]
    for r in state.get("rounds", []):
        for f in r["flags"]:
            text = f"Avoid {f['code']}: {LIMIT_TEXT.get(f['code'], ('', f['code']))[1]}"
            if f["route"] == "revise" and text not in known:
                events.append(memory.lesson(text, "auditor"))
                known.add(text)
    events.append({"kind": "pending_flags", "payload": {"flags": [
        {"code": f["code"], "detail": f.get("detail", "")} for f in state.get("human_flags", [])]}})
    memory.append([{**e, "run_id": run_id} for e in events])
    mem = memory.load()

    os.makedirs(RUNS_DIR, exist_ok=True)
    keys = ["score_config_version", "score_meta", "candidates", "rounds", "final_plan", "human_flags",
            "audit_passed", "audit_status", "outreach", "channel_plan", "outreach_plan", "past_lessons", "recent_visits", "ev_context",
            "stop_details"]
    record = {k: state.get(k) for k in keys}
    record.update(run_id=run_id, limits=limits, claims=claims,
                  labels={r["geo_id"]: r.get("label") for r in state.get("all_scores", [])},
                  all_scores=state.get("all_scores", []), memory_after=mem)
    with open(os.path.join(RUNS_DIR, f"{run_id}.json"), "w") as f:
        json.dump(record, f, indent=2, default=str)
    return ({"limits": limits, "run_id": run_id},
            f"Limits list: {len(limits)} entries. Run saved as {run_id}; memory updated "
            f"({len(mem['lessons'])} lessons, {len(mem['visits'])} visits).")


# ------------------------------------------------------------------ Planner tool
def stop_distances(geo_ids: list[str], tool_context: ToolContext) -> dict:
    """Straight-line km between every pair of candidate tracts you are considering. Call it on your
    four picks before answering; every pair must be at least 5 km apart."""
    pool = {r["geo_id"]: r for r in tool_context.state.get("all_scores", [])}
    pairs, missing = [], [g for g in geo_ids if g not in pool]
    ok = [g for g in geo_ids if g in pool]
    for i, a in enumerate(ok):
        for b in ok[i + 1:]:
            d = round(km_between(pool[a], pool[b]), 2)
            pairs.append({"a": a, "b": b, "km": d, "ok": d >= MIN_KM_BETWEEN_STOPS})
    return {"pairs": pairs, "all_ok": all(p["ok"] for p in pairs), "unknown_tracts": missing,
            "min_km_required": MIN_KM_BETWEEN_STOPS}


# ------------------------------------------------------------------ Auditor tool
async def check_plan(tool_context: ToolContext) -> dict:
    """Run the deterministic audit checks on the current draft plan: spacing, candidate and claim
    validity, scale misuse, tie-band overclaiming, and demographic disparity against the county
    and against the county's highest-need tracts. Returns flags and the demographic comparison."""
    st = tool_context.state
    plan = parse_json(st.get("draft_plan"))
    stops = plan.get("stops", [])
    cands = {c["geo_id"]: c for c in st.get("candidates", [])}
    claims = st.get("claims", {})
    flags = []
    if len(stops) != 4:
        flags.append({"code": "NOT_A_CANDIDATE", "claim_ids": [], "route": "revise",
                      "detail": f"plan has {len(stops)} stops, needs 4"})
    for s in stops:
        if s.get("geo_id") not in cands:
            flags.append({"code": "NOT_A_CANDIDATE", "claim_ids": [str(s.get("geo_id"))], "route": "revise"})
        bad = [c for c in s.get("claim_ids", []) if c not in claims]
        if bad:
            flags.append({"code": "UNKNOWN_CLAIM", "claim_ids": bad, "route": "revise"})
        wrong_scale = [c for c in s.get("claim_ids", []) if c in claims and claims[c]["scale"] in ("county", "health_service_area")]
        if wrong_scale:
            flags.append({"code": "SCALE_MISUSE", "claim_ids": wrong_scale, "route": "revise"})
    chosen = [cands[s["geo_id"]] for s in stops if s.get("geo_id") in cands]
    for i, a in enumerate(chosen):
        for b in chosen[i + 1:]:
            d = km_between(a, b)
            if d < MIN_KM_BETWEEN_STOPS:
                flags.append({"code": "STOPS_TOO_CLOSE", "route": "revise",
                              "claim_ids": [a["claim_ids"]["score"], b["claim_ids"]["score"]],
                              "detail": f"{a['geo_id']} and {b['geo_id']} are {d:.1f} km apart"})
    # Tie bands: note when an unchosen candidate is inside a chosen tract's band (ledger only).
    chosen_ids = {c["geo_id"] for c in chosen}
    ties = [c["claim_ids"]["score"] for c in chosen
            if any(o["geo_id"] not in chosen_ids and o["rank_band"][0] <= c["rank"] <= o["rank_band"][1]
                   for o in cands.values())]
    if ties:
        flags.append({"code": "NO_INTERVAL", "claim_ids": ties, "route": "ledger"})
    # Ranking language for a tract that sits in a tie band with an unchosen tract is an overclaim.
    rank_words = re.compile(r"(#\s*\d|\branked?\s*(first|second|third|\d)|\bhighest\b|\btop[- ]ranked\b|"
                            r"\bsecond[- ]highest\b|\bmost (in )?need)", re.I)
    for s in stops:
        c = cands.get(s.get("geo_id"))
        if c and c["claim_ids"]["score"] in ties and rank_words.search(s.get("reason", "")):
            flags.append({"code": "OVERCLAIM_TIE", "route": "revise", "claim_ids": [c["claim_ids"]["score"]],
                          "detail": f"reason for {c['geo_id']} ranks it, but its score is tied with an "
                                    f"unchosen tract (rank band {c['rank_band'][0]}-{c['rank_band'][1]})"})

    demo = None
    if chosen:
        plan_rows = await call_tool("demographics_for_tracts", geo_ids=[c["geo_id"] for c in chosen])
        base = {r["baseline"]: r for r in await call_tool("demographics_baseline", county_fips=COUNTY_FIPS)}

        def shares(rows):
            tot = sum(r["total_pop"] or 0 for r in rows) or 1
            return {k: round(100 * sum(r[k] or 0 for r in rows) / tot, 1)
                    for k in ("black_pop", "hispanic_pop", "white_pop", "asian_pop")}
        plan_sh = shares(plan_rows)
        ref = base.get("most_uninsured_tenth", {})
        ref_sh = {"black_pop": ref.get("pct_black"), "hispanic_pop": ref.get("pct_hispanic"),
                  "white_pop": ref.get("pct_white_non_hispanic"), "asian_pop": ref.get("pct_asian")}
        gaps = {k: round(plan_sh[k] - (ref_sh[k] or 0), 1) for k in plan_sh}
        demo = {"plan": plan_sh, "most_uninsured_tenth": ref_sh, "county": base.get("county"),
                "gap_vs_most_uninsured_pts": gaps, "threshold_pts": DISPARITY_THRESHOLD_PTS,
                # per-stop breakdown, so one stop cannot hide behind the combined share
                "per_stop": [{"geo_id": r["geo_id"], "total_pop": r["total_pop"],
                              **{k: r.get(k) for k in r if k.startswith("pct_")}} for r in plan_rows]}
        worst = max(gaps, key=lambda k: abs(gaps[k]))
        if abs(gaps[worst]) > DISPARITY_THRESHOLD_PTS:
            flags.append({"code": "DEMOGRAPHIC_DISPARITY", "route": "human",
                          "claim_ids": [c["claim_ids"]["score"] for c in chosen],
                          "detail": f"{worst.replace('_pop', '')} share differs by {gaps[worst]:+.0f} pts from "
                                    f"the county's most-uninsured tenth of tracts"})
    result = {"flags": flags, "demographics": demo}
    tool_context.state["audit_checks"] = result
    return result
