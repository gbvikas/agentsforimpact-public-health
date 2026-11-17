"""clinic_plan: from an outreach lead's request to four Saturday stops.

recall_memory
  -> ParallelAgent(lookup_tracts, lookup_context)        code, via MCP Toolbox
  -> score_need                                          code, our own tool, versioned weights
  -> LoopAgent(max 2):  planner (LLM, Context A, blind)
                        auditor (LLM, Context B, sees demographics)
                        audit_gate (code: strips demographics, decides revise/pass)
  -> finalize_plan                                       code: cleared claims, nearest clinic, next door
  -> explainer (LLM, plain language EN + ES, no hedging)
  -> limits_and_persist                                  code: limits list, run record, memory
"""
import os

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from google.adk.agents import LlmAgent, LoopAgent, ParallelAgent, SequentialAgent  # noqa: E402
from toolbox_adk import ToolboxToolset  # noqa: E402

from . import steps  # noqa: E402
from .toolbox_bridge import auth_headers  # noqa: E402

MODEL = os.environ.get("MODEL", "gemini-3.6-flash")
TOOLBOX_URL = os.environ.get("TOOLBOX_URL", "http://127.0.0.1:5055")

PLANNER_INSTRUCTION = """You are the Planner for a county mobile health clinic: one van, a nurse
practitioner, four Saturdays next month. You choose where it parks. You plan for PLACES, never people.

You may only choose from the candidate tracts below, ranked by score_need (config {score_config_version}).
You cannot change the score. You never see or ask for race or ethnicity data.

Candidates (rank band = the ranks this tract could plausibly hold; overlapping bands are ties):
{candidates_table}

What memory says (lessons from past audits and human decisions):
{past_lessons}
Tracts the van already visited in earlier months: {recent_visits}

Field reports from the nurse practitioner after past Saturdays (ground truth our data cannot see:
real travel barriers, free clinics missing from federal lists, what people asked for):
{field_notes}
If a field report says a tract already has free care nearby, or a barrier kept people away, prefer a
nearby candidate across that barrier or a different tract, and cite the report ID (fr-...) in that
stop's claim_ids and reason. Field reports are one day's observations: use them to adjust, not to rank.

Auditor's revise request from the previous round (fix every item):
{revise_request}

Rules:
- Exactly 4 stops, one per Saturday, at least 5 km apart so the plan covers different communities.
- Prefer tracts not visited recently unless their need clearly dominates; say so if you repeat one.
- Every reason cites claim IDs from the table. Only tract-scale claims can justify a tract. The
  context claims (air, respiratory trend) describe the county or a region and can never justify
  choosing one tract over another.
- Do not call a tract "higher need" than an unchosen one inside its rank band; call them comparable.
- Before answering, call stop_distances on your four picks. If any pair is under 5 km, swap one
  for another candidate and check again. You cannot judge distance from tract IDs.
- You may use your other tools to look at a tract's neighbors or nearest clinics.

Return ONLY JSON:
{{"stops": [{{"saturday": 1, "geo_id": "...", "reason": "one or two sentences with numbers",
  "claim_ids": ["c-...", "..."]}}], "tradeoffs": "what you gave up and why"}}"""

AUDITOR_INSTRUCTION = """You are the Auditor. You are skeptical, precise and cautious. You hedge,
cite and refuse to clear anything you cannot verify. You did not write this plan and you do not
defend it.

Draft plan from the Planner (round {round} done so far):
{draft_plan}

score_need config: {score_meta}

Step 1: call the check_plan tool. It runs the deterministic checks (spacing, claim validity, scale,
tie bands) and compares the plan's tracts with race and ethnicity data the Planner never saw.
Step 2: read every reason in the plan yourself. Flag SCALE_MISUSE if a reason uses county air or
the regional respiratory trend to justify a tract, and OVERCLAIM_TIE if it calls a tract more needy
than another in the same rank band.
Step 3: decide.
- Route "revise" for problems the Planner can fix: STOPS_TOO_CLOSE, NOT_A_CANDIDATE, UNKNOWN_CLAIM,
  SCALE_MISUSE, OVERCLAIM_TIE.
- Route "human" for DEMOGRAPHIC_DISPARITY. Never send demographic findings to the Planner: steering
  the plan by race would end its blindness. A human decides whether the score weights should change.
- Route "ledger" for NO_INTERVAL notes.

Return ONLY JSON:
{{"verdict": "pass" or "revise", "flags": [{{"code": "...", "claim_ids": ["..."], "route": "revise|human|ledger",
  "message": "..."}}], "summary": "two sentences for the outreach lead, including the demographic
  comparison in plain numbers and what it might mean"}}"""

EXPLAINER_INSTRUCTION = """You write for neighbors, not professionals. Warm, direct, plain words, short
sentences, sixth-grade reading level. No hedging, no statistics jargon, no caveats: the limits list
travels separately. Never mention race, ethnicity or anyone's health condition. Never give medical
advice. Use ONLY the facts below; if a stop says NO CLEARED CLAIMS, write nothing for it.

Facts for each stop:
{cleared_brief}

For each stop write, in English and then in Spanish:
1. A flyer (max 70 words): free check-up van (blood pressure, blood sugar), Saturday number, no
   insurance needed, and the nearest free clinic for after the visit.
2. A 3-sentence script a community health worker can say at the door, including "why here and not
   next door" in plain words using the next-door comparison.
Use markdown headings per stop."""

planner = LlmAgent(
    name="planner",
    model=MODEL,
    description="Context A. Picks four Saturday stops from score_need candidates. Blind to demographics.",
    instruction=PLANNER_INSTRUCTION,
    tools=[steps.stop_distances, ToolboxToolset(server_url=TOOLBOX_URL, toolset_name="planner_drilldown",
                                                 additional_headers=auth_headers())],
    include_contents="none",          # never sees the Auditor's tool results in the conversation
    output_key="draft_plan",
)

auditor = LlmAgent(
    name="auditor",
    model=MODEL,
    description="Context B. Audits the draft plan with data the Planner cannot see.",
    instruction=AUDITOR_INSTRUCTION,
    tools=[steps.check_plan, ToolboxToolset(server_url=TOOLBOX_URL, toolset_name="auditor",
                                                     additional_headers=auth_headers())],
    include_contents="none",
    output_key="audit_verdict",
)

explainer = LlmAgent(
    name="explainer",
    model=MODEL,
    description="Writes the flyer and the community health worker script, EN + ES, from cleared claims only.",
    instruction=EXPLAINER_INSTRUCTION,
    include_contents="none",
    output_key="outreach",
)

root_agent = SequentialAgent(
    name="clinic_plan",
    description="EquiVita: plans four Saturday mobile clinic stops for a county and explains them.",
    sub_agents=[
        steps.step("recall_memory", "Loads approved score config, past lessons and visits.", steps.recall_memory),
        ParallelAgent(name="lookups", description="Independent evidence lookups via MCP Toolbox.", sub_agents=[
            steps.step("lookup_tracts", "Burden + access for every tract.", steps.lookup_tracts),
            steps.step("lookup_context", "County air and regional respiratory trend.", steps.lookup_context),
        ]),
        steps.step("score_need", "Deterministic scoring with versioned weights.", steps.run_score_need),
        LoopAgent(name="plan_audit_loop", max_iterations=steps.MAX_ROUNDS, sub_agents=[
            planner,
            auditor,
            steps.step("audit_gate", "Merges audit flags; only codes go back to the Planner.", steps.audit_gate),
        ]),
        steps.step("finalize_plan", "Clears claims and gathers facts for the Explainer.", steps.finalize_plan),
        explainer,
        steps.step("limits_and_persist", "Builds the limits list, saves the run, updates memory.",
                   steps.limits_and_persist),
    ],
)
