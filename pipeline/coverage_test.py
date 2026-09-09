"""Held-out anchor coverage test (the experiment behind docs/VALIDATION.md).

For every eligible closed-final anchor in a pool: hide the eligible anchors
within a rank radius R, bracket the target from outside R only, and check
whether the true purchase count falls in the bracket. Offline: uses only the
shipped anchors + pool manifests.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bracket  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POOLS = ["pools/party_pool_nfl_wrapped.json",
         "pools/stormbreak_pool_nfl_wrapped.json",
         "pools/crown_pool_nfl_wrapped.json"]


def load_anchors():
    anchors = {}
    for l in open(os.path.join(ROOT, "anchors", "anchors_harden.jsonl")):
        rec = json.loads(l)
        if rec.get("item_id"):
            anchors[str(rec["item_id"])] = rec
    return anchors


def main():
    anchors = load_anchors()
    for rel in POOLS:
        ids = json.load(open(os.path.join(ROOT, rel)))["item_ids"]
        el_idx = [j for j, t in enumerate(ids)
                  if anchors.get(t) and bracket.anchor_eligible(anchors[t])[0]
                  and anchors[t]["purchased"] is not None]
        print(f"{rel}: {len(el_idx)} eligible of {len(ids)}")
        for R in (1, 2, 5, 10):
            n = cov = abst = 0
            widths = []
            for i in el_idx:
                near = [j for j in el_idx if j != i and abs(j - i) <= R]
                if not near:
                    continue
                hide = {ids[j] for j in near}
                sub = {k: v for k, v in anchors.items() if k not in hide}
                r = bracket.rank_bracket(ids, ids[i], sub)
                if r["status"] != "ESTIMATE":
                    abst += 1
                    continue
                lo, hi = r["bracket"]
                n += 1
                widths.append(hi / lo if lo else float("inf"))
                if lo <= anchors[ids[i]]["purchased"] <= hi:
                    cov += 1
            med = sorted(widths)[len(widths) // 2] if widths else 0
            print(f"  R={R}: n={n} abstain={abst} coverage={cov}/{n}"
                  f"={cov / n if n else 0:.0%} median_width={med:.2f}x")


if __name__ == "__main__":
    main()
