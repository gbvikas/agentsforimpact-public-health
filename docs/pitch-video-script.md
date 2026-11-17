# EquiVita: pitch video script (~3 minutes)

Track: **Siting**, with the Accountability and Explanation agents behind it.
Live app: https://equivita-375283687966.us-central1.run.app

**If the time limit is shorter than 3 minutes, read only the bold lines.**

## Before you press record

1. Open `/console` → **Reset memory**. Then on the home page press **Plan next month** once and let it finish
   (1–2 min). This creates the starting state: distance-first scoring, review banner showing.
2. Have a second tab on `/field`. Test the microphone once (any browser works).
3. Have `docs/clinic-plan-console-guide.pdf` page "Planner ⇄ Auditor" open as a backup screenshot of a
   rejected round (live runs don't always produce one).
4. Planning takes 1–2 minutes: **cut or speed up the waits** in the edit.

---

## 0:00 – 0:20 · The problem

**Screen:** EquiVita home page, top of the page.

> **"A county has one mobile clinic van, a nurse practitioner, and four Saturdays a month. Where it parks
> is a public-health decision. EquiVita helps the outreach lead at Cook County decide where the van goes,
> and the thing it knows that a spreadsheet doesn't is which numbers it can trust at which scale, and
> who its plan actually reaches."**

## 0:20 – 0:50 · The obvious answer fails

**Screen:** the review banner and the first plan (suburban stops). Point at the map.

> **"We started with the intuitive formula: most need, farthest from care. It sent the van to the suburbs.**
> In Cook County, distance to a free clinic runs *opposite* to need: it correlates minus 0.65 with
> households that have no car. The farthest tracts are insured, car-owning suburbs."

> **"Our auditor caught it. The four stops were 81 percent white; the county's most-uninsured
> neighborhoods are 82 percent Hispanic. But the planner never saw race. That's the rule here:
> race is banned as an input and required as an audit. And that rule forced our architecture."**

## 0:50 – 1:20 · A human decides, and the system remembers

**Screen:** click **Switch to need-first scoring** → **Plan next month** → the progress steps run (cut the wait).

> "The auditor isn't allowed to steer the planner by race, so it routes the finding to a person.
> The outreach lead switches to need-first scoring. That decision, and the reason, are written to
> memory, an append-only log in BigQuery, so next month starts from what we learned."

## 1:20 – 1:50 · The plan she can put on a calendar

**Screen:** the four Saturday cards, then the map, then the flyer EN/ES toggle.

> **"Four Saturdays, four neighborhoods, each with the reason in plain numbers: about one in four adults
> uninsured, one in three homes without a car.** Where to send people after the visit, and why this
> neighborhood and not the one next door. And a flyer and a door script in English and Spanish, written
> for a neighbor, not a professional."

## 1:50 – 2:25 · How we decided (the architecture)

**Screen:** "How we decided" / `/console`: live trace, then the Planner ⇄ Auditor rounds
(or the PDF backup showing round 1 rejected).

> **"This is four agents, not one with four prompts.** The planner works blind to demographics: its MCP
> Toolbox toolset has no demographic tool, so it can't even ask. The auditor runs in a separate context
> with census race data and checks scale, ties and spacing. Watch the state: the planner writes
> `draft_plan`, the auditor reads it and writes `audit_verdict`, and a code gate sends back only flag
> codes, never demographic detail."

> **"Here the system rejected its own first answer: two stops 3.9 kilometers apart. The planner revised.**
> The auditor's prompt says hedge, cite, refuse. The explainer's says warm, plain, no hedging. One
> agent can't hold both."

## 2:25 – 2:50 · The van talks back

**Screen:** `/field`. Pick Saturday 1, press **Speak**, say the debrief below, **Stop**, **Save report**.
Then **Plan next month** (cut the wait) and show the trade-offs line citing `fr-…`.

Say into the mic:
> "We parked at the church lot. Only nine people came. Most walked from the apartments across the
> expressway; the underpass felt unsafe. Mrs. Alvarez said her sugar is high. Four people asked about
> Medicaid. There's a free clinic at St. Columba a few blocks east."

Then narrate:
> **"After each Saturday the nurse just talks. A fourth agent keeps the place-level facts and removes
> anything about a person: Mrs. Alvarez is gone.** Next month the planner skips that tract and cites
> the report: a free clinic our federal data couldn't see, and a barrier straight-line distance can't
> measure. Ground truth closes our two biggest data gaps."

## 2:50 – 3:10 · Honest limits and the stack

**Screen:** "Good to know" / limits list, then the claims ledger.

> **"Every number carries its scale. Air quality is a 12-kilometer grid: it varies 6 percent across the
> county, so we never rank on it. Disease trends are a four-county region. Prevalence is modeled, not
> counted. Distances are straight-line to federal sites only, so they're upper bounds.** We even caught
> Gemini inventing a patient note from silence, so voice is gated on real sound before any model hears it."

> **"Google ADK, Gemini, MCP Toolbox over BigQuery, memory in BigQuery, deployed on Cloud Run.
> EquiVita plans places, not people, and tells you what it can't see."**

---

## The four judge questions, and where the video answers them

| Question | Where | The answer in one line |
|---|---|---|
| Delete any one agent: does it get worse? | 0:20–0:50, 2:25–2:50 | No auditor: the suburban plan ships unchallenged. No field reporter: the van returns to a tract with an unlisted free clinic. No explainer: no flyer. |
| A `session.state` key written by one agent, read by another | 1:50–2:25 | Planner writes `draft_plan` → Auditor reads it, writes `audit_verdict` → audit gate reads it, writes `revise_request` → Planner reads it. |
| Two agents whose instructions conflict | 1:50–2:25 | Auditor: hedge, cite, refuse. Explainer: warm, plain, no hedging. |
| Where the system rejected its own first answer | 2:00 (and 0:20 across runs) | Round 1 rejected for stops 3.9 km apart; and the human-approved switch from distance-first to need-first. |

## Numbers used (all from our own runs on Cook County, 1,328 tracts)

- Distance to a safety-net clinic vs. no-vehicle households: Spearman **−0.65**.
- Distance-first plan: stops **81% white**; most-uninsured tenth of tracts **82% Hispanic**; top-30 median uninsured **8.6%** (county median 10.4%), **0 of 30** in a federal shortage area.
- Need-first (v1) top-30 median uninsured **24.5%**.
- PM2.5 spread across tracts **1.06×** (p90/p10) vs. no-vehicle **16×**, uninsured **4.75×**.
- Honest open finding: even need-first stops are majority Black while the most-uninsured tenth is majority Hispanic; four stops can't mirror the county, so the flag stays open for a person to decide.
