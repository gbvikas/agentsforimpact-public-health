# EquiVita: pitch video script + deck outline (~2 minutes)

The **pitch** video is deck-led: why this matters, what we found, why it's built this way, what it changes.
The **demo** video (`docs/demo-video-script.md`) shows the product working. Don't repeat the full
walkthrough here; use at most two short app clips.

Track: **Siting**, with Accountability and Explanation agents behind it. One slide per section below.
Front-load: assume you get cut off before the last slide.

---

## Slide 1 · Title (0:00–0:10)

**On slide:** EquiVita · "Where the mobile clinic parks next month, and why" · team names · Cook County, IL.

> "EquiVita helps a county outreach lead decide where one mobile clinic van goes on four Saturdays, and
> explain that choice to the neighborhoods it chose and the ones it didn't."

## Slide 2 · The problem (0:10–0:25)

**On slide:** one van, one nurse practitioner, four Saturdays, 1,328 census tracts. "Last month it went where a councilman asked."

> "Park in the wrong place and you've run an expensive health fair for people who already have a doctor.
> The outreach lead has no epidemiologist, just a spreadsheet and a hunch."

## Slide 3 · The number that surprised us (0:25–0:45)

**On slide:** big number **−0.65**. Two small maps: "distance-first plan" (suburbs) vs "need-first plan".
Caption: *In Cook County, distance to a free clinic runs opposite to need.*

> "The intuitive formula, most need and farthest from care, sent the van to insured suburbs. Distance
> to a free clinic correlates minus 0.65 with households that have no car. Its top 30 tracts were less
> uninsured than the county median, and none was a federal shortage area."

## Slide 4 · The rule that shaped the architecture (0:45–1:10)

**On slide:** diagram: Planner (blind) → Auditor (sees race) → Human → Explainer; Field Reporter feeding memory.
Callout: *Race is banned as an input and required as an audit.*

> "Race can't be an input, but it must be an audit. So the auditor has to see data the planner can't,
> in a separate context, or it just defends the plan. That rule forced four agents: a blind planner, an
> auditor with census data, an explainer that writes for neighbors, and a field reporter. Their
> instructions conflict on purpose: the auditor hedges and cites; the explainer is warm and never hedges.
> And when the audit finds a disparity, it goes to a person, not back to the planner."

## Slide 5 · What changed because of the audit (1:10–1:25)

**On slide:** before/after table.

| | Distance-first | Need-first (human-approved) |
|---|---|---|
| Median uninsured, top 30 tracts | 8.6% | 24.5% |
| In a federal shortage area | 0 of 30 | 29 of 30 |
| Four stops (audit) | 81% white | majority Black and Hispanic |

> "The auditor flagged the first plan, a human switched the weights, and the system remembered why.
> One finding stays open honestly: the most-uninsured neighborhoods are 82 percent Hispanic, and four
> stops can't mirror that. We report it rather than hide it."

## Slide 6 · The loop no spreadsheet has (1:25–1:40)

**On slide:** circle: data → plan → audit → human → van goes out → **nurse reports back** → next plan.
Short clip (5–8 s): `/field` saving a voice debrief, "🔒 personal details removed".

> "After each Saturday the nurse just talks. A field reporter keeps place-level facts and drops anything
> about a person. Next month the planner skips a tract because of a free clinic our federal data couldn't
> see. Ground truth closes our biggest data gaps."

## Slide 7 · What we can't tell you (1:40–1:52)

**On slide:** four lines with scale tags.
- Air quality: 12 km grid, varies 6% across the county → never used to rank. *(county)*
- Disease trends: a four-county region. *(region)*
- Prevalence is modeled; vehicles and language are survey estimates. *(tract)*
- Distances are straight-line to federal sites only → upper bounds. *(facility point)*

> "Every number carries its scale, and the limits list ships with every plan. We even caught Gemini
> inventing a patient note from silence, so voice is gated on real sound first."

## Slide 8 · Built on Google Cloud, and what's next (1:52–2:05)

**On slide:** ADK multi-agent · Gemini 3.6 Flash · MCP Toolbox (BigQuery, per-agent toolsets) · our own
tools (`score_need`, `check_plan`, `stop_distances`) · memory as an append-only BigQuery log · Cloud Run.
Next: Outreach Kit (data-chosen channels: posters where homes lack internet, Spanish radio where English
is limited), travel-time data, a low-latency memory store (Cloud SQL).

> "EquiVita plans places, not people, and tells you what it can't see."

---

## Deck checklist (judges score the deck and videos only, with no Q&A)

- [ ] Say the track (Siting) on slide 1 or 2.
- [ ] The four judge questions are answered somewhere in the deck: put a small "Judge questions" appendix
      slide with the table from `docs/demo-video-script.md`.
- [ ] Measured vs. modeled is stated (slide 7).
- [ ] The equity audit numbers are shown, including the open finding (slide 5).
- [ ] One honest limitation line on every data slide.
- [ ] Links: live app, GitHub repo, Google Skills project.
