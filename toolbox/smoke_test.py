"""Call every Toolbox tool once and check toolset isolation.

Usage: .venv/bin/python toolbox/smoke_test.py [http://127.0.0.1:5055]
"""
import asyncio
import json
import sys

from toolbox_core import ToolboxClient

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5055"
TRACT = "17031838800"


def show(name, out):
    rows = json.loads(out) if isinstance(out, str) and out.strip().startswith(("[", "{")) else out
    n = len(rows) if isinstance(rows, list) else 1
    first = rows[0] if isinstance(rows, list) and rows else rows
    print(f"OK  {name:<28} rows={n:<5} first={json.dumps(first)[:160]}")


async def main():
    async with ToolboxClient(URL) as client:
        planner = {t.__name__: t for t in await client.load_toolset("planner")}
        auditor = {t.__name__: t for t in await client.load_toolset("auditor")}
        print("planner tools:", sorted(planner))
        print("auditor tools:", sorted(auditor))
        leaked = [n for n in planner if n.startswith(("demographics", "data_trap"))]
        print("planner isolation:", "FAIL " + str(leaked) if leaked else "OK (no demographic tools)")

        calls = [
            (planner["tract_features"], dict(min_pop=500)),
            (planner["tract_detail"], dict(geo_ids=[TRACT, "17031460800"])),
            (planner["nearest_safety_net_sites"], dict(geo_id=TRACT, n=3)),
            (planner["tract_neighbors"], dict(geo_id=TRACT, n=5)),
            (planner["county_air_context"], {}),
            (planner["regional_respiratory_trend"], dict(weeks=4)),
            (auditor["demographics_for_tracts"], dict(geo_ids=[TRACT])),
            (auditor["demographics_baseline"], dict(county_fips="17031")),
            (auditor["data_trap_checks"], {}),
        ]
        for tool, args in calls:
            try:
                show(tool.__name__, await tool(**args))
            except Exception as e:  # report and keep going
                print(f"ERR {tool.__name__:<28} {str(e)[:300]}")


asyncio.run(main())
