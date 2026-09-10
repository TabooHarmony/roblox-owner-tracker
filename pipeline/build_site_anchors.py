#!/usr/bin/env python3
"""Build site/anchors_compact.json — the browser-side anchor DB.

The full anchors_harden.jsonl is 9.4 MB; the browser only needs eligibility
fields per anchor plus which pool file contains its ranking. This script is
THE compact step: it drops nothing that eligibility needs and adds nothing
that isn't in the hardened DB (no synthesis — provenance preserved).
"""
import json, os, glob

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# which pool file each item_id appears in (first hit wins; membership is what
# matters — rank_bracket refuses ambiguous duplicates anyway)
pool_of = {}
for pf in sorted(glob.glob(os.path.join(ROOT, "pools", "*_wrapped.json"))):
    blob = json.load(open(pf))
    rel = "pools/" + os.path.basename(pf)
    for i in blob["item_ids"]:
        pool_of.setdefault(str(i), rel)

out = {}
n_in = n_kept = 0
with open(os.path.join(ROOT, "anchors", "anchors_harden.jsonl")) as f:
    for line in f:
        n_in += 1
        rec = json.loads(line)
        if not rec.get("item_id"):
            continue
        key = "asset:%d" % rec["item_id"]
        compact = {
            "purchased": rec.get("purchased"),
            "purchased_as_of": rec.get("purchased_as_of"),
            "unpaired_purchased": rec.get("unpaired_purchased"),
            "sale_state": rec.get("sale_state"),
            "until": rec.get("until"),
            "windows": [{"index": w.get("index"), "until": w.get("until"),
                         "state": w.get("state")} for w in (rec.get("windows") or [])],
            "parse_ok": rec.get("parse_ok"),
            "parse_notes": rec.get("parse_notes") or [],
            "purchase_count_scope": rec.get("purchase_count_scope"),
            "title": rec.get("title"),
        }
        if str(rec["item_id"]) in pool_of:
            compact["pool"] = pool_of[str(rec["item_id"])]
        out[key] = compact
        n_kept += 1

dst = os.path.join(ROOT, "site", "anchors_compact.json")
with open(dst, "w") as f:
    json.dump(out, f, separators=(",", ":"))
print("in=%d kept=%d out=%s (%.2f MB)" % (n_in, n_kept, dst, os.path.getsize(dst) / 1e6))
