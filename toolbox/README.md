# MCP Toolbox: the query layer for clinic_plan

`tools.yaml` defines every BigQuery lookup the agents can make, as fixed, parameterized SQL.
Agents call tools by name; they never write SQL.

## Run locally

```bash
# one-time: download the server binary (macOS arm64; swap darwin/arm64 for linux/amd64 in Cloud Shell)
curl -L -o toolbox/bin/toolbox https://storage.googleapis.com/mcp-toolbox-for-databases/v1.17.0/darwin/arm64/toolbox
chmod +x toolbox/bin/toolbox

# credentials: application-default credentials (gcloud auth application-default login),
# or point at the gcloud login's copy:
export GOOGLE_APPLICATION_CREDENTIALS=$(ls ~/.config/gcloud/legacy_credentials/*/adc.json)
export A4I_PROJECT=qwiklabs-gcp-03-1a6edb739e38

toolbox/bin/toolbox --config toolbox/tools.yaml --port 5055
.venv/bin/python toolbox/smoke_test.py          # calls all 9 tools, checks isolation
```

## Tools and who can call them

| Tool | Scale | planner (code lookups) | planner_drilldown (Planner agent) | auditor |
|---|---|:-:|:-:|:-:|
| `tract_features(min_pop)` | tract | ✅ | | |
| `tract_detail(geo_ids[])` | tract | ✅ | ✅ | ✅ |
| `nearest_safety_net_sites(geo_id, n)` | facility point | ✅ | ✅ | |
| `tract_neighbors(geo_id, n)` | tract | ✅ | ✅ | |
| `county_air_context()` | county | ✅ | ✅ | ✅ |
| `regional_respiratory_trend(weeks)` | health service area | ✅ | ✅ | ✅ |
| `demographics_for_tracts(geo_ids[])` | tract | | | ✅ |
| `demographics_baseline(county_fips)` | county | | | ✅ |
| `data_trap_checks()` | mixed | | | ✅ |

Tract tools return a plain-English `label` (from `a4i_health.tract_labels`). Load per agent with `ToolboxToolset(server_url=..., toolset_name="planner")` from `toolbox-adk`.
The planner's toolset has no demographic tool, so it cannot request race or ethnicity at all.

## Gotcha

Do not set `readOnly: true` on the BigQuery source: Toolbox 1.17 then suppresses every
`bigquery-sql` tool ("Suppressing write-capable tool ... bound to read-only source").

## Deployed

Toolbox runs as a private Cloud Run service (`clinic-toolbox`), with `tools.yaml` stored in Secret Manager
(`toolbox-tools`). After editing `tools.yaml`: `gcloud secrets versions add toolbox-tools --data-file=toolbox/tools.yaml`,
then redeploy the service so it reads the new version.
