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
    if delta_path is not None:
        if not os.path.exists(delta_path):
            raise SystemExit(f"missing required input: {delta_path} "
                             f"(explicitly supplied delta is never silently skipped)")
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
    n_ok = n_refused = 0
    refused_path = os.path.join(os.path.dirname(OUT), "anchors_refused.jsonl")
    tmp_refused = refused_path + ".tmp"
    # Round-4 finding 6: the two zero-sales disagreements were adjudicated
    # against the LIVE economy API (Sales=0 there too): the wiki counts are
    # unsupported. The adjudication is an explicit, committed file; any anchor
    # listed as wiki_value_erroneous is refused at the merge boundary, so the
    # refusal policy is implemented, not just narrated in the ledger.
    adj_path = os.path.join(ROOT, "docs", "zero_sales_adjudications.json")
    erroneous = set()
    if os.path.exists(adj_path):
        with open(adj_path) as af:
            for k, v in json.load(af).get("adjudications", {}).items():
                if v.get("adjudication") == "wiki_value_erroneous":
                    erroneous.add(k)
    with open(tmp, "w") as f, open(tmp_refused, "w") as g:
        for t in sorted(base):
            r = base[t]
            typed_key = ('bundle' if "entity_type:bundle" in (r.get("parse_notes") or [])
                         else 'asset') + f":{r.get('item_id')}"
            if typed_key in erroneous:
                r = dict(r)
                r["parse_ok"] = False
                r["parse_notes"] = list(r.get("parse_notes") or []) + [
                    f"adjudicated_wiki_value_erroneous ({typed_key}: live economy API "
                    f"reports Sales=0; wiki count unsupported - see "
                    f"docs/zero_sales_adjudications.json)"]
            # Parse-quality gate AT THE MERGE BOUNDARY (Astra round-3 finding 1):
            # failed parses are never shipped as anchors; they are archived with
            # full notes so the refusal itself is auditable.
            if r.get("parse_ok") is True:
                f.write(json.dumps(r) + "\n")
                n_ok += 1
            else:
                g.write(json.dumps(r) + "\n")
                n_refused += 1
    os.replace(tmp, OUT)        # atomic publication
    os.replace(tmp_refused, refused_path)
    print(f"merged: {n_ok} anchors -> {OUT}; refused (archived): {n_refused} -> {refused_path}")


if __name__ == "__main__":
    main()
