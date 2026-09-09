"""Hardened wikitext parser for Roblox wiki item pages.

Fixes from external adversarial review (2026-09-09):
- HTML comments stripped before any extraction (comment poisoning).
- Purchase/favorite counts only trusted when paired with an "As of <date>"
  in the same sentence; unpaired counts are stored separately as
  unpaired_purchased (lower-bound candidate), never as exact values.
- "N copies" fallback REMOVED: copies-available != sold.
- Availability parsed case-insensitively; sale_state is a 3-value enum
  (still_available / closed / unknown), never a boolean guess.
- ALL until rows captured (until_history); a reopened item's LAST date
  wins, "Still available" anywhere means still available.
- until values that fail date validation are kept in until_history and
  flagged (parse_notes) rather than silently consumed or mis-typed.
"""
import re

DATE = r"[A-Z][a-z]+ \d{1,2}, \d{4}"
RE_ID = re.compile(r"^\s*\|\s*(?:catalog\s+)?id\s*=\s*(\d+)", re.M | re.I)
RE_BUNDLE_ID = re.compile(r"^\s*\|\s*bundle\s+id\s*=\s*(\d+)", re.M | re.I)
# Primary: same-sentence pairing ("As of X, it has been purchased N times")
RE_PAIR_PUR = re.compile(r"As of (" + DATE + r")[^.]*?(?:been|was) purchased ([\d,]+) times", re.I)
# times? was a backtracking bug: optional s let [^.]*? eat the s and match ACROSS the
# sentence-ending period. Wiki always writes "times". Anchored, no period crossing:
RE_PAIR_PUR2 = re.compile(r"(?:been|was) purchased ([\d,]+) times[^.\n]*?As of (" + DATE + r")", re.I)
# Wiki convention: count sentence followed IMMEDIATELY by an As-of sentence
# ("Before going off-sale, it was purchased N times. As of X, ...").
# The gap between count and date may not cross a second count mention.
RE_PAIR_PUR3 = re.compile(r"(?:been|was) purchased ([\d,]+) times\.\s*As of (" + DATE + r")", re.I)
RE_UNPAIRED_PUR = re.compile(r"(?:been|was) purchased ([\d,]+) times", re.I)
RE_PAIR_FAV = re.compile(r"As of (" + DATE + r")[^.]*?(?:been |was )?favorited ([\d,]+) times", re.I)
RE_PAIR_FAV2 = re.compile(r"(?:been |was )?favorited ([\d,]+) times[^.\n]*?As of (" + DATE + r")", re.I)
RE_UNTIL = re.compile(r"^\s*\|\s*until\s*=\s*(.+?)\s*$", re.M)
RE_DATE_ONLY = re.compile(r"^" + DATE + r"$|^\d{1,2} [A-Z][a-z]+ \d{4}$", re.I)
RE_STILL = re.compile(r"still\s+available", re.I)


def strip_comments(wt):
    return re.sub(r"<!--.*?-->", "", wt, flags=re.S)


def parse(wt):
    raw = wt
    wt = strip_comments(wt)
    notes = []
    if "<!--" in raw:
        notes.append("comments_stripped")
    m = RE_ID.search(wt)
    if not m:
        m = RE_BUNDLE_ID.search(wt)
        if m:
            notes.append("id_from_bundle_id")
    untils = [u.strip() for u in RE_UNTIL.findall(wt)]
    still = any(RE_STILL.search(u) for u in untils)
    real_dates = [u for u in untils if RE_DATE_ONLY.match(u)]
    bad_untils = [u for u in untils if not RE_DATE_ONLY.match(u) and not RE_STILL.search(u)]
    if bad_untils:
        notes.append("unparsed_until:" + ";".join(bad_untils))

    rec = {
        "item_id": int(m.group(1)) if m else None,
        "purchased": None,
        "purchased_as_of": None,
        "unpaired_purchased": None,
        "favorites": None,
        "favorites_as_of": None,
        "sale_state": "still_available" if still else ("closed" if real_dates else "unknown"),
        "until": real_dates[-1] if real_dates else None,
        "until_history": untils,
        "parse_ok": True,
        "parse_notes": notes,
    }

    p = RE_PAIR_PUR.search(wt)
    if p:
        rec["purchased_as_of"], rec["purchased"] = p.group(1), int(p.group(2).replace(",", ""))
    else:
        p2 = RE_PAIR_PUR2.search(wt)
        p3 = None if p2 else RE_PAIR_PUR3.search(wt)
        if p2:
            rec["purchased"], rec["purchased_as_of"] = int(p2.group(1).replace(",", "")), p2.group(2)
        elif p3:
            rec["purchased"], rec["purchased_as_of"] = int(p3.group(1).replace(",", "")), p3.group(2)
        else:
            up = RE_UNPAIRED_PUR.search(wt)
            if up:
                rec["unpaired_purchased"] = int(up.group(1).replace(",", ""))
                notes.append("purchased_unpaired_no_asof")

    f = RE_PAIR_FAV.search(wt)
    if f:
        rec["favorites"], rec["favorites_as_of"] = int(f.group(2).replace(",", "")), f.group(1)
    else:
        f2 = RE_PAIR_FAV2.search(wt)
        if f2:
            rec["favorites"], rec["favorites_as_of"] = int(f2.group(1).replace(",", "")), f2.group(2)
    rec["parse_notes"] = notes
    return rec
