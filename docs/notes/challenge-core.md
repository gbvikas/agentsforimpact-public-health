---
name: challenge-core
description: "A4I 2026 Challenge 5 (mobile clinic siting) — goal, required tech, deliverables, judging weights, the 4 judge questions"
metadata:
  node_type: memory
  type: project
  originSessionId: e580f079-8de7-49f4-9f0f-bb27f2a97aee
  modified: 2026-11-17T19:06:44.599Z
---

Hackathon: Agents for Impact 2026, Challenge 5 "Dynamic Public Health Equity & Preventative Mobile Care Broker". Repo: `agentsforimpact-public-health/` (template; `agent/` is empty for our code). 4.5h build.

**The job:** one county, one van (nurse practitioner, BP cuff, glucometer), four Saturdays → pick 4 census tracts to park in, and explain why *this* street not the next one. Places, never people. Agent plans outreach; it does NOT practice medicine (demo showing agent talking to a patient = wrong thing).

**Three tracks = three agents** (user's notes match): Siting (planner; user = county outreach lead), Accountability (equity auditor; user = program director/funder report), Explanation (plain-language flyer/CHW script, multilingual; user = community health worker). Judged against the track we pick, but judges look for the other two agents behind it.

**Hard requirements:** Google ADK (Python) · Gemini 3.x (`gemini-3.6-flash` verified) · data in BigQuery `a4i_health` dataset · consume ≥1 Google-managed MCP server (BigQuery built-in MCP or MCP Toolbox for Databases — Toolbox preferred: fixed parameterized SQL) · ≥1 tool we wrote ourselves (best: the "ranked list → plan with reasons" logic, not just a query wrapper) · deploy to Agent Runtime or Cloud Run · genuine multi-agent orchestration (required differentiator).

**Output artifact "Clinic Plan" (4 parts):** (1) where the van goes ×4 with reasons + numbers + tract named; (2) what we could NOT tell you — scales named and counted (a finding, not a disclaimer); (3) who this plan lands on — equity audit vs. race/demographics, reported even if uncomfortable; (4) the thing handed to the neighborhood — flyer/SMS/CHW script, >1 language. Part 4 is what most teams skip.

**Submission:** GitHub repo, Google Skills project link, pitch deck, pitch video (screen-share). Judged after the event, no Q&A — everything must be said in deck/video.

**Scoring:** Impact & insight 30 · Technical execution 30 (real orchestration, state passing, disagreement) · Rigor & judgment 25 (defensible "needs the van" definition, measured vs modeled, validation WARNs, equity audit with numbers, limitations) · Craft 15 · Bonus range +10.

**The 4 judge questions (answer explicitly in deck/video):**
1. Delete any one agent — does the answer get worse? (show before/after)
2. Show a `session.state` key written by one agent, read by another.
3. Show two agents whose instructions genuinely conflict.
4. Show where the system rejected its own first answer. (separates winners)

Best line available: "The rule we were given (race banned as input, required as audit) forces the architecture." Do NOT justify multi-agent with the old "built-in tool can't share agent with function tool" limit — gone on Gemini 3.x and judges know it.

Fill-in before coding: "Our agent helps ___ in ___ County decide ___, and the thing it knows that a spreadsheet does not is ___."

See [[data-traps]], [[adk-api-gotchas]], [[solution-direction]].
