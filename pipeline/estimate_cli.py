"""estimate_cli.py — deterministic single-target entry point.
Usage: python3 estimate_cli.py --item-id 92137983874490 --pool pools/crown_pool_nfl_wrapped.json [--anchors anchors/anchors_harden.jsonl]
Exit 0 on ESTIMATE or ABSTAIN (both are valid results); nonzero only on internal error.
Emits the SAME canonical schema as the batch path (shared serializer, Astra 2.8).
"""
import argparse, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bracket
import pool_manifest
from estimate_schema import dumps, row


def load_anchors(path):
    anchors = {}
    if not os.path.exists(path):
        return anchors
    for l in open(path):
        try:
            r = json.loads(l)
        except Exception:
            continue  # malformed line: skip here; the merge gate is the enforcer
        # typed identity ONLY (Astra round-4 finding 3): no untyped plain-ID
        # aliases; a bundle record must never become asset evidence.
        if r.get("item_id"):
            et = "bundle" if "entity_type:bundle" in (r.get("parse_notes") or []) else "asset"
            anchors[f"{et}:{r['item_id']}"] = r
    return anchors


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--item-id", required=True)  # string: ids stay exact (int vs str bug is history)
    ap.add_argument("--entity-type", choices=["asset", "bundle"], default="asset")
    ap.add_argument("--pool", required=True)
    ap.add_argument("--anchors", default=os.path.join(os.path.dirname(__file__), "..", "anchors", "anchors_harden.jsonl"))
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    blob = json.load(open(args.pool))
    manifest, ids = blob["manifest"], blob["item_ids"]
    errs = pool_manifest.validate(manifest, blob.get("item_ids"))
    if errs:
        result = {"status": "ABSTAIN", "reason": "INVALID_POOL", "detail": "; ".join(errs)}
    else:
        anchors = load_anchors(args.anchors)
        result = bracket.rank_bracket(ids, str(args.item_id), anchors)

    out = row(f"id:{args.item_id}", args.item_id, result,
              snapshot_utc=manifest.get("finished_utc"), pool=args.pool,
              entity_type=args.entity_type, anchors_path=args.anchors)
    text = dumps(out, indent=1)
    if args.out:
        tmp = args.out + ".tmp"
        open(tmp, "w").write(text + "\n")
        os.replace(tmp, args.out)
    print(text)
    return 0

if __name__ == "__main__":
    sys.exit(main())
