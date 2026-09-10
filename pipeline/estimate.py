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
        # typed identity ONLY (Astra round-4 finding 3): no untyped plain-ID
        # aliases. A bundle alias must never become asset evidence via key
        # fallback; every lookup preserves the entity type.
        if rec.get("item_id"):
            et = "bundle" if "entity_type:bundle" in (rec.get("parse_notes") or []) else "asset"
            anchors[f"{et}:{rec['item_id']}"] = rec
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


def run(anchors_path=None, pools=None, out_path=None):
    """Programmatic entry over explicit paths (test/batch harness surface).
    pools: list of pool-file paths; each must contain {"item_ids": [...],
    "manifest": {...}} like the shipped wrapped pools. Returns row dicts."""
    import estimate_schema
    if anchors_path is None:
        anchors = load_anchors()
    else:
        anchors = {}
        for l in open(anchors_path):
            rec = json.loads(l)
            # typed identity ONLY (Astra round-4 finding 3): no untyped
            # plain-ID aliases; entity type must survive every lookup.
            et = rec.get("entity_type", "asset")
            anchors[f"{et}:{rec['item_id']}"] = rec
    pool_files = pools or [p for _, p in sorted(TARGETS.items())]
    out = []
    for pf in pool_files:
        blob = json.load(open(pf))
        ids = blob["item_ids"]
        errs = pool_manifest.validate(blob["manifest"], ids)
        if errs:
            r = {"status": "ABSTAIN", "reason": "INVALID_POOL",
                 "detail": "; ".join(errs)}
        else:
            r = bracket.rank_bracket(ids, str(ids[1] if len(ids) > 1 else ids[0]),
                                     anchors)
        snap = blob["manifest"].get("finished_utc")
        out.append(row(os.path.basename(pf), ids[1] if len(ids) > 1 else ids[0],
                       r, snapshot_utc=snap, pool=os.path.abspath(pf),
                       anchors_path=anchors_path or os.path.join(
                           ROOT, "anchors", "anchors_harden.jsonl")))
    if out_path is not None:
        tmp = out_path + ".tmp"
        with open(tmp, "w") as f:
            for r in out:
                f.write(dumps(r) + "\n")
        os.replace(tmp, out_path)
    return out


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
