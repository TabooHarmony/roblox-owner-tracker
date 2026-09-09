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
    "until_history": list, "rev_id": int, "parse_ok": bool,
}
ANCHOR_STATES = {"still_available", "closed", "unknown"}
DATE_RE = re.compile(r"^[A-Z][a-z]+ \d{1,2}, \d{4}$|^\d{1,2} [A-Z][a-z]+ \d{4}$", re.I)
ESTIMATE_REQUIRED = {
    "schema": int, "item": str, "item_id": int, "snapshot_utc": str,
    "pool": str, "status": str,
}
ESTIMATE_STATUS = {"ESTIMATE", "ABSTAIN"}
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
    if rec.get("rev_id") is None:
        errors.append(f"{where}: missing rev_id (provenance rule)")


def validate_estimate(rec, errors):
    where = f"estimate {rec.get('item', '?')!r}"
    for k, typ in ESTIMATE_REQUIRED.items():
        if k not in rec:
            errors.append(f"{where}: missing field {k}")
    if rec.get("status") not in ESTIMATE_STATUS:
        errors.append(f"{where}: bad status {rec.get('status')!r}")
    if rec.get("status") == "ABSTAIN" and not rec.get("abstain_reason"):
        errors.append(f"{where}: ABSTAIN without reason")
    if rec.get("status") == "ESTIMATE":
        for k in ("confidence", "bracket", "anchors"):
            if k not in rec:
                errors.append(f"{where}: ESTIMATE missing {k}")
        b = rec.get("bracket")
        if b and (not isinstance(b, list) or len(b) != 2 or b[0] > b[1]):
            errors.append(f"{where}: bad bracket {b!r}")


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
