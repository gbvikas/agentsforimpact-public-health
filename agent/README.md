# agent/: the EquiVita ADK package

`clinic_plan/` is a Google ADK app. `root_agent` in `agent.py` is the planning workflow; `field_report.py`
defines the separate field-report flow.

| File | What it holds |
|---|---|
| `agent.py` | The workflow and the LLM agents: `planner`, `auditor`, `explainer`, `outreach_reasoner` (prompts included) |
| `steps.py` | Deterministic steps (`recall_memory`, lookups, `score_need` wrapper, `audit_gate`, `finalize_plan`, `limits_and_persist`) and the tools `check_plan` (auditor) and `stop_distances` (planner) |
| `scoring.py` | `score_need`: versioned weights (`distance-first`, `need-first`), tie bands, claims |
| `outreach.py` | `plan_channels` (code picks channels from tract data, finds Overture places) and `check_outreach` |
| `field_report.py` | `field_reporter` agent + code privacy gate; turns field reports into planner notes and claims |
| `memory.py` | Append-only memory events in BigQuery (`MEMORY_BACKEND=bigquery`, default) or a local file |
| `toolbox_bridge.py` | Calls MCP Toolbox from code steps; adds an identity token when Toolbox is a private Cloud Run service |

Run once from the command line: `.venv/bin/python agent/run_once.py`. Developer view: `adk web agent`.
Configuration lives in `clinic_plan/.env` (copy `.env.example`). Local runs should set `MEMORY_TABLE` to
`a4i_health.agent_memory_dev` so they don't change the live app's memory.

ADK API notes from the challenge (Workflow pitfalls, `output_key` clobbering, etc.):
[docs/challenge-agent-notes.md](../docs/challenge-agent-notes.md).
