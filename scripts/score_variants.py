"""Compare candidate "needs the van" formulas, pick 4 spaced stops, and audit each.

Usage: .venv/bin/python scripts/score_variants.py [PROJECT.DATASET]
"""
import math
import subprocess
import sys

from google.cloud import bigquery

DS = sys.argv[1] if len(sys.argv) > 1 else "qwiklabs-gcp-03-1a6edb739e38.a4i_health"
PROJECT = DS.split(".")[0]
try:
    bq = bigquery.Client(project=PROJECT)
except Exception:
    from google.oauth2.credentials import Credentials
    tok = subprocess.check_output(["gcloud", "auth", "print-access-token"], text=True).strip()
    bq = bigquery.Client(project=PROJECT, credentials=Credentials(tok))

FEATURES = f"""
WITH hpsa AS (SELECT GEO_ID geo_id, MAX(HPSA_SCORE) hpsa_score FROM `{DS}.shortage_areas` GROUP BY 1),
f AS (
  SELECT b.geo_id, b.total_pop, b.latitude, b.longitude, b.pct_uninsured, b.pct_no_vehicle,
         b.pct_limited_english, a.km_to_safety_net, h.hpsa_score,
         PERCENT_RANK() OVER (ORDER BY b.pct_uninsured) pr_unins,
         (PERCENT_RANK() OVER (ORDER BY b.pct_diabetes) + PERCENT_RANK() OVER (ORDER BY b.pct_high_bp)
          + PERCENT_RANK() OVER (ORDER BY b.pct_copd)) / 3 pr_chronic,
         PERCENT_RANK() OVER (ORDER BY b.pct_no_vehicle) pr_noveh,
         PERCENT_RANK() OVER (ORDER BY b.pct_limited_english) pr_lep,
         PERCENT_RANK() OVER (ORDER BY a.km_to_safety_net * b.pct_no_vehicle) pr_carless_km,
         IFNULL((h.hpsa_score - 10) / 15, 0) shortage
  FROM `{DS}.burden_tracts` b JOIN `{DS}.tract_access` a USING (geo_id)
  LEFT JOIN hpsa h USING (geo_id)
  WHERE b.total_pop >= 500)
"""

VARIANTS = {
    "blueprint: need_pct x km x (1+noveh_pct)":
        "((pr_unins + pr_chronic) / 2) * km_to_safety_net * (1 + pr_noveh)",
    "v0: .5 need + .4 barrier(noveh, carless km) + .1 hpsa":
        "0.5 * (pr_unins + pr_chronic) / 2 + 0.4 * (pr_noveh + pr_carless_km) / 2 + 0.1 * shortage",
    "v1: .55 need(.6 unins/.4 chronic) + .35 barrier(noveh, lep, carless km) + .1 hpsa":
        "0.55 * (0.6 * pr_unins + 0.4 * pr_chronic)"
        " + 0.35 * (pr_noveh + pr_lep + pr_carless_km) / 3 + 0.1 * shortage",
}

ACS = "bigquery-public-data.census_bureau_acs.censustract_2020_5yr"


def km(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a.latitude, a.longitude, b.latitude, b.longitude))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 12742 * math.asin(math.sqrt(h))


def pick_spaced(df, n=4, min_km=5.0):
    picks = []
    for r in df.itertuples():
        if all(km(r, p) >= min_km for p in picks):
            picks.append(r)
        if len(picks) == n:
            break
    return picks


def audit(geo_ids):
    ids = ", ".join(f"'{g}'" for g in geo_ids)
    return bq.query(f"""SELECT ROUND(100*SUM(black_pop)/SUM(total_pop)) blk, ROUND(100*SUM(hispanic_pop)/SUM(total_pop)) hisp,
        ROUND(100*SUM(white_pop)/SUM(total_pop)) wht FROM `{ACS}` WHERE geo_id IN ({ids})""").to_dataframe().iloc[0]


county = bq.query(f"""SELECT ROUND(100*SUM(black_pop)/SUM(total_pop)) blk, ROUND(100*SUM(hispanic_pop)/SUM(total_pop)) hisp,
    ROUND(100*SUM(white_pop)/SUM(total_pop)) wht FROM `{ACS}` WHERE STARTS_WITH(geo_id, '17031')""").to_dataframe().iloc[0]
print(f"County baseline: Black {county.blk:.0f}% | Hispanic {county.hisp:.0f}% | White NH {county.wht:.0f}%")

for name, expr in VARIANTS.items():
    df = bq.query(FEATURES + f"SELECT *, {expr} AS score FROM f ORDER BY score DESC").to_dataframe()
    top30 = df.head(30)
    picks = pick_spaced(df.head(60))
    a30, a4 = audit(top30.geo_id), audit([p.geo_id for p in picks])
    print(f"\n=== {name}")
    print(f"  top-30: median uninsured {top30.pct_uninsured.median():.1f}% | median no-vehicle "
          f"{top30.pct_no_vehicle.median():.1f}% | median km {top30.km_to_safety_net.median():.2f} | "
          f"in HPSA {top30.hpsa_score.notna().sum()}/30")
    print(f"  top-30 audit: Black {a30.blk:.0f}% | Hispanic {a30.hisp:.0f}% | White NH {a30.wht:.0f}%")
    print(f"  4 spaced stops (>=5 km apart) audit: Black {a4.blk:.0f}% | Hispanic {a4.hisp:.0f}% | White NH {a4.wht:.0f}%")
    for p in picks:
        print(f"    {p.geo_id}  pop {p.total_pop:>5}  unins {p.pct_uninsured:>4.1f}%  noveh {p.pct_no_vehicle:>4.1f}%  "
              f"LEP {p.pct_limited_english:>4.1f}%  km {p.km_to_safety_net:>5.2f}  hpsa {p.hpsa_score}")
