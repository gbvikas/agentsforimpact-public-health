---
name: data-traps
description: "The 8 BigQuery tables, their true resolutions, key columns, the 9 federal-data defects, and per-county gaps (Fulton/Cook/etc.)"
metadata:
  node_type: memory
  type: project
  originSessionId: e580f079-8de7-49f4-9f0f-bb27f2a97aee
  modified: 2026-11-17T19:07:00.361Z
---

**Core lesson: precision ≠ resolution.** Tables are at 4 scales and none says so. Agent must tag every claim with its scale: tract · 12 km grid · facility point · multi-county Health Service Area (HSA). Blending them into one confident sentence is the #1 way to lose points. Confident wrong answer = worst output.

**Tables in `<project>.a4i_health`** (load: notebook `c5_01_load_explore.ipynb` or `bash scripts/load.sh <5-digit FIPS>`):
- `burden_tracts` (tract, PLACES = MODELED prevalence, + SVI): pct_uninsured (18–64, PLACES), pct_uninsured_all_ages (SVI) + uninsured_gap, pct_checkup (LOW is bad; others high is bad), pct_asthma/copd/diabetes/high_bp, disability measures, pct_lack_transport (NULL in 11 states incl. TX), pct_no_vehicle, pctile_no_vehicle, pctile_uninsured (SVI EPL_* national 0–1 percentiles — use these for ranking), pct_age_65_plus, pct_limited_english (drives flyer language!), pct_no_internet, svi_* themes, centroid. **No race columns** (SVI Theme 3 / RPL_THEMES deliberately excluded) → auditor must source demographics elsewhere (likely `bigquery-public-data.census_bureau_acs` tract tables — verify).
- `exposure_tracts` (12 km GRID wearing tract ID): PM2.5 mean/max, days_over_12/20/25/35. Spread across Fulton tracts ~5% → useless for ranking neighborhoods; only good for county-level / bad-day claims. LEFT join from burden.
- `tract_access` (THE key table): km_to_any_care, km_to_safety_net, gap. Straight-line, not travel time; federal sites only → every distance is an UPPER BOUND ("nearest federally recognized site"); stops at county line (`care_sites_state` to re-measure).
- `care_sites` / `care_sites_state` (facility points, site_kind). HRSA layer has TOT_OPER_HR_PER_WEEK (capacity signal, 0–168 h).
- `shortage_areas` (HPSA areas, HPSA_SCORE folds in federal travel-time term = siting signal) vs `shortage_facilities` (where care already IS). NEVER union them (would site a van on a prison).
- `disease_weekly` (HSA region on a county key; fips is NUMERIC): ed_trends_covid/influenza/rsv. Cannot describe a neighborhood.

**9 defects:** 12 km grid as tract · two HPSA layers opposite meanings · `HPSA_WITHDRAWAL_DT IS NULL` filter does nothing, use HPSA_STATUS_DESC (39% "Proposed For Withdrawal") · HSA number on county key · lat/lon transposed in air files · SVI -999 sentinel · RHC staffing columns 100% empty · `mobility_crudeprev_` trailing underscore · two uninsured columns measure different populations (pick one headline, say which). Also: pad FIPS/tract IDs to 5/11 chars (leading zero). PLACES has `_crude95ci` CIs — overlapping CIs mean ranking is decorative.

**County choice:**
| County | Strength | Missing |
|---|---|---|
| Fulton GA 13121 (default) | biggest safety-net gap: 135/326 tracts (41%), worst 28.6 km, 443,800 people >5 km | shortage_areas EMPTY (99/99 proposed withdrawal) |
| Cook IL 17031 | only county with everything; 498 live shortage areas | big (1,328 tracts) |
| Harris TX 48201 | strongest inequality (uninsured p90 40.8%) | no pct_lack_transport, no shortage areas |
| Travis TX 48453 | small, fast dev county | thin demo, no transport, no HPSA |
| Santa Clara CA 06085 | only county where air spreads (1.20×) | disease_weekly all NULL, no HPSA |
| Bronx NY 36005 | sharp test: van NOT justified on distance (max gap 650 m) | no disease data |

Fulton hero tract: 13121010214 — 1,938 people, 14% uninsured, 43% no vehicle, 8.1 km to safety-net.

Not available (say so out loud): travel time (Access Across America is CC BY-NC — banned), free/county clinics, pharmacies, mobile clinic registries, tract-level disease counts. BYO data must be PD/CC0/US Gov; no NC/ND/SA, no individual-level.

See [[challenge-core]], [[solution-direction]].
