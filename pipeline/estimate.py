"""Regenerate estimates/estimates_v2.jsonl from pools/ + anchors/.
Deterministic: fixed target list, persisted pool manifests, hardened anchors.
Uses the SAME serializer as the CLI (Astra 2.8): one schema, no drift.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bracket  # noqa: E402
import pool_manifest  # noqa: E402
from estimate_schema import dumps, row  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

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
        # typed identity (Astra 2.2): bundle records key separately from assets
        # so equal numeric ids cannot collide across namespaces.
        if rec.get("item_id"):
            et = "bundle" if "entity_type:bundle" in (rec.get("parse_notes") or []) else "asset"
            anchors[f"{et}:{rec['item_id']}"] = rec
            anchors[str(rec["item_id"])] = rec  # unprefixed alias for asset lookups
    return anchors


def estimate_target(name, tid, pool_rel, anchors):
    blob = json.load(open(os.path.join(ROOT, pool_rel)))
    ids = blob["item_ids"]
    # Same gate as the CLI: an unprovable pool abstains, never estimates.
    errs = pool_manifest.validate(blob["manifest"], blob.get("item_ids"))
    if errs:
        r = {"status": "ABSTAIN", "reason": "INVALID_POOL",
             "detail": "; ".join(errs)}
    else:
        r = bracket.rank_bracket(ids, str(tid), anchors)
    # snapshot provenance comes from the manifest, not wall clock
    snap = blob["manifest"].get("finished_utc")
    return row(name, tid, r, snapshot_utc=snap, pool=pool_rel,
               anchors_path=os.path.join(ROOT, "anchors", "anchors_harden.jsonl"))


def main():
    anchors = load_anchors()
    out = []
    for name, (tid, pool_rel) in sorted(TARGETS.items()):
        out.append(estimate_target(name, tid, pool_rel, anchors))
    dest = os.path.join(ROOT, "estimates", "estimates_v2.jsonl")
    tmp = dest + ".tmp"
    with open(tmp, "w") as f:
        for r in out:
            f.write(dumps(r) + "\n")
    os.replace(tmp, dest)  # atomic publication (Astra 2.9)
    for r in out:
        if r["status"] == "ESTIMATE":
            print(f"{r['item']}: {r['bracket']} ({r['confidence']})")
        else:
            print(f"{r['item']}: ABSTAIN {r['abstain_reason'][:80]}")


if __name__ == "__main__":
    main()
