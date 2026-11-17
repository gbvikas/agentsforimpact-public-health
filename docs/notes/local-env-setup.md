---
name: local-env-setup
description: Python env convention — always create a venv and install with pip3; venv lives at agentsforimpact-public-health/.venv
metadata:
  node_type: memory
  type: feedback
  originSessionId: e580f079-8de7-49f4-9f0f-bb27f2a97aee
  modified: 2026-11-17T19:07:09.885Z
---

Create a venv first, then install packages with `pip3` inside it (never global installs). Venv: `agentsforimpact-public-health/.venv` (machine has only Homebrew Python 3.15).

**Why:** the user explicitly asked for venv + pip3; the stack is Google ADK.
**How to apply:** use `.venv/bin/pip3 install ...` and `.venv/bin/python`; pin `google-adk==2.7.0` (see [[adk-api-gotchas]]).
