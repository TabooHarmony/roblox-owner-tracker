"""Schema validation for anchors and estimates. Exit 1 on any violation.
No network, no LLM: pure structural checks over the shipped JSONL files.
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ANCHOR_REQUIRED = {
    "title": str, "item_id": (int, type(None)), "purchased": (int, type(None)),
    "purchased_as_of": (str, type(None)), "unpaired_purchased": (int, type(None)),
    "sale_state": (str,), "until": (str, type(None)),
    "until_history": list, "rev_id": int, "rev_timestamp": str, "parse_ok": bool,
}
ANCHOR_STATES = {"still_available", "closed", "unknown"}
DATE_RE = re.compile(r"^[A-Z][a-z]+ \d{1,2}, \d{4}$|^\d{1,2} [A-Z][a-z]+ \d{4}$", re.I)
ESTIMATE_REQUIRED = {
    "schema": int, "item": str, "item_id": int, "snapshot_utc": str,
    "pool": str, "status": str,
}
ESTIMATE_STATUS = {"ESTIMATE", "ABSTAIN"}
SNAPSHOT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
# sale_state != still_available requires a parseable until (the closure-date rule)


def validate_anchor(rec, errors):
    where = f"anchor {rec.get('title', '?')!r}"
    for k, typ in ANCHOR_REQUIRED.items():
        if k not in rec:
            errors.append(f"{where}: missing field {k}")
        elif not isinstance(rec[k], typ):
            errors.append(f"{where}: field {k} wrong type {type(rec[k]).__name__}")
    if rec.get("sale_state") not in ANCHOR_STATES:
        errors.append(f"{where}: bad sale_state {rec.get('sale_state')!r}")
    until = rec.get("until")
    if until is not None and not DATE_RE.match(until):
        errors.append(f"{where}: until not a date: {until!r}")
    if rec.get("sale_state") == "closed":
        if until is None:
            errors.append(f"{where}: closed but no until date (Astra #2 rule)")
        elif not DATE_RE.match(until):
            errors.append(f"{where}: closed until unparseable: {until!r}")
    if rec.get("purchased") is not None and rec.get("purchased_as_of") is None:
        errors.append(f"{where}: purchased without purchased_as_of (unpaired count)")
    if rec.get("rev_id") is None or rec.get("rev_timestamp") is None:
        errors.append(f"{where}: missing rev_id/rev_timestamp (provenance rule: the rev its "
                      "wikitext actually came from, never a backfilled current rev)")
    if rec.get("sale_state") == "closed" and rec.get("purchased") is not None:
        # Astra #2: a count observed before closure is not the final count.
        # Kept in the DB (honest record) but the engine rejects such anchors;
        # structural errors above are fatal, this one is reported and tolerated.
        u = rec.get("until"); a = rec.get("purchased_as_of")
        try:
            from bracket import parse_until
            ud, ad = parse_until(u or ""), parse_until(a or "")
            if ud and ad and ad < ud:
                print(f"WARNING: {where}: stale count (as_of {a} before until {u}) - "
                      "engine will reject as anchor")
        except ImportError:
            pass


def validate_estimate(rec, errors):
    where = f"estimate {rec.get('item', '?')!r}"
    for k, typ in ESTIMATE_REQUIRED.items():
        if k not in rec:
            errors.append(f"{where}: missing field {k}")
        elif not isinstance(rec[k], typ):
            errors.append(f"{where}: field {k} wrong type {type(rec[k]).__name__}")
    if not SNAPSHOT_RE.match(rec.get("snapshot_utc") or ""):
        errors.append(f"{where}: snapshot_utc not a UTC timestamp "
                      f"({rec.get('snapshot_utc')!r}; wall-clock fabrication forbidden)")
    if rec.get("status") not in ESTIMATE_STATUS:
        errors.append(f"{where}: bad status {rec.get('status')!r}")
    if rec.get("status") == "ABSTAIN" and not rec.get("abstain_reason"):
        errors.append(f"{where}: ABSTAIN without reason")
    if rec.get("status") == "ESTIMATE":
        for k in ("confidence", "bracket", "anchors"):
            if k not in rec:
                errors.append(f"{where}: ESTIMATE missing {k}")
        b = rec.get("bracket")
        if b and (not isinstance(b, list) or len(b) != 2
                  or not all(isinstance(x, int) for x in b) or b[0] > b[1]):
            errors.append(f"{where}: bad bracket {b!r}")
        a = rec.get("anchors") or {}
        for side in ("above", "below"):
            sa = a.get(side) or {}
            if sa.get("purchased") is None:
                errors.append(f"{where}: {side} anchor has no paired count")


def main():
    errors = []
    n_anchors = n_est = 0
    p = os.path.join(ROOT, "anchors", "anchors_harden.jsonl")
    if os.path.exists(p):
        for i, l in enumerate(open(p)):
            rec = json.loads(l)
            validate_anchor(rec, errors)
            n_anchors += 1
    else:
        errors.append(f"missing {p}")
    p = os.path.join(ROOT, "estimates", "estimates_v2.jsonl")
    if os.path.exists(p):
        for l in open(p):
            rec = json.loads(l)
            validate_estimate(rec, errors)
            n_est += 1
    else:
        errors.append(f"missing {p}")
    for e in errors[:20]:
        print("ERROR:", e)
    print(f"validated: {n_anchors} anchors, {n_est} estimates, {len(errors)} errors")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
