"""Merge the full re-scrape + delta re-parse into anchors/anchors_harden.jsonl.

Provenance rules (Astra 2.9):
- A replacement record WITHOUT its own rev_id/rev_timestamp is REJECTED, never
  dressed in the base record's provenance.
- Input paths are explicit (CLI args), no silent parent-directory fallback.
- Missing/empty inputs are a hard error: never publish an empty database.
- Output written atomically (tmp + rename); conflicting duplicate identities
  (same id, different counts) are refused.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "anchors", "anchors_harden.jsonl")


def load(p):
    d = {}
    if not os.path.exists(p):
        raise SystemExit(f"missing required input: {p} (refusing to merge partial data)")
    for n, l in enumerate(open(p), 1):
        l = l.strip()
        if not l:
            continue
        try:
            r = json.loads(l)
        except json.JSONDecodeError as e:
            raise SystemExit(f"{p}:{n}: malformed JSON: {e} (repair the tail, do not append)")
        t = r.get("title")
        if not t:
            continue
        prev = d.get(t)
        if prev and prev.get("purchased") != r.get("purchased"):
            raise SystemExit(f"{p}:{n}: conflicting duplicate identity for {t!r} "
                             f"({prev.get('purchased')} vs {r.get('purchased')}); resolve manually")
        d[t] = r
    if not d:
        raise SystemExit(f"{p}: zero usable rows; refusing to publish an empty database")
    return d


def main():
    # argv discipline (round-3 finding 5F): one arg = BASE-ONLY merge (no delta).
    # The old code fell through to default paths, silently ignoring the caller's
    # explicit base and merging whatever defaults existed.
    if len(sys.argv) == 2:
        base_path, delta_path = sys.argv[1], None
    elif len(sys.argv) >= 3:
        base_path, delta_path = sys.argv[1], sys.argv[2]
    else:
        # repo-internal artifacts only; NO parent-directory fallback (undeclared input)
        base_path = os.path.join(ROOT, "anchors_harden_rescrape.jsonl")
        delta_path = os.path.join(ROOT, "anchors_delta_parsed.jsonl")
        if not os.path.exists(base_path):
            raise SystemExit(f"missing {base_path}; pass paths explicitly: "
                             f"merge_anchors.py <base.jsonl> [delta.jsonl]")

    base = load(base_path)
    if os.path.exists(delta_path):
        delta = load(delta_path)
        replaced = 0
        for t, drec in delta.items():
            b = base.get(t)
            if b is None:
                base[t] = drec
                continue
            b_has = b.get("purchased") is not None or b.get("unpaired_purchased") is not None
            d_has = drec.get("purchased") is not None or drec.get("unpaired_purchased") is not None
            if d_has and not b_has:
                # provenance must be the REPLACEMENT's OWN (Astra 2.9): never inherit
                # the base record's rev_id - that would claim the new content came
                # from the old revision.
                if not drec.get("rev_id") or not drec.get("rev_timestamp"):
                    raise SystemExit(f"delta row {t!r} lacks its own rev provenance; rejected")
                base[t] = drec
                replaced += 1
        print(f"delta replaced: {replaced}")

    tmp = OUT + ".tmp"
    with open(tmp, "w") as f:
        for t in sorted(base):
            f.write(json.dumps(base[t]) + "\n")
    os.replace(tmp, OUT)  # atomic publication
    print(f"merged: {len(base)} anchors -> {OUT}")


if __name__ == "__main__":
    main()
