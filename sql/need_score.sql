-- "Needs the van" score, v0. One row per census tract, ranked.
-- Dataset placeholder: replace `DATASET` (e.g. qwiklabs-gcp-03-1a6edb739e38.a4i_health).
--
-- All inputs are tract-level. Every component is a within-county percentile rank (0-1),
-- so features on different units are comparable and the weights read as shares.
--
--   need     (0.5) = mean of  uninsured 18-64 (PLACES, modeled)
--                             chronic burden = mean pctile of diabetes, high BP, COPD (PLACES, modeled;
--                             these three correlate 0.88-0.91 in Cook, so they get ONE vote)
--   barrier  (0.4) = mean of  no-vehicle households (SVI/ACS, survey)
--                             car-less distance = km_to_safety_net x share with no vehicle
--                             (distance only counts for people without a car; raw distance
--                             correlates -0.65 with no-vehicle in Cook and would favour suburbs)
--   shortage (0.1) = max HPSA_SCORE on the tract, scaled 0-1; 0 when not designated
--
-- Deliberately excluded from the score: PM2.5 (12 km grid, 1.06x spread), disease_weekly
-- (multi-county region), pct_checkup (1.14x spread, age-confounded), pct_lack_transport
-- (0.83 corr with uninsured), svi_socioeconomic (0.85 corr with uninsured), race (audit only).

WITH base AS (
  SELECT b.geo_id, b.total_pop, b.latitude, b.longitude,
         b.pct_uninsured, b.pct_diabetes, b.pct_high_bp, b.pct_copd, b.pct_no_vehicle,
         b.pct_limited_english, b.pct_age_65_plus,
         a.km_to_any_care, a.km_to_safety_net,
         a.km_to_safety_net * b.pct_no_vehicle / 100 AS carless_km
  FROM `DATASET.burden_tracts` b
  JOIN `DATASET.tract_access` a USING (geo_id)
  WHERE b.total_pop >= 500                       -- skip near-empty tracts (parks, airports)
),
hpsa AS (
  SELECT GEO_ID AS geo_id, MAX(HPSA_SCORE) AS hpsa_score, COUNT(*) AS n_designations
  FROM `DATASET.shortage_areas` GROUP BY 1
),
ranked AS (
  SELECT base.*, hpsa.hpsa_score,
         PERCENT_RANK() OVER (ORDER BY pct_uninsured)  AS pr_uninsured,
         PERCENT_RANK() OVER (ORDER BY pct_diabetes)   AS pr_diabetes,
         PERCENT_RANK() OVER (ORDER BY pct_high_bp)    AS pr_high_bp,
         PERCENT_RANK() OVER (ORDER BY pct_copd)       AS pr_copd,
         PERCENT_RANK() OVER (ORDER BY pct_no_vehicle) AS pr_no_vehicle,
         PERCENT_RANK() OVER (ORDER BY carless_km)     AS pr_carless_km,
         PERCENT_RANK() OVER (ORDER BY km_to_safety_net) AS pr_km
  FROM base LEFT JOIN hpsa USING (geo_id)
),
scored AS (
  SELECT *,
         (pr_uninsured + (pr_diabetes + pr_high_bp + pr_copd) / 3) / 2 AS need,
         (pr_no_vehicle + pr_carless_km) / 2                         AS barrier,
         IFNULL((hpsa_score - 10) / 15, 0)                           AS shortage
  FROM ranked
)
SELECT RANK() OVER (ORDER BY 0.5 * need + 0.4 * barrier + 0.1 * shortage DESC) AS rnk,
       geo_id, total_pop,
       ROUND(0.5 * need + 0.4 * barrier + 0.1 * shortage, 3) AS score,
       ROUND(need, 2) AS need, ROUND(barrier, 2) AS barrier, hpsa_score,
       pct_uninsured, pct_diabetes, pct_no_vehicle, km_to_safety_net,
       ROUND(carless_km, 2) AS carless_km, pct_limited_english,
       RANK() OVER (ORDER BY km_to_safety_net DESC) AS rank_distance_only,
       latitude, longitude
FROM scored
ORDER BY rnk
