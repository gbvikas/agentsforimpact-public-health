---
name: adk-api-gotchas
description: "Google ADK 2.7.0 Workflow API shape and the five verified pitfalls (timeout, schemas, JSON input, output_key clobbering, {key?})"
metadata:
  node_type: memory
  type: reference
  originSessionId: e580f079-8de7-49f4-9f0f-bb27f2a97aee
  modified: 2026-11-17T19:07:07.175Z
---

Organizer-verified against `google-adk==2.7.0` (PyPI later had 2.11.0; imports still worked). Pin 2.7.0. Source: `agentsforimpact-public-health/agent/README.md` and notebook §13. Docs: https://adk.dev/ , https://adk.dev/workflows/

- `SequentialAgent`/`ParallelAgent`/`LoopAgent` work but are deprecated in favor of graph `Workflow` (`from google.adk import Workflow, Event`; `from google.adk.workflow import node, START`; `@node async def f(ctx: Context)`). Workflow CANNOT be a sub-agent of an LlmAgent, but it can be a tool: `LlmAgent(tools=[plan_graph])`. Using the deprecated classes is fine.
- Cycle with no `timeout` runs forever (no max-iterations field on Workflow). Plan→audit→revise IS a cycle → always set `timeout=`. `LoopAgent` has `max_iterations`.
- Workflow as tool needs both `description` and `input_schema` (Pydantic).
- Schema'd workflow takes a JSON STRING: `run_debug('{"county": "Fulton"}')`, not a dict.
- Parallel branches share ONE state dict → each needs a distinct `output_key` or they silently clobber.
- Missing `{key}` in an instruction = hard KeyError; use `{key?}` for optional.
- Debug: `InMemoryRunner(agent=root_agent, plugins=[LoggingPlugin()])` + `await runner.run_debug(..., verbose=True)` (shows token usage). `adk web` State tab + event graph shows which agent wrote what. Cloud Shell: `adk web --host 0.0.0.0 --port 8080`.

See [[challenge-core]], [[local-env-setup]].
