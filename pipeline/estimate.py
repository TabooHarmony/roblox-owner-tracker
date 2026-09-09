"""Regenerate estimates/estimates_v2.jsonl from pools/ + anchors/.
Deterministic: fixed target list, persisted pool manifests, hardened anchors.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bracket  # noqa: E402
import pool_manifest  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SNAPSHOT = "2026-09-09T00:00:00Z"

# target name -> (item_id, pool manifest)
TARGETS = {
    "Confetti Cannon (2010)": (34399428, "pools/confetti_pool_wrapped.json"),
    "Vicennial Party Hat": (133333938101155, "pools/party_pool_nfl_wrapped.json"),
    "Stormbreak Horns": (76479271580913, "pools/stormbreak_pool_nfl_wrapped.json"),
    "Rose Quartz Crown": (92137983874490, "pools/crown_pool_nfl_wrapped.json"),
}


def load_anchors():
    anchors = {}
    p = os.path.join(ROOT, "anchors", "anchors_harden.jsonl")
    for l in open(p):
        rec = json.loads(l)
        if rec.get("item_id"):
            anchors[str(rec["item_id"])] = rec
    return anchors


def main():
    anchors = load_anchors()
    out = []
    for name, (tid, pool_rel) in sorted(TARGETS.items()):
        blob = json.load(open(os.path.join(ROOT, pool_rel)))
        ids = blob["item_ids"]
        # Same gate as the CLI: an unprovable pool abstains, never estimates.
        errs = pool_manifest.validate(blob["manifest"])
        if errs:
            r = {"status": "ABSTAIN", "reason": "INVALID_POOL",
                 "detail": "; ".join(errs)}
        else:
            r = bracket.rank_bracket(ids, str(tid), anchors)
        # snapshot provenance comes from the manifest, not wall clock
        snap = blob["manifest"].get("finished_utc")
        row = {
            "schema": 2, "item": name, "item_id": tid,
            "snapshot_utc": snap, "pool": pool_rel, "status": r["status"],
        }
        if r["status"] == "ESTIMATE":
            row.update({
                "confidence": r["confidence"], "bracket": r["bracket"],
                "warnings": r["warnings"], "anchors": r["anchors"],
                "quantity": r["quantity"], "note": r["note"],
            })
        else:
            row["abstain_reason"] = r["reason"] + ": " + r.get("detail", "")
        out.append(row)
    dest = os.path.join(ROOT, "estimates", "estimates_v2.jsonl")
    with open(dest, "w") as f:
        for row in out:
            f.write(json.dumps(row) + "\n")
    for row in out:
        if row["status"] == "ESTIMATE":
            print(f"{row['item']}: {row['bracket']} ({row['confidence']})")
        else:
            print(f"{row['item']}: ABSTAIN {row['abstain_reason'][:80]}")


if __name__ == "__main__":
    main()
