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
    (293 real anchors were rejected for format before this fix)."""
    m = re.match(r"([A-Za-z]+) (\d{1,2}), (\d{4})", s.strip())
    if m and m.group(1).lower() in DATE_MONTHS:
        return (int(m.group(3)), DATE_MONTHS[m.group(1).lower()], int(m.group(2)))
    m = re.match(r"(\d{1,2}) ([A-Za-z]+) (\d{4})", s.strip())
    if m and m.group(2).lower() in DATE_MONTHS:
        return (int(m.group(3)), DATE_MONTHS[m.group(2).lower()], int(m.group(1)))
    return None


def anchor_eligible(rec):
    """Closed-final anchor check. Returns (ok, reason).

    Eligible: sale_state == 'closed' with a validated until date >= MIN_CLOSED_YEAR,
    a PAIRED purchase count (purchased + purchased_as_of), where the observation
    date is not earlier than the closure date. A count observed before closure is
    not the final count (Astra #2): purchases keep accruing until `until`.
    Unpaired counts are lower bounds of the anchor's own count; they must never
    serve as endpoints of a target bracket.
    """
    if rec.get("sale_state") != "closed":
        return False, f"not-closed-final ({rec.get('sale_state')})"
    if not rec.get("until"):
        return False, "no until date"
    d = parse_until(rec["until"])
    if d is None:
        return False, f"unparseable until: {rec['until']}"
    if d[0] < MIN_CLOSED_YEAR:
        return False, f"pre-{MIN_CLOSED_YEAR} closure ({d[0]})"
    if rec.get("purchased") is None:
        if rec.get("unpaired_purchased") is not None:
            return False, "unpaired count only (lower bound, not final)"
        return False, "no purchase count"
    a = parse_until(rec.get("purchased_as_of") or "")
    if a is None:
        return False, f"unparseable purchased_as_of: {rec.get('purchased_as_of')}"
    if a < d:
        return False, (f"stale count: observed {rec['purchased_as_of']} before "
                       f"closure {rec['until']}; not the final count")
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
    if target_id not in pool:
        return {"status": "ABSTAIN", "reason": "TARGET_NOT_IN_POOL",
                "detail": "target absent from this pool snapshot; re-walk required"}

    # collect eligible anchors above and below the target rank
    ti = pool.index(target_id)
    above = below = None
    for j in range(ti - 1, -1, -1):
        a = anchors_db.get(str(pool[j]))
        if a and anchor_eligible(a)[0]:
            above = (j, a); break
    for j in range(ti + 1, len(pool)):
        a = anchors_db.get(str(pool[j]))
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
        # monotonicity guard: approximate ordering means this CAN happen.
        # widen: the interval is still [lo, hi] as numbers, but the ordering
        # claim is broken -> widen to the next anchors would need more pool.
        # Here: emit with explicit inversion warning.
        result = {"status": "ESTIMATE", "confidence": "LOW",
                  "warnings": warnings0 + ["ANCHOR_INVERSION: upper-rank anchor has fewer purchases than lower-rank anchor; ordering is approximate"]}
    elif hi == 0 or lo / hi < (1.0 / MAX_SANE_WIDTH_RATIO):
        result = {"status": "ESTIMATE", "confidence": "LOW",
                  "warnings": warnings0 + [f"wide bracket ({hi/max(lo,1):.1f}x)"]}
    else:
        result = {"status": "ESTIMATE", "confidence": "MEDIUM", "warnings": warnings0}

    result.update({
        "bracket": [lo, hi],
        "target_id": target_id,
        "rank_in_pool": ti,
        "anchors": {
            "above": {"id": pool[ai], "rank": ai, "purchased": hi, "title": aa.get("title"),
                      "until": aa.get("until"), "purchased_as_of": aa.get("purchased_as_of")},
            "below": {"id": pool[bi], "rank": bi, "purchased": lo, "title": ab.get("title"),
                      "until": ab.get("until"), "purchased_as_of": ab.get("purchased_as_of")},
        },
        "quantity": "cumulative_purchases_lower_bound_interval",
        "note": "rank-neighbor interval, NOT a verified bound: ordering is approximate (measured ~17% local inversions)",
    })
    return result


def merge_pools(pool_results, target_id):
    """Multiple pool snapshots for the same target: intersect if they overlap,
    ABSTAIN on conflict. Never pick the narrower one (Astra #1)."""
    ests = [r for r in pool_results if r["status"] == "ESTIMATE"]
    if not ests:
        return {"status": "ABSTAIN", "reason": "NO_POOL_PRODUCED_ESTIMATE"}
    lo = max(r["bracket"][0] for r in ests)
    hi = min(r["bracket"][1] for r in ests)
    if lo > hi:
        return {"status": "ABSTAIN", "reason": "CONFLICTING_POOLS",
                "detail": f"pools disagree: {[r['bracket'] for r in ests]} - intersection empty"}
    out = dict(ests[0])
    out["bracket"] = [lo, hi]
    out["pools_merged"] = len(ests)
    return out
