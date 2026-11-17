---
name: solution-direction
description: "Our team's working architecture + open decisions for the mobile clinic agent (as of 2026-11-17 brainstorm, DRAFT)"
metadata:
  node_type: memory
  type: project
  originSessionId: e580f079-8de7-49f4-9f0f-bb27f2a97aee
  modified: 2026-11-17T19:25:41.205Z
---

Status 2026-11-17: brainstorm stage, nothing decided by user yet. Update this as decisions land.

**Draft architecture (Claude's proposal):**
1. Coordinator LlmAgent (outreach lead's chat) → calls `clinic_plan` Workflow as a tool.
2. Parallel evidence nodes, each with its own output_key and a `scale` tag: `ev_burden` (tract, modeled), `ev_access` (tract, measured upper bound), `ev_context` (HPSA areas; disease = HSA region; air = 12 km grid/county only).
3. Custom tool `score_need` (our "built it ourselves" tool): need × access barrier, e.g. need = pctile_uninsured + low checkup + chronic burden; barrier = km_to_safety_net weighted by no-vehicle share; CI-overlap → tie bands; spread the 4 Saturdays geographically. → `state.candidates`.
4. Planner LlmAgent (blind to demographics) → `state.draft_plan` (4 tracts + reasons).
5. Auditor LlmAgent, separate context, sees race/ethnicity (planner was denied; burden_tracts has none → pull ACS tract demographics) + checks scale violations + CI ties → `state.audit_verdict` {approve|revise, findings}. Revise loops back to planner (cycle, set timeout, max ~2 rounds) = "system rejected its own first answer".
6. Explainer LlmAgent (warm, 6th-grade, no hedging, EN + language from pct_limited_english) → flyer + CHW "why here and not next door" script → `state.outreach`. Its prompt directly contradicts auditor's hedge/cite prompt.
7. "What we couldn't tell you" ledger — deterministic node listing every claim's scale + missing layers.

**Ranking framing (discussed 2026-11-17):** row = census tract (`geo_id`, 11-char). Score ≈ NEED × BARRIER, then pick a SET of 4 (spread out, ties respected), then explain. Feature roles:
- Rank on (tract-level, varies): need = pct_uninsured/pctile_uninsured, pct_checkup (inverted), diabetes/high_bp/copd/asthma; barrier = km_to_safety_net, extra_km_if_uninsured, pct_no_vehicle/pctile_no_vehicle, pct_lack_transport (NULL in TX), mobility, age65.
- Context/tie-break: HPSA_SCORE (often empty), clinic hours, svi_* themes (careful: theme 4 already contains no-vehicle → double count).
- Shape the outreach, not the rank: pct_limited_english (language), pct_no_internet (flyer vs SMS).
- Never rank on: PM2.5 (12 km grid), disease_weekly (region → maybe *when*, not *where*).
- Audit only: race/ethnicity (ACS). Caveat to verify: PLACES is model-based and may use race in its small-area model → race can leak in through the prevalence features.
- Safety-net = site_kind IN ('FQHC','Health Center site'); tract_access has km_to_any_care, km_to_safety_net, extra_km_if_uninsured.
Idea: several ranking "lenses" (need-first, access-first, combined); tracts that top every lens are robust picks, and where lenses disagree the planner has to argue its choice.

**Ideas worth keeping:** "why not next door" tool (nearest unchosen neighbor tract + what differs, honest when CIs overlap); custom UI showing planner vs auditor disagreement live + map with 4 Saturdays; field-report agent stretch (NP debrief → BigQuery append → planner revises).

**Open decisions (user's call):** track to demo · county (Fulton = best story but no HPSA; Cook = complete data) · exact "needs the van" formula · front end (adk web vs custom) · MCP choice (lean Toolbox) · deploy target.

See [[challenge-core]], [[data-traps]], [[adk-api-gotchas]].
