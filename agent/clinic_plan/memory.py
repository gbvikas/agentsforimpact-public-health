"""EquiVita long-term memory: an append-only event log, replayed into a summary on read.

Events (kind -> payload):
  visit           {"month", "geo_id", "saturday"}         tracts the van was planned for
  lesson          {"source", "text"}                      rules learned from audits / human decisions
  config_change   {"from", "to", "approver", "reason"}    human approved new score_need weights
  decision        {"approver", "accepted_flags", "reason"} human accepted a plan with open flags
  field_report    {"geo_id", "turnout", "barriers", ...}   nurse debrief, place-level only
  pending_flags   {"flags": [...]}                        human-routed flags awaiting a decision
  reset           {}                                      everything before this is ignored

The Planner reads visits and lessons. Nothing demographic is ever written: lessons are built from
flag codes and rule text, so memory cannot leak the Auditor's data into the Planner's context.

Backends are swappable behind the same two calls (events(), append()):
  bigquery (default) - table <project>.a4i_health.agent_memory, the same governed store as the data
  file               - a local JSON file, for offline development
A low-latency store (Cloud SQL MySQL, Firestore) would be one more backend class.
"""
import json
import os
from datetime import datetime, timezone

from .scoring import canonical_config

BACKEND = os.environ.get("MEMORY_BACKEND", "bigquery")
DEFAULT_CONFIG = "distance-first"
EMPTY = {"approved_config": DEFAULT_CONFIG, "config_history": [], "visits": [], "lessons": [],
         "decisions": [], "pending_human_flags": [], "field_reports": [], "backend": BACKEND}


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


class FileBackend:
    def __init__(self):
        self.path = os.environ.get("MEMORY_STORE",
                                   os.path.join(os.path.dirname(__file__), "..", "memory_events.json"))

    def events(self) -> list[dict]:
        try:
            with open(self.path) as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def append(self, rows: list[dict]) -> None:
        evs = self.events()
        with open(self.path, "w") as f:
            json.dump(evs + rows, f, indent=2)


class BigQueryBackend:
    def __init__(self):
        from google.cloud import bigquery
        self.bq = bigquery
        project = os.environ.get("GOOGLE_CLOUD_PROJECT")
        self.table = os.environ.get("MEMORY_TABLE", f"{project}.a4i_health.agent_memory")
        self.client = bigquery.Client(project=project)

    def events(self) -> list[dict]:
        rows = self.client.query(
            f"SELECT ts, run_id, kind, TO_JSON_STRING(payload) AS payload FROM `{self.table}` ORDER BY ts, seq"
        ).result()
        return [{"ts": r.ts.strftime("%Y-%m-%d %H:%M UTC"), "run_id": r.run_id, "kind": r.kind,
                 "payload": json.loads(r.payload) if r.payload else {}} for r in rows]

    def append(self, rows: list[dict]) -> None:
        if not rows:
            return
        p = self.bq.ArrayQueryParameter
        self.client.query(
            f"""INSERT INTO `{self.table}` (ts, seq, run_id, kind, payload)
                SELECT CURRENT_TIMESTAMP(), off, @run_id, kind, PARSE_JSON(@payloads[OFFSET(off)])
                FROM UNNEST(@kinds) AS kind WITH OFFSET off""",
            job_config=self.bq.QueryJobConfig(query_parameters=[
                self.bq.ScalarQueryParameter("run_id", "STRING", rows[0].get("run_id")),
                p("kinds", "STRING", [r["kind"] for r in rows]),
                p("payloads", "STRING", [json.dumps(r["payload"]) for r in rows]),
            ])).result()


_backend = None


def backend():
    global _backend
    if _backend is None:
        _backend = BigQueryBackend() if BACKEND == "bigquery" else FileBackend()
    return _backend


def _replay(events: list[dict]) -> dict:
    mem = json.loads(json.dumps(EMPTY))
    for e in events:
        k, p, ts = e["kind"], e.get("payload") or {}, e.get("ts", "")
        if k == "reset":
            mem = json.loads(json.dumps(EMPTY))
        elif k == "visit":
            mem["visits"].append({**p, "date": ts})
        elif k == "lesson":
            if not any(l["text"] == p.get("text") for l in mem["lessons"]):
                mem["lessons"].append({"date": ts, "source": p.get("source"), "text": p.get("text")})
        elif k == "config_change":
            p = {**p, **{k: canonical_config(p[k]) for k in ("from", "to") if p.get(k)}}
            mem["config_history"].append({**p, "date": ts})
            mem["approved_config"] = p.get("to", mem["approved_config"])
        elif k == "decision":
            mem["decisions"].append({**p, "date": ts})
        elif k == "field_report":
            mem["field_reports"].append({**p, "date": ts})
        elif k == "pending_flags":
            mem["pending_human_flags"] = p.get("flags", [])
    mem["event_count"] = len(events)
    return mem


def load() -> dict:
    return _replay(backend().events())


def append(rows: list[dict]) -> None:
    """rows: [{"kind": ..., "payload": {...}, "run_id": optional}]"""
    backend().append(rows)


def lesson(text: str, source: str) -> dict:
    return {"kind": "lesson", "payload": {"source": source, "text": text}}


def reset() -> dict:
    append([{"kind": "reset", "payload": {"by": "outreach lead"}}])
    return load()


def acknowledge_flags(reason: str, approver: str = "outreach lead") -> dict:
    """Human action: accept the plan with its open human-routed flags. The reason stays in the
    decision log; the Planner's lesson carries no demographic detail."""
    codes = sorted({f["code"] for f in load().get("pending_human_flags", [])})
    append([{"kind": "decision", "payload": {"approver": approver, "accepted_flags": codes, "reason": reason}},
            lesson(f"A human accepted a plan with open flag(s) {', '.join(codes) or 'none'} and kept the "
                   f"current weights; the decision is logged for the funder report.", "human"),
            {"kind": "pending_flags", "payload": {"flags": []}}])
    return load()


def approve_config(version: str, reason: str, approver: str = "outreach lead") -> dict:
    """Human action: switch the weights score_need uses on the next run."""
    version = canonical_config(version)
    current = load()["approved_config"]
    append([{"kind": "config_change", "payload": {"from": current, "to": version, "approver": approver,
                                                 "reason": reason}},
            lesson(f"A human replaced the score weights with config {version}: {reason}", "human"),
            {"kind": "pending_flags", "payload": {"flags": []}}])
    return load()
