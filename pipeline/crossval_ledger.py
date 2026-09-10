"""Cross-validation against an independent reference dump.

Commits the FULL evidence chain Astra round-3 required (finding 4):
- pinned reference input (sha256 of the dump file),
- full flow ledger: reference rows -> unique typed identities -> wiki matches ->
  available observations -> parseable records -> temporally comparable records ->
  eligible records -> agreements / disagreements / unresolved,
- per-row disposition for every disagreement (including "dump-side zero"
  adjudication fields: MUST be filled by a human, never auto-dismissed),
- first wiki revision containing the tested count (upstream-independence
  evidence), recorded from the harvest metadata (rev_id of the matched count).

Usage:
  python3 crossval_ledger.py <anchors.jsonl> <dump.json> <out_ledger.jsonl> <out_summary.json>

The script NEVER mutates data; it only measures and reports.
"""
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "pipeline"))
from bracket import anchor_eligible  # noqa: E402


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def typed(entity_type, item_id):
    return f"{entity_type}:{item_id}"


def load_dump(path):
    blob = json.load(open(path))
    rows = blob["item"] if isinstance(blob, dict) else blob
    out = {}
    for r in rows:
        # dump types: 'Asset'/'Bundle' (capitalized) -> typed namespace
        etype = {"Asset": "asset", "Bundle": "bundle"}.get(r.get("type"), "asset")
        out[typed(etype, r["id"])] = r
    return out


def main():
    anchors_path, dump_path, ledger_out, summary_out = sys.argv[1:5]
    flow = {
        "reference_rows": 0,
        "reference_unique_typed": 0,
        "wiki_matches": 0,
        "available_observations": 0,
        "parseable_records": 0,
        "temporally_comparable": 0,
        "eligible_records": 0,
        "agreements": 0,
        "disagreements": 0,
        "unresolved": 0,
    }
    ledger = []
    anchors = {}
    for line in open(anchors_path):
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        anchors[typed(rec.get("entity_type", "asset"), rec["item_id"])] = rec

    dump = load_dump(dump_path)
    flow["reference_rows"] = len(dump)

    for tkey, drow in sorted(dump.items()):
        rec = anchors.get(tkey)
        entry = {
            "typed_id": tkey,
            "title": rec.get("title") if rec else drow.get("name"),
            "dump_sales": drow.get("sales"),
            "wiki_purchased": rec.get("purchased") if rec else None,
            "wiki_as_of": rec.get("purchased_as_of") if rec else None,
            "wiki_until": rec.get("until") if rec else None,
            "wiki_rev_id": rec.get("rev_id") if rec else None,
            "wiki_rev_timestamp": rec.get("rev_timestamp") if rec else None,
            "disposition": None,
            "zero_adjudication": None,
        }
        flow["reference_unique_typed"] += 1
        if rec is None:
            entry["disposition"] = "no_wiki_match"
            flow["unresolved"] += 1
            ledger.append(entry)
            continue
        flow["wiki_matches"] += 1
        if rec.get("purchased") is None and rec.get("unpaired_purchased") is None:
            entry["disposition"] = "no_available_observation"
            flow["unresolved"] += 1
            ledger.append(entry)
            continue
        flow["available_observations"] += 1
        if rec.get("parse_ok") is not True:
            entry["disposition"] = "unparseable_record"
            flow["unresolved"] += 1
            ledger.append(entry)
            continue
        flow["parseable_records"] += 1
        # temporal comparability: the wiki observation must predate the dump
        # collection window for the count to be expected comparable. The dump
        # vintage is NOT assumed here; both dates travel in the ledger and the
        # comparable-window cutoff is an explicit CLI-injected constant, never
        # an undocumented guess.
        cutoff = os.environ.get("DUMP_VINTAGE_CUTOFF")  # e.g. "2023-01-01"
        as_of = rec.get("purchased_as_of") or ""
        if cutoff and as_of and as_of >= cutoff:
            entry["disposition"] = "not_temporally_comparable"
            flow["unresolved"] += 1
            ledger.append(entry)
            continue
        flow["temporally_comparable"] += 1
        ok, why = anchor_eligible(rec)
        if not ok:
            entry["disposition"] = f"ineligible_anchor:{why}"
            flow["unresolved"] += 1
            ledger.append(entry)
            continue
        flow["eligible_records"] += 1
        d_sales = drow.get("sales")
        w_pur = rec.get("purchased")
        if d_sales == w_pur:
            entry["disposition"] = "agree"
            flow["agreements"] += 1
        elif d_sales == 0 and (w_pur or 0) > 0:
            entry["disposition"] = "disagree_dump_zero"
            entry["zero_adjudication"] = "PENDING HUMAN ADJUDICATION"
            flow["disagreements"] += 1
        else:
            entry["disposition"] = "disagree"
            flow["disagreements"] += 1
        ledger.append(entry)

    summary = {
        "anchors_file": os.path.abspath(anchors_path),
        "anchors_sha256": sha256_file(anchors_path),
        "dump_file": os.path.abspath(dump_path),
        "dump_sha256": sha256_file(dump_path),
        "dump_vintage_cutoff_env": os.environ.get("DUMP_VINTAGE_CUTOFF"),
        "flow": flow,
    }
    with open(ledger_out, "w") as f:
        for entry in ledger:
            f.write(json.dumps(entry, sort_keys=True) + "\n")
    with open(summary_out, "w") as f:
        json.dump(summary, f, indent=2, sort_keys=True)
    print(json.dumps(summary["flow"], indent=2))


if __name__ == "__main__":
    main()
