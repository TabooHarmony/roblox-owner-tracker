"""estimate_cli.py — deterministic single-target entry point.
Usage: python3 estimate_cli.py --item-id 92137983874490 --pool pools/crown_pool_nfl_wrapped.json [--anchors anchors/anchors_harden.jsonl]
Exit 0 on ESTIMATE or ABSTAIN (both are valid results); nonzero only on internal error.

v0 scope (reviewer directive): assets only, ONE estimation path, ONE loader.
This CLI is a thin argument-parser over estimate.py's run() — it does not
duplicate loading, validation, or serialization logic.
"""
import argparse, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import estimate  # single source of loaders, gates, and serializer


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--item-id", required=True)  # string: ids stay exact
    ap.add_argument("--pool", required=True)
    ap.add_argument("--anchors", default=os.path.join(os.path.dirname(__file__), "..", "anchors", "anchors_harden.jsonl"))
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    rows = estimate.run(anchors_path=os.path.abspath(args.anchors),
                        pools=[args.pool], out_path=None,
                        targets=[args.item_id])
    # single-target run: emit only the row for the requested id
    want = str(args.item_id)
    out = next((r for r in rows if str(r.get("item_id")) == want), None)
    if out is None:
        print(f"item {want} not produced by this pool run", file=sys.stderr)
        return 1
    text = estimate.dumps(out, indent=1)
    if args.out:
        tmp = args.out + ".tmp"
        open(tmp, "w").write(text + "\n")
        os.replace(tmp, args.out)
    print(text)
    return 0

if __name__ == "__main__":
    sys.exit(main())
