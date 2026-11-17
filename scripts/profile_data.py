"""Profile the a4i_health tables: schemas, keys, join coverage, nulls and feature spread.

Usage (from repo root, after `gcloud auth application-default login`):
    .venv/bin/python scripts/profile_data.py [PROJECT] [DATASET]
"""
import sys

from google.cloud import bigquery

PROJECT = sys.argv[1] if len(sys.argv) > 1 else "qwiklabs-gcp-03-1a6edb739e38"
DATASET = sys.argv[2] if len(sys.argv) > 2 else "a4i_health"
T = f"{PROJECT}.{DATASET}"
try:
    bq = bigquery.Client(project=PROJECT)
except Exception:  # no application-default credentials: borrow the gcloud CLI login (~1h token)
    import subprocess
    from google.oauth2.credentials import Credentials
    token = subprocess.check_output(["gcloud", "auth", "print-access-token"], text=True).strip()
    bq = bigquery.Client(project=PROJECT, credentials=Credentials(token))


def q(sql):
    return bq.query(sql).to_dataframe()


def section(title):
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")


# 1. Inventory + schema: which tables carry which identifier
section("1. Tables, row counts, key columns")
tables = [t.table_id for t in bq.list_tables(T)]
KEYISH = ("geo_id", "GEO_ID", "fips", "FIPS", "STATE_COUNTY_FIPS_CD", "CMN_STATE_COUNTY_FIPS_CD",
          "county_geo_id", "latitude", "longitude", "week_end", "hsa", "hsa_counties")
schemas = {}
for t in tables:
    tbl = bq.get_table(f"{T}.{t}")
    schemas[t] = {f.name: f.field_type for f in tbl.schema}
    keys = [c for c in schemas[t] if c in KEYISH]
    print(f"{t:<22} {tbl.num_rows:>7,} rows  {len(schemas[t]):>3} cols  keys: {keys}")

for t, cols in schemas.items():
    print(f"\n-- {t}")
    print("   " + ", ".join(f"{c}:{ty}" for c, ty in cols.items()))

# 2. Tract-keyed tables: do the geo_ids line up?
section("2. Tract join coverage (geo_id)")
tract_tables = [t for t in ("burden_tracts", "tract_access", "exposure_tracts") if t in schemas]
for t in tract_tables:
    print(q(f"""SELECT '{t}' AS tbl, COUNT(*) n, COUNT(DISTINCT geo_id) n_distinct,
                COUNTIF(LENGTH(geo_id) != 11) bad_len FROM `{T}.{t}`""").to_string(index=False, header=False))
for a in tract_tables:
    for b in tract_tables:
        if a < b:
            print(q(f"""SELECT '{a} vs {b}' pair,
                  COUNTIF(x.geo_id IS NOT NULL AND y.geo_id IS NOT NULL) both_,
                  COUNTIF(y.geo_id IS NULL) only_{a[:6]}, COUNTIF(x.geo_id IS NULL) only_{b[:6]}
                FROM `{T}.{a}` x FULL OUTER JOIN `{T}.{b}` y USING (geo_id)""").to_string(index=False))

# 3. Non-tract tables: what grain are they really?
section("3. Non-tract tables")
if "care_sites" in schemas:
    print(q(f"SELECT site_kind, COUNT(*) n FROM `{T}.care_sites` GROUP BY 1 ORDER BY 2 DESC").to_string(index=False))
    if "TOT_OPER_HR_PER_WEEK" in schemas["care_sites"]:
        print(q(f"""SELECT COUNTIF(TOT_OPER_HR_PER_WEEK IS NOT NULL) has_hours,
                   APPROX_QUANTILES(TOT_OPER_HR_PER_WEEK, 4) hour_quartiles FROM `{T}.care_sites`""").to_string(index=False))
for t in ("shortage_areas", "shortage_facilities"):
    if t in schemas:
        n = q(f"SELECT COUNT(*) n FROM `{T}.{t}`").n[0]
        print(f"\n{t}: {n} rows")
        if n and "geo_id_len" in schemas[t]:
            print(q(f"""SELECT geo_id_len, HPSA_TYP_DESC, COUNT(*) n, ROUND(AVG(HPSA_SCORE),1) avg_score
                       FROM `{T}.{t}` GROUP BY 1,2 ORDER BY 1,2""").to_string(index=False))
if "disease_weekly" in schemas:
    cols = [c for c in schemas["disease_weekly"] if c.startswith("percent_visits")]
    nn = ", ".join(f"COUNTIF({c} IS NOT NULL) nn_{c[-8:]}" for c in cols)
    print("\ndisease_weekly:")
    print(q(f"""SELECT COUNT(*) weeks, MIN(week_end) first_wk, MAX(week_end) last_wk,
               ANY_VALUE(hsa) hsa, ANY_VALUE(hsa_counties) hsa_counties{', ' + nn if nn else ''}
               FROM `{T}.disease_weekly`""").T.to_string(header=False))

# 4. Feature profile: can each column actually separate tracts?
section("4. Feature profile (nulls, p10, p50, p90, p90/p10 spread)")
rows = []
for t in tract_tables:
    num = [c for c, ty in schemas[t].items()
           if ty in ("FLOAT", "INTEGER", "NUMERIC") and c not in ("latitude", "longitude")]
    parts = []
    for i, c in enumerate(num):
        parts += [f"COUNTIF({c} IS NULL) AS n_null_{i}", f"COUNTIF({c} = -999) AS n_sent_{i}",
                  f"APPROX_QUANTILES({c}, 10) AS qs_{i}"]
    r = q(f"SELECT {', '.join(parts)} FROM `{T}.{t}`").iloc[0]
    for i, c in enumerate(num):
        qs = r[f"qs_{i}"]
        qs = list(qs) if qs is not None and len(qs) == 11 else [None] * 11
        p10, p50, p90 = qs[1], qs[5], qs[9]
        spread = (p90 / p10) if p10 not in (None, 0) and p90 is not None else None
        rows.append((t, c, int(r[f"n_null_{i}"]), int(r[f"n_sent_{i}"]), p10, p50, p90, spread))
print(f"{'table':<16} {'column':<30} {'nulls':>5} {'-999':>4} {'p10':>9} {'p50':>9} {'p90':>9} {'p90/p10':>8}")
for t, c, nulls, sen, p10, p50, p90, s in rows:
    f = lambda v: f"{v:9.3f}" if v is not None else f"{'-':>9}"
    print(f"{t[:16]:<16} {c[:30]:<30} {nulls:>5} {sen:>4} {f(p10)} {f(p50)} {f(p90)} "
          f"{(f'{s:.2f}' if s is not None else '-'):>8}")

# 5. Correlations among candidate ranking features (double-counting check)
section("5. Correlations among candidate ranking features")
cand = ["pct_uninsured", "pct_uninsured_all_ages", "pct_checkup", "pct_diabetes", "pct_high_bp",
        "pct_copd", "pct_no_vehicle", "pct_lack_transport", "pct_age_65_plus",
        "svi_socioeconomic", "svi_housing_transport", "km_to_safety_net", "extra_km_if_uninsured"]
have_b = set(schemas.get("burden_tracts", {}))
have_a = set(schemas.get("tract_access", {})) - have_b
sel = [f"b.{c}" for c in cand if c in have_b] + [f"a.{c}" for c in cand if c in have_a]
if sel:
    df = q(f"""SELECT {', '.join(sel)} FROM `{T}.burden_tracts` b
               LEFT JOIN `{T}.tract_access` a USING (geo_id)""")
    df = df.loc[:, df.notna().sum() > 10]
    print(df.corr(method="spearman").round(2).to_string())
