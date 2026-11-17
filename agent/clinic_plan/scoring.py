"""score_need: our own deterministic tool. Agents read its output; none can change the formula.

Weights are versioned config. The approved version lives in agent memory and changes only
when a human approves a new one (see memory.approve_config).
"""
import math

import pandas as pd

SCORE_CONFIGS = {
    "v0-blueprint": {
        "label": "need_pct x km_to_safety_net x (1 + no-vehicle pct)",
        "kind": "product",
        "why": "The intuitive formula: most need, least access. Multiplying by km rewards distance.",
    },
    "v1": {
        "label": ".55 need (.6 uninsured, .4 chronic) + .35 barrier (no vehicle, limited English, "
                 "car-less km) + .10 shortage area",
        "kind": "additive",
        "w_need": 0.55, "w_unins": 0.6, "w_chronic": 0.4,
        "w_barrier": 0.35, "w_shortage": 0.10,
        "why": "Need leads; distance only counts for households without a car; language is an "
               "access barrier.",
    },
}

MEASURE_SOURCES = {
    "pct_uninsured": ("burden_tracts.pct_uninsured", ["MODELED_PREVALENCE"]),
    "pct_diabetes": ("burden_tracts.pct_diabetes", ["MODELED_PREVALENCE"]),
    "pct_no_vehicle": ("burden_tracts.pct_no_vehicle", ["SURVEY_ESTIMATE"]),
    "pct_limited_english": ("burden_tracts.pct_limited_english", ["SURVEY_ESTIMATE"]),
    "km_to_safety_net": ("tract_access.km_to_safety_net", ["STRAIGHT_LINE_KM", "FEDERAL_SITES_ONLY"]),
    "hpsa_score": ("shortage_areas.HPSA_SCORE", ["HPSA_MAX_OF_DESIGNATIONS"]),
}


def _pr(s: pd.Series) -> pd.Series:
    """Within-county percent rank, 0..1 (same as BigQuery PERCENT_RANK)."""
    r = s.rank(method="min")
    return (r - 1) / max(len(s) - 1, 1)


def score_need(rows: list[dict], version: str, top_n: int = 25) -> dict:
    cfg = SCORE_CONFIGS[version]
    df = pd.DataFrame(rows)
    needed = ["pct_uninsured", "pct_diabetes", "pct_high_bp", "pct_copd", "pct_no_vehicle",
              "pct_limited_english", "km_to_safety_net"]
    missing = df[df[needed].isna().any(axis=1)]
    df = df.dropna(subset=needed).copy()

    df["pr_unins"] = _pr(df.pct_uninsured)
    df["pr_chronic"] = (_pr(df.pct_diabetes) + _pr(df.pct_high_bp) + _pr(df.pct_copd)) / 3
    df["pr_noveh"] = _pr(df.pct_no_vehicle)
    df["pr_lep"] = _pr(df.pct_limited_english)
    df["pr_carless_km"] = _pr(df.km_to_safety_net * df.pct_no_vehicle)
    df["shortage"] = ((df.hpsa_score.astype(float) - 10) / 15).fillna(0).clip(0, 1)

    if cfg["kind"] == "product":
        df["need"] = (df.pr_unins + df.pr_chronic) / 2
        df["barrier"] = df.km_to_safety_net * (1 + df.pr_noveh)
        df["score"] = df.need * df.barrier
    else:
        df["need"] = cfg["w_unins"] * df.pr_unins + cfg["w_chronic"] * df.pr_chronic
        df["barrier"] = (df.pr_noveh + df.pr_lep + df.pr_carless_km) / 3
        df["score"] = (cfg["w_need"] * df.need + cfg["w_barrier"] * df.barrier
                       + cfg["w_shortage"] * df.shortage)

    df = df.sort_values("score", ascending=False).reset_index(drop=True)
    df["rank"] = df.index + 1
    # No confidence intervals are loaded, so a "tie band" stands in: tracts whose score is within
    # 2% of the score range of each other cannot honestly be ordered.
    band = 0.02 * (df.score.max() - df.score.min())
    top = df.head(top_n).copy()
    top["tie_band_low"] = top.score.apply(lambda s: int((df.score >= s - band).sum()))
    top["tie_band_high"] = top.score.apply(lambda s: int((df.score > s + band).sum()) + 1)

    claims, candidates = {}, []
    for r in top.itertuples():
        ids = {}
        for col, (source, caveats) in MEASURE_SOURCES.items():
            val = getattr(r, col)
            if val is None or (isinstance(val, float) and math.isnan(val)):
                val, null_state = None, "null"
            else:
                null_state = "ok"
            cid = f"c-{r.geo_id[-6:]}-{col.replace('pct_', '').replace('_to_safety_net', '')}"
            claims[cid] = dict(claim_id=cid, geo_id=r.geo_id, measure=col, value=val, scale="tract",
                               source=source, as_of="CDC PLACES 2025 / SVI 2022 / HRSA 2026",
                               interval=None, null_state=null_state,
                               caveats=caveats + ["NO_INTERVAL"], audit="not_reviewed")
            ids[col] = cid
        sid = f"c-{r.geo_id[-6:]}-score"
        claims[sid] = dict(claim_id=sid, geo_id=r.geo_id, measure="score", value=round(r.score, 4),
                           scale="tract", source=f"score_need {version}", as_of="computed",
                           interval=[r.tie_band_high, r.tie_band_low], null_state="ok",
                           caveats=["WITHIN_COUNTY_RANK", "NO_INTERVAL"], audit="not_reviewed")
        candidates.append(dict(
            geo_id=r.geo_id, rank=int(r.rank), score=round(float(r.score), 4),
            rank_band=[int(r.tie_band_high), int(r.tie_band_low)],
            need=round(float(r.need), 3), barrier=round(float(r.barrier), 3),
            total_pop=int(r.total_pop), latitude=float(r.latitude), longitude=float(r.longitude),
            pct_uninsured=float(r.pct_uninsured), pct_no_vehicle=float(r.pct_no_vehicle),
            pct_limited_english=float(r.pct_limited_english),
            pct_diabetes=float(r.pct_diabetes), pct_high_bp=float(r.pct_high_bp), pct_copd=float(r.pct_copd),
            km_to_safety_net=float(r.km_to_safety_net),
            # Percent ranks (0-1, within county) that feed the formula, so the UI can show why a tract scored high.
            components=dict(uninsured=round(float(r.pr_unins), 3), chronic=round(float(r.pr_chronic), 3),
                            no_vehicle=round(float(r.pr_noveh), 3), limited_english=round(float(r.pr_lep), 3),
                            carless_km=round(float(r.pr_carless_km), 3), shortage=round(float(r.shortage), 3)),
            hpsa_score=None if pd.isna(r.hpsa_score) else int(r.hpsa_score),
            claim_ids={**ids, "score": sid}))

    all_scores = df[["geo_id", "score", "need", "rank", "latitude", "longitude", "pct_uninsured",
                     "pct_no_vehicle", "km_to_safety_net"]].to_dict("records")
    return dict(
        meta=dict(config_version=version, formula=cfg["label"], why=cfg["why"],
                  n_scored=len(df), dropped=missing.geo_id.tolist(), tie_band=round(band, 4)),
        candidates=candidates, claims=claims, all_scores=all_scores)


def km_between(a: dict, b: dict) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a["latitude"], a["longitude"], b["latitude"], b["longitude"]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 12742 * math.asin(math.sqrt(h))
