---
name: cook-data-profile
description: "Measured profile of the loaded dataset (Cook County IL 17031) — join coverage, feature spread, correlations, surprises that shape the ranking"
metadata:
  node_type: memory
  type: project
  originSessionId: e580f079-8de7-49f4-9f0f-bb27f2a97aee
  modified: 2026-11-17T20:12:32.518Z
---

Profiled 2026-11-17 via `scripts/profile_data.py`. **Loaded county is Cook IL (17031), not Fulton.**

**Tables:** burden_tracts 1,328 = tract_access 1,328 (perfect join); exposure_tracts 1,332 (4 extra → LEFT join). No nulls, no -999 in any tract feature (pct_lack_transport populated — IL has it). care_sites 523 = 240 HRSA "Health Center site" + 208 CMS "FQHC" + 75 Hospital; 128 of 208 FQHCs sit within 50 m of a Health Center site (same clinic listed twice → don't count clinics as supply without dedup). Hours (TOT_OPER_HR_PER_WEEK) only on the 240 Health Center sites: quartiles 1/40/42.5/53/85. shortage_areas 498 rows, ALL 11-char GEO_ID = tract-level in Cook (53 Geographic + 445 Population HPSAs), 468 distinct tracts, 467 join to burden (35% of tracts), HPSA_SCORE 11–20 (multiple designations per tract → take MAX). shortage_facilities 31. disease_weekly 215 weeks to 2026-11-07, HSA = Cook+DuPage+Lake+McHenry; `fips` is STRING here (README said number); percent_visits_combined only 105/215 non-null.

**Spread p90/p10 (can it separate tracts?):** no_vehicle 16.4×, km_to_safety_net 13.2×, km_to_any 10.6×, pctile_uninsured 8.2×, pct_uninsured 4.75×, lack_transport 4.5×, diabetes 3.0×, copd 3.2×, high_bp 2.2×, asthma 1.49×, checkup 1.14× (weak), mean_pm 1.06× (useless). extra_km_if_uninsured median 0, p90 1.24 km → Cook has little safety-net gap.

**Surprises (pitch material):**
- km_to_safety_net vs pct_no_vehicle Spearman **−0.65**; vs pct_uninsured −0.26; vs age65 +0.34. Far-from-clinic tracts in Cook are suburban, older, insured, car-owning. Ranking on distance alone sends the van to the wrong people → need×distance must be designed carefully (distance matters only where no car).
- diabetes/high_bp/copd inter-correlate 0.88–0.91 → one "chronic burden" factor, not three votes.
- pct_lack_transport ≈ modeled; correlates 0.83 uninsured, 0.92 svi_socioeconomic → redundant. pct_no_vehicle (ACS, measured) only 0.20 with uninsured → independent signal; prefer it.
- pct_uninsured vs svi_socioeconomic 0.85 → don't use both.
- pct_checkup correlates +0.79 high_bp, +0.59 age65 → age-confounded; weak.
- pct_limited_english p90 16.5% → multilingual outreach required.

See [[data-traps]], [[solution-direction]].

**Need score v0 (`sql/need_score.sql`, 2026-11-17):** 0.5·need (pr uninsured + pr chronic) + 0.4·barrier (pr no-vehicle + pr car-less km) + 0.1·HPSA. Top 10 = all South Side Chicago, all in HPSA tracts, ~50–67% no vehicle, 15–26% uninsured, span 16.7 km (clustered → need spacing rule). Score gap #10 vs #30 only 0.038 → treat top ~30 as a tie band, not a strict order. Distance-only lens top 10 = suburban 8240xx tracts, ~6% uninsured, ~0–2% no vehicle, need rank 500–1300 (the "obvious answer fails" slide).

**Audit preview (ACS `bigquery-public-data.census_bureau_acs.censustract_2020_5yr`, all 1,328 tracts match):** county 23% Black / 25% Hispanic / 42% white NH. Score top-30 = **87% Black / 8% Hispanic**. Top-decile-uninsured tracts = **81% Hispanic**. → v0 plan under-serves the most-uninsured (Latino) neighborhoods because barrier weights no-vehicle and ignores language; chronic prevalence is PLACES-modeled (possible race leakage). This is the planner-vs-auditor disagreement / "rejected its first answer" demo moment. Candidate fixes: weight uninsured more, add pct_limited_english as an access barrier, spread 4 Saturdays across distinct communities.
