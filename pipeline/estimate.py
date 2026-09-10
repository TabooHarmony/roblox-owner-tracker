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


def load_anchors(path=None):
    """THE one anchor loader (v0 scope: assets only). Typed keys, no aliases.
    Bundle records are refused here — out of product scope — so they can never
    enter the evidence set through any entry point."""
    anchors = {}
    p = path or os.path.join(ROOT, "anchors", "anchors_harden.jsonl")
    for l in open(p):
        rec = json.loads(l)
        if not rec.get("item_id"):
            continue
        if "entity_type:bundle" in (rec.get("parse_notes") or []):
            continue  # bundles out of scope for the experimental release
        anchors[f"asset:{rec['item_id']}"] = rec
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


def run(anchors_path=None, pools=None, out_path=None, targets=None):
    """Programmatic entry over explicit paths (test/batch harness surface,
    and THE estimation path the CLI wraps). pools: list of pool-file paths;
    each must contain {"item_ids": [...], "manifest": {...}}. targets: optional
    list of item ids to estimate (default: the shipped target list)."""
    anchors = load_anchors(anchors_path)
    pool_files = pools or [p for _, p in sorted(TARGETS.items())]
    want = {str(t) for t in targets} if targets else None
    out = []
    for pf in pool_files:
        blob = json.load(open(pf))
        ids = blob["item_ids"]
        errs = pool_manifest.validate(blob["manifest"], ids)
        # target selection: explicit ids when given, else the shipped target
        # that this pool file was built for, else the pool's second entry.
        if want:
            tids = [t for t in ids if str(t) in want]
        else:
            tids = [tid for name, (tid, pr) in TARGETS.items()
                    if pr == pf and str(tid) in [str(x) for x in ids]]
            tids = tids or [ids[1] if len(ids) > 1 else ids[0]]
        for tid in tids:
            if errs:
                r = {"status": "ABSTAIN", "reason": "INVALID_POOL",
                     "detail": "; ".join(errs)}
            else:
                r = bracket.rank_bracket(ids, str(tid), anchors)
            snap = blob["manifest"].get("finished_utc")
            out.append(row(str(tid), tid, r, snapshot_utc=snap,
                           pool=os.path.abspath(pf),
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
            print(f"{r['item']}: {r['bracket']}")
        else:
            print(f"{r['item']}: ABSTAIN {r['abstain_reason'][:80]}")


if __name__ == "__main__":
    main()
