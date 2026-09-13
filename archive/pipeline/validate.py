"""Schema validation for anchors and estimates. Exit 1 on any violation.
No network, no LLM: pure structural checks over the shipped JSONL files.

Strictness policy (Astra 2.7): type errors are structured failures, never
truthiness-guarded; booleans are NOT integers; schema version, enums, calendar
timestamps, bracket shape, and anchor/endpoint relational consistency are all
enforced. Empty/truncated datasets fail (completeness rule, Astra 2.9).
"""
import datetime
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
SCHEMA_VERSIONS = {2}
ESTIMATE_REQUIRED = {
    "schema": int, "item": str, "item_id": int, "snapshot_utc": str,
    "pool": str, "status": str, "quantity": str,
    # provenance envelope fields are MANDATORY (round-3 finding 5C): a row
    # without them cannot be replayed or attributed.
    "code_commit": str, "parser_version": str, "anchors_sha256": str,
}
ESTIMATE_STATUS = {"ESTIMATE", "ABSTAIN"}
# real calendar dates only: 2026-99-99 must fail, not just the shape
SNAPSHOT_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})Z$")


def _is_int(x):
    """bool is an int subclass in Python; the schema says integer, so bool fails."""
    return isinstance(x, int) and not isinstance(x, bool)


def _real_timestamp(s):
    m = SNAPSHOT_RE.match(s or "")
    if not m:
        return False
    y, mo, d, h, mi, se = map(int, m.groups())
    try:
        datetime.datetime(y, mo, d, h, mi, se)
    except ValueError:
        return False
    return True


def validate_anchor(rec, errors):
    where = f"anchor {rec.get('title', '?')!r}"
    for k, typ in ANCHOR_REQUIRED.items():
        if k not in rec:
            errors.append(f"{where}: missing field {k}")
        elif not isinstance(rec[k], typ):
            errors.append(f"{where}: field {k} wrong type {type(rec[k]).__name__}")
    # bool/negative counts (Astra 2.6c/2.7)
    for k in ("purchased", "unpaired_purchased", "item_id", "rev_id"):
        v = rec.get(k)
        if v is not None and not _is_int(v):
            errors.append(f"{where}: field {k} must be integer-or-null, got {v!r}")
        elif _is_int(v) and v < 0 and k != "rev_id":
            errors.append(f"{where}: field {k} negative: {v!r}")
    if rec.get("sale_state") not in ANCHOR_STATES:
        errors.append(f"{where}: bad sale_state {rec.get('sale_state')!r}")
    # parse_ok must be TRUE, not merely boolean (round-3 finding 1 integration):
    # a record the parser flagged unresolved must never reach the shipped DB.
    if rec.get("parse_ok") is not True:
        errors.append(f"{where}: parse_ok is {rec.get('parse_ok')!r}; failed parses are "
                      "refused, not shipped")
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
    if rec.get("schema") not in SCHEMA_VERSIONS:
        errors.append(f"{where}: unsupported schema {rec.get('schema')!r}")
    if not _is_int(rec.get("item_id")) or rec.get("item_id", 0) < 0:
        errors.append(f"{where}: item_id must be a nonnegative integer, got {rec.get('item_id')!r}")
    if not _real_timestamp(rec.get("snapshot_utc")):
        errors.append(f"{where}: snapshot_utc not a real UTC calendar timestamp "
                      f"({rec.get('snapshot_utc')!r}; wall-clock fabrication forbidden)")
    if rec.get("status") not in ESTIMATE_STATUS:
        errors.append(f"{where}: bad status {rec.get('status')!r}")
    if rec.get("status") == "ABSTAIN" and not rec.get("abstain_reason"):
        errors.append(f"{where}: ABSTAIN without reason")
    if rec.get("status") == "ESTIMATE":
        for k in ("bracket", "anchors"):
            if k not in rec:
                errors.append(f"{where}: ESTIMATE missing {k}")
        b = rec.get("bracket")
        if b is None:
            errors.append(f"{where}: ESTIMATE with null bracket")
        elif (not isinstance(b, list) or len(b) != 2
              or not all(_is_int(x) for x in b)):
            errors.append(f"{where}: bad bracket {b!r} (two nonnegative integers required)")
        elif any(x < 0 for x in b):
            errors.append(f"{where}: negative bracket endpoint {b!r}")
        elif b[0] > b[1]:
            errors.append(f"{where}: inverted bracket {b!r} (engine must abstain, not emit)")
        elif b[0] == b[1]:
            errors.append(f"{where}: singleton interval {b!r} implies exact knowledge; "
                          "engine must abstain (SINGLETON_INTERVAL)")
        a = rec.get("anchors") or {}
        if not isinstance(a, dict) or not a:
            errors.append(f"{where}: ESTIMATE anchors missing/empty")
        else:
            pa = pb = None
            for side in ("above", "below"):
                sa = a.get(side)
                if not isinstance(sa, dict):
                    errors.append(f"{where}: {side} anchor missing")
                    continue
                p = sa.get("purchased")
                if not _is_int(p) or p < 0:
                    errors.append(f"{where}: {side} anchor count invalid: {p!r}")
                if side == "above":
                    pa = p
                else:
                    pb = p
            # relational consistency: bracket must lie between the anchor counts
            b_ok = (isinstance(b, list) and len(b) == 2
                    and all(_is_int(x) for x in b)
                    and _is_int(pa) and _is_int(pb))
            if b_ok:
                lo, hi = b
                if not (min(pa, pb) <= lo and hi <= max(pa, pb)):
                    errors.append(f"{where}: bracket {[lo, hi]} inconsistent with anchor "
                                  f"counts {[pa, pb]}")
    if rec.get("status") == "ABSTAIN":
        # an abstention must not smuggle an interval
        if rec.get("bracket") is not None:
            errors.append(f"{where}: ABSTAIN carrying bracket")
    # v0 scope: assets only; the entity_type field is a fixed constant now
    if rec.get("entity_type") != "asset":
        errors.append(f"{where}: entity_type must be 'asset' "
                      f"(v0 scope is assets only), got {rec.get('entity_type')!r}")


def _validate_file(path, fn, errors, min_rows=1):
    if not os.path.exists(path):
        errors.append(f"missing {path}")
        return 0
    n = 0
    for i, l in enumerate(open(path), 1):
        l = l.strip()
        if not l:
            errors.append(f"{path}:{i}: blank line (truncated write?)")
            continue
        try:
            rec = json.loads(l)
        except json.JSONDecodeError as e:
            errors.append(f"{path}:{i}: malformed JSON: {e}")
            continue
        fn(rec, errors)
        n += 1
    if n < min_rows:
        errors.append(f"{path}: {n} rows (completeness rule: an empty/partial dataset "
                      "must fail validation, never publish)")
    return n


def main():
    errors = []
    n_anchors = _validate_file(
        os.path.join(ROOT, "anchors", "anchors_harden.jsonl"), validate_anchor, errors)
    n_est = _validate_file(
        os.path.join(ROOT, "estimates", "estimates_v2.jsonl"), validate_estimate, errors)
    for e in errors[:20]:
        print("ERROR:", e)
    print(f"validated: {n_anchors} anchors, {n_est} estimates, {len(errors)} errors")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
