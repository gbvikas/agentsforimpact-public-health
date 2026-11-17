# Outreach Kit: implementation spec

**Owner:** Kiran · **Target:** merged and deployed by ~4:00 pm · **Parallel work:** Field Reporter (Akshay/Vyomika)

## Goal

Today the Explainer writes one flyer and one door script per stop. The Outreach Kit turns that into
**the right message, in the right language, on the right channel, for each neighborhood**, with the
channel chosen by data, not by the LLM.

> "1 in 4 homes here have no internet → posters and radio, not Instagram."

This is the part of the Clinic Plan the challenge is named for ("the thing you hand to the
neighborhood") and that most teams skip.

## What ships

Per stop:

1. **Channel plan** (code, deterministic): which channels and why, citing the tract's numbers.
2. **Poster / bus-shelter billboard** (EN + ES): headline, date, "Free check-up · No insurance needed",
   the nearest free clinic for follow-up, and a QR code.
3. **SMS** (≤160 chars, EN + ES).
4. **15-second radio script** (EN + ES).
5. **Door script** for community health workers (EN + ES), as today.

Plus a public **`/van`** page ("Where's the van?") that the QR code points to: the four Saturdays,
the map and an EN/ES toggle. No login, no personal data.

## Design rules (do not break these)

- **Channel choice is code, not LLM.** The Explainer only writes text for the channels code picked.
- **Every number shown is a claim.** Add the new measures to the claims ledger with `scale: "tract"`,
  `caveats: ["SURVEY_ESTIMATE"]`. The Explainer may only use cleared claims.
- **No race or ethnicity anywhere in the kit.** Language need comes from `pct_limited_english`, which
  is a survey measure of language, not ethnicity. Never write "Hispanic neighborhood" or similar.
- **No medical advice, no individual data.** Places, not people.
- **Spanish is the only second language.** ACS `pct_limited_english` does not say *which* language.
  Add a limits-list entry: `LANGUAGE_UNSPECIFIED`, "Which languages residents need. The data counts
  limited-English households but not their language; we default to Spanish."

## Channel rules (put these in code)

Thresholds are from the Cook County profile (p50 → p90): no internet 10.9% → 25%, limited English
3.3% → 16.5%, age 65+ 14.6% → 24.4%.

| Condition (tract) | Channels added | Reason text template |
|---|---|---|
| always | `poster`, `door_script` | "Posters and door-knocking reach everyone." |
| `pct_no_internet >= 20` | `print_first` (laundromat, corner store, church bulletin), `radio` | "About 1 in {n} homes have no internet." |
| `pct_limited_english >= 10` | `spanish_first`, `radio_es` | "About 1 in {n} households have limited English." |
| `pct_age_65_plus >= 20` | `phone_tree`, `senior_center` | "About 1 in {n} residents are 65 or older." |
| `pct_no_internet < 10` | `sms`, `social` | "Most homes are online." |

"About 1 in N" = `round(100 / pct)`. Keep the same helper the home page uses.

## Implementation (keep it in new files to avoid merge conflicts)

The Field Reporter will touch `memory.py`, `recall_memory` in `steps.py`, and add a new agent.
To stay clear of that work, put all Outreach Kit logic in **new files**, with one small edit each
in `agent.py`, `steps.py` (persisted keys only) and `dashboard/app.py`.

### 1. New file `agent/clinic_plan/outreach.py`

```python
from .toolbox_bridge import call_tool

async def plan_channels(state):
    """Code step. Reads the final plan, fetches tract detail via MCP Toolbox, picks channels."""
    stops = state["final_plan"].get("stops", [])
    rows = await call_tool("tract_detail", geo_ids=[s["geo_id"] for s in stops])
    # rows already include pct_no_internet, pct_limited_english, pct_age_65_plus: no tools.yaml change needed
    # 1. apply the channel rules table above -> per-stop {"geo_id", "channels": [...], "reasons": [...]}
    # 2. add claims c-<last6>-no_internet / -limited_english / -age65 to state["claims"] (scale tract,
    #    caveats ["SURVEY_ESTIMATE"], audit "cleared" because they are code-computed facts, not plan claims)
    # 3. build a text brief for the Explainer, e.g.
    #    "Saturday 1, tract 17031838800: channels poster, door_script, spanish_first, radio_es.
    #     Why: about 1 in 9 households have limited English."
    return ({"channel_plan": plan, "claims": claims, "channel_brief": brief},
            f"Channel plan: {summary}")
```

`tract_detail` already returns `pct_no_internet`, `pct_limited_english` and `pct_age_65_plus`
(see `toolbox/tools.yaml`), so **you do not need to change Toolbox or redeploy it.**

### 2. Wire it into the workflow (`agent/clinic_plan/agent.py`)

Insert the step **after `finalize_plan` and before `explainer`**:

```python
from . import outreach
...
steps.step("finalize_plan", ...),
steps.step("plan_channels", "Chooses outreach channels per stop from tract data.", outreach.plan_channels),
explainer,
```

### 3. Update the Explainer (same file)

Keep its voice (warm, plain, no hedging). Change the inputs and output:

- Add `{channel_brief}` to the instruction, next to `{cleared_brief}`.
- Ask for **JSON only**, with `output_key="outreach_kit"`:

```json
{"stops": [{"saturday": 1, "geo_id": "...",
  "poster":  {"en": {"headline": "...", "body": "..."}, "es": {"headline": "...", "body": "..."}},
  "sms":     {"en": "...", "es": "..."},
  "radio":   {"en": "...", "es": "..."},
  "door_script": {"en": "...", "es": "..."}}]}
```

- Only fill channels that `channel_plan` picked for that stop. Leave others out.
- Keep `include_contents="none"`.
- **Backwards compatibility:** the home page and `/console` read `outreach` (markdown). Either keep a
  second markdown field or, simpler, add a tiny code step after the Explainer that renders
  `outreach_kit` into the old `outreach` markdown so nothing else breaks.

### 4. Persist the new keys (`agent/clinic_plan/steps.py`)

In `limits_and_persist`, add `"channel_plan"` and `"outreach_kit"` to the `keys` list. Add
`LANGUAGE_UNSPECIFIED` to `LIMIT_TEXT` and make sure it reaches the limits list. Code-wise: add the
code to the caveats of the `-limited_english` claims you create.

### 5. Public page `dashboard/van.html` + route in `dashboard/app.py`

```python
@app.get("/van")
def van():
    return FileResponse(os.path.join(os.path.dirname(__file__), "van.html"))
```

`van.html` reads `/api/runs` (latest) and `/api/runs/{id}`, and shows only: dates, tract name
("Census tract 8388"), nearest free clinic, the poster text and an EN/ES toggle. **Show no scores,
no audit data and no demographics on this page**: it is for residents.

QR code: `https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/1.0.0/qrcode.min.js`, encoding
`location.origin + "/van"`.

### 6. Home page (`dashboard/lead.html`)

Per stop, add an **Outreach Kit** section:
- channel chips with the reason ("📮 posters · 📻 radio (ES) — about 1 in 9 households have limited English");
- a **poster preview card** styled like a bus-shelter ad (big type, date, QR), with an EN/ES toggle;
- SMS shown in a phone-bubble style;
- a print button that prints only the poster.

## Running it locally without touching the live demo

The live app uses `a4i_health.agent_memory`. Locally, point at the dev table so your test runs don't
change what the live demo shows:

```bash
cd agentsforimpact-public-health
export GOOGLE_APPLICATION_CREDENTIALS=$(ls ~/.config/gcloud/legacy_credentials/*/adc.json)
export A4I_PROJECT=qwiklabs-gcp-03-1a6edb739e38
export MEMORY_TABLE=qwiklabs-gcp-03-1a6edb739e38.a4i_health.agent_memory_dev   # BigQuery, but not the live demo's table
toolbox/bin/toolbox --config toolbox/tools.yaml --port 5055 &      # see toolbox/README.md to download
.venv/bin/python -m uvicorn dashboard.app:app --port 8090          # open http://127.0.0.1:8090
```

(`agent/clinic_plan/.env` sets the project, `location=global` and the model. Copy it from
`.env.example` if you don't have one. Offline alternative: `MEMORY_BACKEND=file`, which writes the
gitignored `agent/memory_events.json`.)

Quick test without the UI: `.venv/bin/python agent/run_once.py`.

## Done when

- [ ] A run produces `channel_plan` and `outreach_kit` in `agent/runs/<id>.json`.
- [ ] At least one stop gets `spanish_first` and one gets `print_first` (true for Cook's top tracts).
- [ ] Every number in the kit traces to a claim ID in the ledger; `LANGUAGE_UNSPECIFIED` appears in the limits list.
- [ ] No race/ethnicity words in any kit text (grep the run JSON for "Hispanic", "Black", "Latino", "white").
- [ ] `/van` loads with no scores or demographics, and the QR code opens it.
- [ ] Home page and `/console` still render (the old `outreach` field still exists).
- [ ] Commit to `main`, then tell Akshay/Vyomika to redeploy (one deploy for both features).

## Deploy (after both features are merged)

```bash
P=qwiklabs-gcp-03-1a6edb739e38
gcloud run deploy equivita --source . --service-account clinic-plan-sa@$P.iam.gserviceaccount.com \
  --region us-central1 --project $P --allow-unauthenticated --no-cpu-throttling \
  --min-instances 1 --max-instances 1 --memory 1Gi --timeout 900 \
  --set-env-vars "GOOGLE_GENAI_USE_VERTEXAI=TRUE,GOOGLE_CLOUD_PROJECT=$P,GOOGLE_CLOUD_LOCATION=global,TOOLBOX_URL=https://clinic-toolbox-375283687966.us-central1.run.app,COUNTY_FIPS=17031,MODEL=gemini-3.6-flash,MEMORY_BACKEND=bigquery"
```

A redeploy wipes saved runs (memory in BigQuery survives). After deploying, open `/console`, press
**Reset memory**, then run once so the demo starts from its usual state.
