"""estimate_cli.py — deterministic entry point.
Usage: python3 estimate_cli.py --item-id 92137983874490 --pool pools/crown_pool.json [--anchors anchors/anchors_harden.jsonl]
Exit 0 on ESTIMATE or ABSTAIN (both are valid results); nonzero only on internal error.
"""
import argparse, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bracket
from estimate_schema import row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--item-id", type=int, required=True)
    ap.add_argument("--pool", required=True)
    ap.add_argument("--anchors", default=os.path.join(os.path.dirname(__file__), "..", "anchors", "anchors_harden.jsonl"))
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    blob = json.load(open(args.pool))
    manifest, ids = blob["manifest"], blob["item_ids"]
    errs = __import__("pool_manifest").validate(manifest)
    if errs:
        result = {"status": "ABSTAIN", "reason": "INVALID_POOL", "detail": "; ".join(errs)}
    else:
        anchors = {}
        if os.path.exists(args.anchors):
            for l in open(args.anchors):
                try:
                    r = json.loads(l)
                    if r.get("item_id"):
                        anchors[str(r["item_id"])] = r
                except Exception:
                    pass
        result = bracket.rank_bracket(ids, args.item_id, anchors)

    out = row(f"id:{args.item_id}", args.item_id, result,
              snapshot_utc=manifest.get("finished_utc"), pool_manifest=args.pool)
    out["item"] = (anchors.get(str(args.item_id), {}).get("title") if result["status"] == "ESTIMATE" else out["item"]) or out["item"]
    text = json.dumps(out, indent=1)
    if args.out:
        open(args.out, "w").write(text + "\n")
    print(text)
    return 0

if __name__ == "__main__":
    sys.exit(main())
