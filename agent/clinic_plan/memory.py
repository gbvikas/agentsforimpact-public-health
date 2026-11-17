"""Long-term memory across runs, kept as a small JSON file.

What it remembers:
  approved_config  which score_need weights a human has approved (the Planner cannot change it)
  visits           tracts the van was planned for in earlier months (so plans rotate)
  lessons          rules learned from past audits and human decisions

The Planner reads visits and lessons. Nothing demographic is ever written here: lessons are
built from flag codes and rule text, so memory cannot leak the Auditor's data into Context A.
"""
import json
import os
from datetime import datetime, timezone

STORE = os.environ.get("MEMORY_STORE",
                       os.path.join(os.path.dirname(__file__), "..", "memory_store.json"))

EMPTY = {"approved_config": "v0-blueprint", "config_history": [], "visits": [], "lessons": [],
         "pending_human_flags": []}


def load() -> dict:
    try:
        with open(STORE) as f:
            return {**EMPTY, **json.load(f)}
    except (FileNotFoundError, json.JSONDecodeError):
        return json.loads(json.dumps(EMPTY))


def save(mem: dict) -> None:
    with open(STORE, "w") as f:
        json.dump(mem, f, indent=2)


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def add_lesson(mem: dict, text: str, source: str) -> None:
    if not any(l["text"] == text for l in mem["lessons"]):
        mem["lessons"].append({"date": now(), "source": source, "text": text})


def approve_config(version: str, reason: str, approver: str = "outreach lead") -> dict:
    """Human action: switch the weights score_need uses on the next run."""
    mem = load()
    mem["config_history"].append({"date": now(), "from": mem["approved_config"], "to": version,
                                  "approver": approver, "reason": reason})
    mem["approved_config"] = version
    mem["pending_human_flags"] = []
    add_lesson(mem, f"A human replaced the score weights with config {version}: {reason}", "human")
    save(mem)
    return mem
