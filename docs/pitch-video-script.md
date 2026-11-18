# EquiVita: pitch video script + pitch deck outline

**One video** (~3 minutes): a rapid-fire pitch that shows technical strength, usability and performance.
Slides open and close it; the middle is the live app. Read only the **bold** lines for a ~2-minute cut.

Live app: https://equivita-375283687966.us-central1.run.app · Track: **Siting** (with Accountability and
Explanation agents behind it).

## Before you press record

1. `/console` → **Reset memory**, then on the home page press **Plan next month** once and let it finish.
   The app now opens on the distance-first plan with the review banner. (Already done at 3:46 pm.)
2. A second tab on `/field`; test the microphone once (any browser).
3. Backup for the "rejected its own answer" beat: `docs/clinic-plan-console-guide.pdf`, page "Planner ⇄ Auditor".
4. A plan takes ~65 s: **cut or speed up the waits.**

---

## 0:00 – 0:15 · Slide: The Challenge

> **"One mobile clinic van, one nurse practitioner, four Saturdays a month, and 1,328 neighborhoods in
> Cook County. EquiVita helps the county's outreach lead decide where the van parks, and explains the
> choice to the community health workers and residents it serves."**

## 0:15 – 0:35 · Slide: the number that surprised us (−0.65)

> **"The obvious formula, most need and farthest from care, sends the van to insured suburbs. In Cook
> County, distance to a free clinic runs opposite to need: minus 0.65 against households with no car.**
> Its top 30 tracts were less uninsured than the county median, and none was a federal shortage area."

## 0:35 – 1:05 · Live: the audit catches it, a human decides (usability + performance)

**Screen:** home page banner → **Switch to need-first scoring** → **Plan next month** → progress chips.

> **"Our auditor flagged that plan: its stops were 81 percent white while the county's most-uninsured
> neighborhoods are 82 percent Hispanic. The planner never sees race; the rule here is race banned as
> input, required as audit. So the finding goes to a person, not back to the planner.** She switches to
> need-first scoring, and that decision is saved in memory, an append-only log in BigQuery."

> "Re-planning takes about a minute: data for all 1,328 tracts comes through MCP Toolbox and is scored in
> 3 seconds; the rest is four agents thinking and checking each other."

## 1:05 – 1:30 · Live: the plan (usability)

**Screen:** Saturday cards → map → flyer EN/ES toggle.

> **"Four dated Saturdays in plain language: about one in four adults uninsured, one in three homes
> without a car, the nearest free clinic for follow-up, and why this neighborhood and not the one next
> door.** Plus a flyer and door script in English and Spanish, and an outreach plan per stop: code picks
> the channels from the data, like posters and radio where many homes have no internet or Spanish-first
> where English is limited, and an agent orders them using real nearby places."

## 1:30 – 2:05 · Live: how it decided (technical strength)

**Screen:** "How we decided" → trace with state keys → Planner ⇄ Auditor rounds (or PDF backup).

> **"Five agents, built on Google ADK. The planner's MCP Toolbox toolset has no demographic tool, so it
> can't even ask for race. The auditor runs in a separate context with census data. They pass state:
> `draft_plan`, `audit_verdict`, `revise_request`, and a code gate strips anything demographic.**
> Here it rejected its own first draft, two stops 3.9 km apart, and revised. The auditor's instructions
> say hedge and cite; the explainer's say warm and never hedge: one agent can't hold both."

## 2:05 – 2:35 · Live: the van talks back (technical + usability)

**Screen:** `/field` → Saturday 1 → **Speak** → say the debrief → **Stop** → **Save report** → then
**Plan next month** and show the trade-offs line citing `fr-…` (cut the wait).

Say into the mic:
> "We parked at the church lot. Only nine people came. Most walked from the apartments across the
> expressway; the underpass felt unsafe. Mrs. Alvarez said her sugar is high. Four people asked about
> Medicaid. There's a free clinic at St. Columba a few blocks east."

> **"After each Saturday the nurse just talks. Gemini transcribes it in about two seconds, a fourth agent
> keeps the place-level facts, and a code privacy gate removes the person: Mrs. Alvarez is gone. Next
> month the planner skips that tract and cites the report: a free clinic our federal data couldn't see."**

## 2:35 – 3:00 · Slide: Impact, limits, stack

> **"Need-first plans reach tracts where nearly one in five adults is uninsured, up from under one in ten,
> and all top 30 are federal shortage areas, up from none.** One finding stays open: the plan lands mostly
> in Black neighborhoods while the county's most-uninsured are mostly Hispanic. We chose not to score on
> language, so it can't act as a stand-in for ethnicity; language picks the outreach channels instead.
> The flag stays open for a person to decide, and we say so."

> **"Every number carries its scale: air quality is a 12 km grid that varies 6 percent, so we never rank
> on it; prevalence is modeled; distances are upper bounds. ADK, Gemini, MCP Toolbox, BigQuery, Cloud Run.
> EquiVita plans places, not people, and tells you what it can't see."**

---

# Pitch deck outline (fill the team template from Discord)

The portal requires four sections: **Challenge, Impact, Intel Sources, Prototype Architecture.** Judges
see only the deck and the video, so the four judge questions go in an appendix slide.

## 1 · Title
EquiVita · "Where the mobile clinic parks next month, and why" · team · Agents for Impact 2026, Challenge 5 · live link.

## 2 · The Challenge
- **Who:** the county outreach lead (plans the van), community health workers (explain it door to door),
  the nurse practitioner (runs the Saturday).
- **Problem:** one van, four Saturdays, 1,328 Cook County tracts; decisions made on hunches and requests.
- **Why it matters:** preventive care is the one part of health you can plan in advance; the wrong
  parking spot is an expensive health fair for people who already have a doctor.
- **Track:** Siting, with Accountability and Explanation built in.

## 3 · Impact
- Before/after table:

| | Distance-first (intuitive) | Need-first (human-approved) |
|---|---|---|
| Median uninsured, top 30 tracts | 8.6% (below county median 10.5%) | 18.0% |
| Top 30 in a federal shortage area | 0 | 30 |
| Median homes without a car, top 30 | 7.0% | 49.5% |
| Correlation, distance vs no car | −0.65 | n/a |

- What changes for each user: a calendar-ready plan with reasons; bilingual flyers and door scripts;
  a voice debrief that improves next month's plan.
- Honest open finding: need-first top 30 is 85% Black / 11% Hispanic; the most-uninsured tenth is 82% Hispanic.
  Limited English is deliberately not scored (too close to an ethnicity proxy); it chooses outreach channels.
- Performance: full plan in ~65 s on Cloud Run; 1,328 tracts scored in 3 s; voice transcribed in ~2 s.

## 4 · Intel Sources

| Source | Used for | Scale | Measured or modeled |
|---|---|---|---|
| CDC PLACES 2025 | Uninsured, diabetes, blood pressure, COPD | Tract | Modeled |
| CDC/ATSDR SVI 2022 | No vehicle, limited English, no internet, age | Tract | Survey estimate |
| HRSA health centers + CMS facilities | Free/sliding-scale clinic locations, hours | Facility point | Measured (federal only) |
| HRSA shortage areas (HPSA) | Federal shortage score | Tract (Cook) | Measured |
| EPA/CDC daily PM2.5 | County air context only (never ranks) | 12 km grid | Modeled |
| CDC NSSP ED visits | Regional respiratory trend only | 4-county region | Measured |
| Census ACS 2020 (BigQuery public) | **Auditor only:** race/ethnicity | Tract | Survey estimate |
| Census ZIP boundaries (BigQuery public) | Plain-English tract names | ZIP | Measured |
| Nurse field reports (ours) | Barriers, unlisted clinics, turnout | Observation | One day's observation |

Excluded on purpose: SVI race theme (as input), Access Across America transit (CC BY-NC), Chicago
community-area names (no clear license), NPPES and anything patient-level.

## 5 · Prototype Architecture (schematic)
Use the diagram image `docs/architecture.png`. One line under it: *"Race is banned as an input and
required as an audit; that rule forced a blind planner and a separate auditor."*

## 6 · Appendix · The four judge questions

| Question | Our answer |
|---|---|
| Delete any one agent: does it get worse? | No auditor: the suburban plan ships unchallenged. No field reporter: the van returns to a tract with an unlisted free clinic. No explainer: no flyer for residents. |
| A `session.state` key written by one agent, read by another | Planner writes `draft_plan` → Auditor reads it, writes `audit_verdict` → audit gate writes `revise_request` → Planner reads it. |
| Two agents whose instructions conflict | Auditor: hedge, cite, refuse. Explainer: warm, plain, never hedge. |
| Where the system rejected its own first answer | Round 1 rejected (stops 3.9 km apart) and revised; and the human-approved switch from distance-first to need-first after the audit. |

## 7 · Limits and next
Limits: straight-line distance, federal sites only, modeled prevalence, regional disease data, no
confidence intervals loaded, Spanish as the only second language. Next: travel-time data, more languages, a low-latency memory store (Cloud SQL / Firestore).
