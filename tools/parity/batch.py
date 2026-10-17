"""Crawl every task in tasks.json that has no cap/<id>.json yet."""
import json
import sys
from pathlib import Path

import pm

here = Path(__file__).parent
only = set(sys.argv[1:])
for t in json.loads((here / "tasks.json").read_text()):
    if only and t["id"] not in only:
        continue
    if not only and (pm.CAP / f"{t['id']}.json").exists():
        continue
    try:
        pm.crawl(t["id"], t["pm"])
        print("ok", t["id"], flush=True)
    except Exception as e:  # keep going: one broken task must not stop the batch
        print("FAIL", t["id"], repr(e), flush=True)
