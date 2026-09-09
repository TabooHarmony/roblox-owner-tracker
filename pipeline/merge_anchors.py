"""Merge the full re-scrape + delta re-parse into anchors/anchors_harden.jsonl.
Delta rows (parsed with the latest parser) replace base rows for the same title
when the base row lacks purchase info. Deterministic: title-keyed, delta wins
only on strict improvement (base has no purchase data, delta has some).
"""
import json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# dev-tree artifacts live one level above the repo checkout
BASE = os.path.join(ROOT, "..", "..", "anchors_harden_rescrape.jsonl")
DELTA = os.path.join(ROOT, "..", "..", "anchors_delta_parsed.jsonl")
OUT = os.path.join(ROOT, "anchors", "anchors_harden.jsonl")


def load(p):
    d = {}
    if not os.path.exists(p):
        return d
    for l in open(p):
        r = json.loads(l)
        d[r["title"]] = r
    return d


base = load(BASE)
if os.path.exists(DELTA):
    delta = load(DELTA)
    replaced = 0
    for t, drec in delta.items():
        b = base.get(t)
        if b is None:
            base[t] = drec
            continue
        b_has = b.get("purchased") is not None or b.get("unpaired_purchased") is not None
        d_has = drec.get("purchased") is not None or drec.get("unpaired_purchased") is not None
        if d_has and not b_has:
            # keep base provenance fields delta lacks
            drec.setdefault("rev_id", b.get("rev_id"))
            drec.setdefault("rev_timestamp", b.get("rev_timestamp"))
            base[t] = drec
            replaced += 1
    print(f"delta replaced: {replaced}")
with open(OUT, "w") as f:
    for t in sorted(base):
        f.write(json.dumps(base[t]) + "\n")
print(f"merged: {len(base)} anchors -> {OUT}")
