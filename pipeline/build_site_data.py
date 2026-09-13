#!/usr/bin/env python3
"""Build the site's anchor data from the wiki anchor database.

Reads anchors/anchors_harden.jsonl, emits:
  site/anchors_eligible.json      — { item_id: {p, as_of, until, t} } for every
                                    anchor that passes the eligibility gate
  site/rerelease_post2020.json    — { item_id: true } for anchors the gate
                                    excludes because of a post-2020 re-release
                                    (or a post-2020 close with a count observed
                                    before that close)

Both files are consumed by site/index.html. Run this whenever the anchor DB
changes.
"""
import json, re, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MONTHS = {m: i + 1 for i, m in enumerate(
    "january february march april may june july august september october november december".split())}
MONTHS.update({m[:3]: i + 1 for i, m in enumerate(
    "january february march april may june july august september october november december".split())})
MONTHS["sept"] = 9

def pdate(s):
    if not s:
        return None
    s = str(s).strip()
    m = (re.match(r"^([A-Za-z]+)\.?\s+(\d{1,2}),?\s+(\d{4})$", s)
         or re.match(r"^(\d{1,2})\s+([A-Za-z]+)\.?,?\s+(\d{4})$", s))
    if not m:
        return None
    if m.group(1).isdigit():
        d, mo, y = int(m.group(1)), MONTHS.get(m.group(2).lower()), int(m.group(3))
    else:
        mo, d, y = MONTHS.get(m.group(1).lower()), int(m.group(2)), int(m.group(3))
    return (y, mo, d) if mo else None

def main():
    rows = [json.loads(l) for l in open(os.path.join(ROOT, "anchors/anchors_harden.jsonl"))]
    denied = {}
    eligible = {}

    for r in rows:
        iid = str(r["item_id"])
        if r.get("parse_notes", []) and "entity_type:bundle" in r["parse_notes"]:
            continue
        wins = r.get("windows") or []
        # rule A: any non-first window from >= 2020 -> re-release
        reA = any((pdate(w.get("from")) or (0, 0, 0)) >= (2020, 1, 1)
                  for k, w in enumerate(wins) if k > 0)
        # rule B: closed on/after 2020 with a paired count observed before that close
        u = pdate(r.get("until")); a = pdate(r.get("purchased_as_of"))
        reB = (not reA) and u and u >= (2020, 1, 1) and r.get("purchased") is not None and a and a < u
        if reA or reB:
            denied[iid] = True
            continue

        p = r.get("purchased")
        if (r.get("sale_state") == "closed" and wins
                and all(w.get("state") == "resolved" for w in wins)
                and isinstance(p, int) and p >= 0
                and a and u and a > u and u[0] >= 2012
                and r.get("purchase_count_scope") == "single"):
            eligible[iid] = {"p": p, "as_of": r["purchased_as_of"],
                             "until": r["until"],
                             "t": (r.get("title") or "").replace("Catalog:", "")}

    # one-day branded-event false positives (Apr 18 2020 Adidas etc.)
    for fp in ("4906459532", "4906460384", "4906472016", "4906473211"):
        denied.pop(fp, None)

    with open(os.path.join(ROOT, "site/anchors_eligible.json"), "w") as f:
        json.dump(eligible, f, separators=(",", ":"))
    with open(os.path.join(ROOT, "site/rerelease_post2020.json"), "w") as f:
        json.dump(denied, f)

    print(f"eligible: {len(eligible)}  denied: {len(denied)}")

if __name__ == "__main__":
    main()
