"""Outreach: how to reach the neighborhood around each stop. New file, so it stays clear of other work.

  plan_channels   code step. Rules pick the channels (never the LLM), from tract data via MCP Toolbox, and
                  look up named public places near each stop on the map (OpenStreetMap Overpass, no key).
  check_outreach  code step. Keeps the LLM's reasoning only where it uses channels code picked and places
                  that are really on the map list.
The LLM agent in between (agent.py) explains and prioritizes. It cannot add a channel or a place.
"""
import asyncio
import json
import os
import re

from .toolbox_bridge import call_tool

# ------------------------------------------------------------------ channel rules (spec thresholds)
NO_INTERNET_HIGH, NO_INTERNET_LOW = 20, 10
LIMITED_ENGLISH_HIGH = 10
AGE65_HIGH = 20

LABELS = {
    "poster": "Posters", "door_script": "Door-knocking",
    "print_first": "Print first: laundromat, corner store, church bulletin", "radio": "Local radio",
    "spanish_first": "Spanish first", "radio_es": "Spanish-language radio",
    "phone_tree": "Phone tree", "senior_center": "Senior centers",
    "sms": "Text reminder (opt-in)", "social": "Local social groups",
}

GUARDRAILS = [
    "Plan by place only: no lists of individuals, no person-level data.",
    "No health details in any poster, message or text.",
    "Texts go only to people who opted in, in their language, with a way to stop.",
    "Tract figures are survey estimates, not counts of people.",
]


def one_in(pct: float) -> int:
    """'About 1 in N' = round(100 / pct)."""
    return max(1, round(100 / pct)) if pct else 0


def pick_channels(row: dict) -> list[dict]:
    """The rules table: returns [{"channel", "because", "measure"}]. Deterministic."""
    ni, le, a65 = row.get("pct_no_internet"), row.get("pct_limited_english"), row.get("pct_age_65_plus")
    out = [{"channel": "poster", "because": "Posters and door-knocking reach everyone.", "measure": None},
           {"channel": "door_script", "because": "Posters and door-knocking reach everyone.", "measure": None}]
    if ni is not None and ni >= NO_INTERNET_HIGH:
        t = f"About 1 in {one_in(ni)} homes have no internet."
        out += [{"channel": c, "because": t, "measure": "no_internet"} for c in ("print_first", "radio")]
    if le is not None and le >= LIMITED_ENGLISH_HIGH:
        t = f"About 1 in {one_in(le)} households have limited English."
        out += [{"channel": c, "because": t, "measure": "limited_english"} for c in ("spanish_first", "radio_es")]
    if a65 is not None and a65 >= AGE65_HIGH:
        t = f"About 1 in {one_in(a65)} residents are 65 or older."
        out += [{"channel": c, "because": t, "measure": "age65"} for c in ("phone_tree", "senior_center")]
    if ni is not None and ni < NO_INTERNET_LOW:
        out += [{"channel": c, "because": "Most homes are online.", "measure": "no_internet"} for c in ("sms", "social")]
    return out


# ------------------------------------------------------------------ public places from the map
# Overture Maps places, a public dataset in BigQuery (no key, same login as the rest of the data).
PLACE_TABLE = "bigquery-public-data.overture_maps.place"
SCHOOLS = {"school", "elementary_school", "middle_school", "high_school", "preschool", "private_school",
           "public_school", "charter_school", "religious_school", "kindergarten"}
KIND_ORDER = ["Library", "Place of worship", "Community center", "Senior center", "School", "Grocery",
              "Pharmacy", "Laundromat"]


def _kind(tax: str, basic: str) -> str | None:
    t, b = (tax or ""), (basic or "")
    if "library" in t:
        return "Library"
    if "place_of_worship" in t or "place_of_worship" in b or t == "religious_organization":
        return "Place of worship"
    if t in ("community_center", "community_services_non_profits", "recreation_center") or "community_center" in t:
        return "Community center"
    if t in ("senior_center", "senior_citizen_services"):
        return "Senior center"
    if t in SCHOOLS:
        return "School"
    if t in ("grocery_store", "supermarket", "convenience_store"):
        return "Grocery"
    if t == "pharmacy":
        return "Pharmacy"
    if t in ("laundromat", "laundry_service", "self_service_laundry"):
        return "Laundromat"
    return None


_bq = None


def places_near(lat: float, lon: float, radius_m: int = 2000, per_kind: int = 2, limit: int = 6) -> dict:
    """Named public places near the tract center. Fails soft: a lookup problem never breaks a plan."""
    global _bq
    try:
        from google.cloud import bigquery
        _bq = _bq or bigquery.Client(project=os.environ.get("A4I_PROJECT") or os.environ.get("GOOGLE_CLOUD_PROJECT"))
        job = _bq.query(f"""
            SELECT names.primary AS name, taxonomy.primary AS tax, basic_category AS basic,
                   ST_DISTANCE(geometry, ST_GEOGPOINT(@lon, @lat)) / 1000 AS km,
                   ST_Y(geometry) AS lat, ST_X(geometry) AS lon
            FROM `{PLACE_TABLE}`
            WHERE ST_DWITHIN(geometry, ST_GEOGPOINT(@lon, @lat), @r)
              AND names.primary IS NOT NULL AND confidence >= 0.5
              AND (operating_status IS NULL OR operating_status != 'closed')
              AND REGEXP_CONTAINS(IFNULL(taxonomy.primary, ''),
                    r'library|place_of_worship|religious_organization|community|recreation_center|senior|school|kindergarten|grocery|supermarket|convenience_store|pharmacy|laundr')
            ORDER BY km LIMIT 200""", job_config=bigquery.QueryJobConfig(query_parameters=[
                bigquery.ScalarQueryParameter("lat", "FLOAT64", lat), bigquery.ScalarQueryParameter("lon", "FLOAT64", lon),
                bigquery.ScalarQueryParameter("r", "FLOAT64", float(radius_m))]))
        rows = list(job.result(timeout=40))
    except Exception as e:
        return {"places": [], "note": f"The places lookup did not answer ({type(e).__name__}), so no named places. "
                                      "Ask local partners for host sites."}
    found = []
    for r in rows:
        kind = _kind(r["tax"], r["basic"])
        if kind:
            found.append({"name": r["name"], "kind": kind, "km_away": round(r["km"], 2),
                          "lat": round(r["lat"], 5), "lon": round(r["lon"], 5)})
    picked, seen, count = [], set(), {}
    for p in found:                                  # already nearest first
        if p["name"] in seen or count.get(p["kind"], 0) >= per_kind:
            continue
        seen.add(p["name"])
        count[p["kind"]] = count.get(p["kind"], 0) + 1
        picked.append(p)
    picked = sorted(picked, key=lambda p: (KIND_ORDER.index(p["kind"]), p["km_away"]))
    picked = sorted(picked[:limit * 2], key=lambda p: p["km_away"])[:limit]
    return {"places": picked, "note": "" if picked else "No named public places in the map data nearby; coverage varies."}


# ------------------------------------------------------------------ workflow steps
async def plan_channels(state):
    """Code step. Reads the final plan, fetches tract detail via MCP Toolbox, picks channels, finds places."""
    stops = state["final_plan"].get("stops", [])
    ids = [s["geo_id"] for s in stops if s.get("geo_id")]
    rows = {r["geo_id"]: r for r in await call_tool("tract_detail", geo_ids=ids)} if ids else {}
    centers = {r["geo_id"]: r for r in state.get("all_scores", []) if r["geo_id"] in ids}
    claims = dict(state.get("claims", {}))
    places = {}

    async def look(g):
        c = centers.get(g)
        places[g] = await asyncio.to_thread(places_near, c["latitude"], c["longitude"]) if c else \
            {"places": [], "note": "No tract location."}
    await asyncio.gather(*(look(g) for g in ids))

    plan, lines = [], []
    for s in stops:
        g, r = s.get("geo_id"), rows.get(s.get("geo_id"))
        if not r:
            continue
        for key, col, caveats in (("no_internet", "pct_no_internet", ["SURVEY_ESTIMATE"]),
                                  ("limited_english", "pct_limited_english", ["SURVEY_ESTIMATE", "LANGUAGE_UNSPECIFIED"]),
                                  ("age65", "pct_age_65_plus", ["SURVEY_ESTIMATE"])):
            cid = f"c-{g[-6:]}-{key}"
            claims[cid] = dict(claim_id=cid, geo_id=g, measure=col, value=r.get(col), scale="tract",
                               source=f"burden_tracts.{col}", as_of="CDC SVI / ACS survey",
                               interval=None, null_state="ok" if r.get(col) is not None else "null",
                               caveats=caveats + ["NO_INTERVAL"], audit="cleared")
        chans = pick_channels(r)
        for c in chans:
            c["label"] = LABELS[c["channel"]]
            c["claim_id"] = f"c-{g[-6:]}-{c['measure']}" if c["measure"] else None
        pl = places.get(g, {"places": [], "note": ""})
        plan.append({"saturday": s.get("saturday"), "geo_id": g, "channels": chans,
                     "center": {"lat": (centers.get(g) or {}).get("latitude"), "lon": (centers.get(g) or {}).get("longitude")}, "places": pl["places"],
                     "places_note": pl["note"],
                     "print_in": ["English", "Spanish"] if any(c["channel"] == "spanish_first" for c in chans) else ["English"],
                     "numbers": {"no_internet": r.get("pct_no_internet"), "limited_english": r.get("pct_limited_english"),
                                 "age_65_plus": r.get("pct_age_65_plus")}})
        seen, why = set(), []
        for c in chans:
            if c["because"] not in seen:
                seen.add(c["because"])
                why.append(c["because"])
        pstr = "; ".join(f"{p['name']} ({p['kind']}, {p['km_away']} km)" for p in pl["places"]) or f"none ({pl['note']})"
        lines.append(f"Saturday {s.get('saturday')}, tract {g}\n  Channels chosen by code: "
                     f"{', '.join(c['channel'] for c in chans)}\n  Why: {' '.join(why)}\n  Named public places nearby: {pstr}")
    summary = "; ".join(f"Sat {p['saturday']}: {len(p['channels'])} channels, {len(p['places'])} places" for p in plan)
    return ({"channel_plan": plan, "claims": claims, "channel_brief": "\n".join(lines)}, f"Channel plan: {summary}")


async def check_outreach(state):
    """Code step. The LLM may only prioritize channels code picked and name places from the map list."""
    raw = {}
    m = re.search(r"\{.*\}", str(state.get("outreach_reasoning_raw") or ""), re.S)
    try:
        raw = json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        raw = {}
    by_sat = {s.get("saturday"): s for s in raw.get("stops", [])}
    out, dropped = [], 0
    for p in state.get("channel_plan", []):
        llm = by_sat.get(p["saturday"], {})
        have = {c["channel"]: c for c in p["channels"]}
        real = {x["name"] for x in p["places"]}
        prio = []
        for it in llm.get("priority", []):
            if it.get("channel") in have and it["channel"] not in [x["channel"] for x in prio]:
                prio.append({"channel": it["channel"], "label": LABELS[it["channel"]],
                             "because": it.get("because") or have[it["channel"]]["because"]})
            else:
                dropped += 1
        for c in p["channels"]:                       # anything the model skipped keeps the code's reason
            if c["channel"] not in [x["channel"] for x in prio]:
                prio.append({"channel": c["channel"], "label": c["label"], "because": c["because"]})
        used = [n for n in llm.get("places", []) if n in real]
        dropped += len(llm.get("places", [])) - len(used)
        out.append({"saturday": p["saturday"], "geo_id": p["geo_id"], "center": p.get("center"),
                    "headline": llm.get("headline", ""),
                    "channels": prio, "places": [x for x in p["places"] if x["name"] in used] or p["places"],
                    "print_in": p["print_in"], "caveat": llm.get("caveat") or p["places_note"],
                    "reasoned": bool(llm)})
    return ({"outreach_plan": {"stops": out, "guardrails": GUARDRAILS, "removed_by_check": dropped}},
            f"Outreach checked: {len(out)} stop(s); {dropped} item(s) the model added were removed.")
