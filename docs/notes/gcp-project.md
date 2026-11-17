---
name: gcp-project
description: "Team's Qwiklabs GCP project + BigQuery dataset ID, GitHub identity for pushes, and the data profiling script"
metadata:
  node_type: memory
  type: reference
  originSessionId: e580f079-8de7-49f4-9f0f-bb27f2a97aee
  modified: 2026-11-17T20:09:59.914Z
---

- BigQuery dataset: `qwiklabs-gcp-03-1a6edb739e38.a4i_health` (team's Qwiklabs project; tables already loaded).
- Local machine needs `gcloud auth login` + `gcloud auth application-default login` with the lab's student account before Python/bq can query.
- Profiling: `.venv/bin/python scripts/profile_data.py` (keys, join coverage, nulls, p90/p10 spread, Spearman correlations).
- GitHub: team repo `gbvikas/agentsforimpact-public-health`; push as `shahakshay11` (repo-local git user.name/email set; remote URL includes the username). Notes live on branch `notes` under `docs/notes/`.

See [[data-traps]], [[local-env-setup]].
