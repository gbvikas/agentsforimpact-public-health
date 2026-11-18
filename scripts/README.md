# scripts/

| Script | What it does |
|---|---|
| `load.sh <county FIPS>` | Headless data load from the organizers' snapshot (same tables as the notebook). EquiVita uses `bash scripts/load.sh 17031` (Cook County). Safe to rerun; tables are replaced |
| `profile_data.py` | Profiles `a4i_health`: keys, join coverage, nulls, p90/p10 spread per feature, Spearman correlations |
| `score_variants.py` | Compares need-score formulas, picks 4 spaced stops, and audits each against Census race data |
| `outreach_demo.py [run_id]` | Prints the outreach card for each stop of a saved run |

Python scripts use the repo venv (`.venv/bin/python scripts/<name>.py`) and gcloud credentials.
Type the county FIPS with its leading zero where it has one (`06085`, not `6085`).
