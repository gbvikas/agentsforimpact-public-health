"""Print an outreach card for each stop of a saved run.

Usage: .venv/bin/python scripts/outreach_demo.py [run_id]      (default: newest run)
Needs gcloud credentials (reads BigQuery, including Overture Maps places in BigQuery public data).
"""
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "agent"))

from google.cloud import bigquery  # noqa: E402

from clinic_plan.outreach import outreach_card  # noqa: E402

PROJECT = os.environ.get("A4I_PROJECT", "qwiklabs-gcp-03-1a6edb739e38")
bq = bigquery.Client(project=PROJECT)

runs = sorted(glob.glob(os.path.join(ROOT, "agent", "runs", "*.json")))
path = next((r for r in runs if sys.argv[1:] and sys.argv[1] in r), runs[-1])
run = json.load(open(path))
stops = run["final_plan"]["stops"]
ids = [s["geo_id"] for s in stops]

county = dict(bq.query(f"""
  SELECT APPROX_QUANTILES(pct_no_internet, 4)[OFFSET(3)] AS p75_no_internet,
         APPROX_QUANTILES(pct_age_65_plus, 4)[OFFSET(3)] AS p75_age_65_plus
  FROM `{PROJECT}.a4i_health.burden_tracts`""").result().__iter__().__next__().items())

rows = {r["geo_id"]: dict(r.items()) for r in bq.query(f"""
  SELECT b.geo_id, b.latitude, b.longitude, b.pct_no_internet, b.pct_age_65_plus, b.pct_limited_english,
         SAFE_DIVIDE(c.speak_spanish_at_home, c.total_pop) * 100 AS pct_spanish
  FROM `{PROJECT}.a4i_health.burden_tracts` b
  LEFT JOIN `bigquery-public-data.census_bureau_acs.censustract_2018_5yr` c ON c.geo_id = b.geo_id
  WHERE b.geo_id IN UNNEST(@ids)""", job_config=bigquery.QueryJobConfig(
    query_parameters=[bigquery.ArrayQueryParameter("ids", "STRING", ids)])).result()}

print(f"Run {run['run_id']} · county top-quarter cutoffs: no-internet {county['p75_no_internet']:.0f}%, "
      f"age 65+ {county['p75_age_65_plus']:.0f}%\n")
for s in stops:
    r = rows[s["geo_id"]]
    card = outreach_card(s["geo_id"], r["latitude"], r["longitude"], r, county)
    print(f"=== Saturday {s['saturday']} · tract {s['geo_id']}")
    print("Places to post or ask:", "" if card["places"]["places"] else card["places"]["note"])
    for p in card["places"]["places"]:
        print(f"   - {p['name']} ({p['kind']}, {p['km_away']} km)")
    c = card["channels"]
    print(f"Channels ({c['internet']} internet): {c['why']}")
    for x in c["lead"]:
        print("   +", x)
    for x in c["skip"]:
        print("   -", x, "(skip)")
    l = card["languages"]
    print(f"Print in: {', '.join(l['print_in'])}. {l['why']}")
    if card["seniors"]:
        print("Older residents:", card["seniors"]["why"])
        for x in card["seniors"]["actions"]:
            print("   +", x)
    else:
        print("Older residents: not above the county's top quarter.")
    print()
print("Guardrails:")
for g in card["guardrails"]:
    print("  *", g)
print("\nGap:", card["languages"]["gap"])
