"""Deterministic rank-bracket estimator.

Emits typed results: ESTIMATE (with confidence), ABSTAIN (typed reason), or ERROR.
Never emits a point estimate. Favorites-derived extrapolation is explicitly rejected
as a primary signal (measured fav/purchase ratio spread: 0.23-36.8).

Quantity estimated: cumulative purchases (sales), NOT unique owners. For
limited-unique items these differ (resale churn) - such anchors are excluded
when identifiable.
"""
import json, re
from datetime import date

# Era rule: wiki purchase counts for pre-2012 closures come from a tiny user
# base and don't share a scale with modern sales. Reject as anchors.
MIN_CLOSED_YEAR = 2012
# Bracket width beyond which we flag low confidence (approximate ordering).
MAX_SANE_WIDTH_RATIO = 4.0

MONTHS_FULL = ["January","February","March","April","May","June","July",
               "August","September","October","November","December"]
DATE_MONTHS = {m.lower(): i+1 for i, m in enumerate(MONTHS_FULL)}
# wiki abbreviations (case varies): dec 18, 2013 / NOVEMBER 24, 2023 / Nov 27, 2020
DATE_MONTHS.update({m.lower()[:3]: i+1 for i, m in enumerate(MONTHS_FULL)})

def parse_until(s):
    """'February 26, 2018', '14 mar 2016', 'NOVEMBER 24, 2023' -> (y, m, d) or None.
    Month matching is case-insensitive and accepts 3-letter abbreviations
    (293 real anchors were rejected for format before this fix).
    Impossible calendar dates (February 30, etc.) return None (Astra 2.6c)."""
    import datetime as _dt
    def _ok(y, mth, d):
        try:
            _dt.date(y, mth, d)
            return (y, mth, d)
        except ValueError:
            return None
    m = re.match(r"([A-Za-z]+) (\d{1,2}), (\d{4})", s.strip())
    if m and m.group(1).lower() in DATE_MONTHS:
        return _ok(int(m.group(3)), DATE_MONTHS[m.group(1).lower()], int(m.group(2)))
    m = re.match(r"(\d{1,2}) ([A-Za-z]+) (\d{4})", s.strip())
    if m and m.group(2).lower() in DATE_MONTHS:
        return _ok(int(m.group(3)), DATE_MONTHS[m.group(2).lower()], int(m.group(1)))
    return None


def anchor_eligible(rec):
    """Closed-final anchor check. Returns (ok, reason).

    Eligible: sale_state == 'closed' with a validated until date >= MIN_CLOSED_YEAR,
    a PAIRED purchase count (purchased + purchased_as_of), where the observation
    date is strictly AFTER the last closure date (Astra round-3 finding 1
    boundary: equality does not establish intra-day ordering, so a conservative
    day-level policy rejects obs == close).
    Unpaired counts are lower bounds of the anchor's own count; they must never
    serve as endpoints of a target bracket.

    FINALITY IS ENFORCED CENTRALLY HERE (Astra round-3 finding 1): a record
    that fails parsing, carries an unresolved/open later window, or has any
    window-model inconsistency is rejected. Invariant: removing or corrupting
    a later closure can never turn an ineligible anchor into an eligible one.
    """
    # parse-quality gate at the eligibility boundary (was only structural before)
    if rec.get("parse_ok") is False:
        return False, f"parse not ok (False; notes: {rec.get('parse_notes', [])[:2]})"
    if rec.get("parse_ok") is None and rec.get("parse_notes"):
        return False, f"parse notes present but parse_ok unset: {rec.get('parse_notes', [])[:2]}"
    # parse_ok=None with no notes: hand-built fixture record; tolerated here,
    # the shipped-DB validator refuses parse_ok != True regardless.
    if rec.get("sale_state") != "closed":
        return False, f"not-closed-final ({rec.get('sale_state')})"
    if not rec.get("until"):
        return False, "no until date"
    # Window MODEL (round-3): windows carry resolved/open/unknown states.
    # Any non-resolved window makes finality unestablishable - the last
    # parseable close is NOT proof the item never re-opened after it.
    windows = rec.get("windows")
    if windows is None:
        # Hand-built fixture records without a window model: derive a resolved
        # single window from until_history when the record asserts parse_ok=True.
        # Parsed round-3 records always carry windows; legacy parsed records
        # without windows remain ineligible (fail closed; re-parse instead of
        # trusting a degraded history list).
        if rec.get("parse_ok") is True:
            uh = rec.get("until_history") or ([rec["until"]] if rec.get("until") else [])
            if uh:
                windows = [{"index": str(i + 1), "until": u, "state": "resolved"}
                           for i, u in enumerate(uh)]
        if windows is None:
            return False, "no window model (pre-round-3 record; re-scrape required)"
    for w in windows:
        if w.get("state") != "resolved":
            return False, (f"window {w.get('index')} unresolved/open "
                           f"({w.get('state')}); finality not establishable")
    history = [w["until"] for w in windows if w.get("until")]
    last_close = None
    for u in history:
        du = parse_until(u or "")
        if du is not None and (last_close is None or du > last_close):
            last_close = du
    if last_close is None:
        return False, f"no parseable window close in {history}"
    if last_close[0] < MIN_CLOSED_YEAR:
        return False, f"pre-{MIN_CLOSED_YEAR} closure ({last_close[0]})"
    if rec.get("purchased") is None:
        if rec.get("unpaired_purchased") is not None:
            return False, "unpaired count only (lower bound, not final)"
        return False, "no purchase count"
    # structural sanity (Astra 2.6c): bool is an int subclass in python - reject
    # explicitly; counts must be positive integers; dates must be real.
    pc = rec["purchased"]
    if isinstance(pc, bool) or not isinstance(pc, int) or pc < 0:
        return False, f"malformed purchase count: {pc!r}"
    a = parse_until(rec.get("purchased_as_of") or "")
    if a is None:
        return False, f"unparseable purchased_as_of: {rec.get('purchased_as_of')}"
    # STRICTLY after last close (round-3 boundary): same-day observation cannot
    # be ordered relative to the closure within the day; conservative rejection.
    if a <= last_close:
        return False, (f"stale count: observed {rec['purchased_as_of']} not after "
                       f"last window close {last_close}; not the final count")
    # channel-scope STATUS (round-3): only explicit single-channel scope is
    # trusted; dual AND unknown both fail closed.
    if rec.get("purchase_count_scope") != "single":
        return False, (f"purchase_count_scope={rec.get('purchase_count_scope')!r}: "
                       "count channel coverage unproven; not trusted as anchor")
    return True, "ok"


def rank_bracket(pool, target_id, anchors_db):
    """pool: ordered list of item ids (sales order, snapshot-local).
    anchors_db: dict id -> anchor record (hardened schema).
    ID handling is type-normalized: pools store strings (catalog API ids),
    anchors store ints; both lookups go through str(). The CLI passes an int,
    the batch runner a string - identical behavior either way.
    Returns a result dict. NEVER a point estimate."""
    pool = [str(x) for x in pool]
    target_id = str(target_id)
    # Typed identity lookups ONLY (Astra round-3 finding 5A): untyped plain-ID
    # aliases let a bundle with the same numeric id overwrite an asset anchor
    # (reproduced: asset:555=20000 shadowed by bundle:555=8000, changing the
    # emitted bracket). Pools are catalog walks (assets), so lookups use the
    # asset namespace; bundle targets must be walked and estimated as bundles
    # with an explicit bundle pool + typed target id.
    t_typed = target_id if ":" in target_id else f"asset:{target_id}"
    pool_typed = [x if ":" in x else f"asset:{x}" for x in pool]
    # Normalize the anchors_db keys into the same typed namespace; plain keys
    # are treated as asset ids (pools are catalog walks). An explicitly typed
    # db key always wins over its plain alias (Astra 5A: wrong-entity overwrite).
    db_typed = {}
    for k, v in anchors_db.items():
        if ":" in k:
            db_typed[k] = v            # typed key: authoritative
    for k, v in anchors_db.items():
        if ":" not in k:
            typed = f"asset:{k}"
            if typed not in db_typed:  # never shadow an explicit typed record
                db_typed[typed] = v
    anchors_db = db_typed
    if t_typed not in pool_typed:
        return {"status": "ABSTAIN", "reason": "TARGET_NOT_IN_POOL",
                "detail": "target absent from this pool snapshot; re-walk required"}
    # Self-bracket guard (Astra 2.5): duplicate ids mean 'position' is ambiguous and
    # the same anchor can be found on both sides. Duplicate occurrences are server
    # drift evidence - abstain, do not pick an arbitrary occurrence.
    if len(pool_typed) != len(set(pool_typed)):
        return {"status": "ABSTAIN", "reason": "DUPLICATE_POOL_IDS",
                "detail": f"{len(pool_typed) - len(set(pool_typed))} duplicate id(s); ranking ambiguous"}
    if pool_typed.count(t_typed) > 1:
        return {"status": "ABSTAIN", "reason": "TARGET_DUPLICATED",
                "detail": "target appears multiple times in pool"}

    # collect eligible anchors above and below the target rank (typed keys only)
    ti = pool_typed.index(t_typed)
    above = below = None
    for j in range(ti - 1, -1, -1):
        a = anchors_db.get(pool_typed[j])
        if a and anchor_eligible(a)[0]:
            above = (j, a); break
    for j in range(ti + 1, len(pool_typed)):
        a = anchors_db.get(pool_typed[j])
        if a and anchor_eligible(a)[0]:
            below = (j, a); break

    missing = []
    if above is None: missing.append("no eligible closed-final anchor above")
    if below is None: missing.append("no eligible closed-final anchor below")
    if missing:
        return {"status": "ABSTAIN", "reason": "NO_ELIGIBLE_ANCHOR_" +
                ("ABOVE" if above is None else "BELOW") + ("_AND_BELOW" if above is None and below is None else ""),
                "detail": "; ".join(missing)}

    (ai, aa), (bi, ab) = above, below
    # anchor_eligible now guarantees paired final counts; endpoints are exact
    # anchor observations, never unpaired lower bounds.
    hi = aa["purchased"]
    lo = ab["purchased"]
    warnings0 = []
    if hi is None or lo is None:
        return {"status": "ABSTAIN", "reason": "ANCHOR_COUNT_MISSING",
                "detail": "eligible anchor has no paired count (defense in depth)"}
    if hi < lo:
        # Inversion: the ordering claim is contradicted by the endpoints themselves.
        # A backwords interval is structurally misleading (Astra 2.6a) - sorting the
        # endpoints would hide the contradiction. Abstain instead.
        return {"status": "ABSTAIN", "reason": "ANCHOR_INVERSION",
                "detail": f"upper-rank anchor purchased={hi} < lower-rank anchor purchased={lo}; "
                          "ranking signal contradicted by anchor data"}
    if hi == lo:
        # Singleton interval: exact-looking output implies exact knowledge. An
        # uncalibrated heuristic must not emit that shape by default (Astra 2.6b).
        return {"status": "ABSTAIN", "reason": "SINGLETON_INTERVAL",
                "detail": "both anchors report identical counts; interval would imply exact knowledge"}
    if lo / hi < (1.0 / MAX_SANE_WIDTH_RATIO):
        result = {"status": "ESTIMATE", "confidence": "LOW",
                  "warnings": warnings0 + [f"wide bracket ({hi/max(lo,1):.1f}x)"]}
    else:
        result = {"status": "ESTIMATE", "confidence": "MEDIUM", "warnings": warnings0}

    result.update({
        "bracket": [lo, hi],
        "target_id": target_id,
        "rank_in_pool": ti,
        "anchors": {
            "above": {"id": pool_typed[ai], "rank": ai, "purchased": hi, "title": aa.get("title"),
                      "until": aa.get("until"), "purchased_as_of": aa.get("purchased_as_of")},
            "below": {"id": pool_typed[bi], "rank": bi, "purchased": lo, "title": ab.get("title"),
                      "until": ab.get("until"), "purchased_as_of": ab.get("purchased_as_of")},
        },
        "quantity": "cumulative_purchases_lower_bound_interval",
        "note": "rank-neighbor interval, NOT a verified bound: ordering is approximate (measured ~17% local inversions)",
    })
    return result


def merge_pools(pool_results, target_id):
    """DEPRECATED helper - DO NOT USE for published estimates.

    Two independent reasons (Astra 2.6d + 3.5):
    1. Metadata bug: the result carried the FIRST pool's target_id/confidence
       regardless of the target argument - wrong-entity metadata.
    2. Statistical invalidity: intersecting heuristic intervals does not create
       confidence. Shared-anchor pools are correlated; even ten independent 95%
       intervals intersect-contain only ~60% of the time. Without a separately
       validated combination rule, any merge output is uninterpretable.

    Kept only so old callers fail loudly rather than silently mislead."""
    raise NotImplementedError(
        "merge_pools is retired: interval intersection has no calibrated meaning "
        "(Astra 3.5). Bracket per pool and publish pool-local results.")
