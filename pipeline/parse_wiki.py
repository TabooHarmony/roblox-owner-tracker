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
# Scoped identity: search infobox parameter lines ONLY (line starts with | inside the
# infobox span), so literal examples in <nowiki> or prose cannot shadow the real id.
RE_INFOBOX = re.compile(r"\{\{\s*[Ii]nfobox[^}]*\}\}", re.S)
RE_ID = re.compile(r"^\s*\|\s*(?:catalog\s+)?id\s*=\s*(\d+)", re.M | re.I)
RE_BUNDLE_ID = re.compile(r"^\s*\|\s*bundle\s+id\s*=\s*(\d+)", re.M | re.I)
# STRICT same-sentence date binding (Astra 2.1a): a purchase count pairs with an
# As-of date ONLY when both live in the same sentence (no period between). The old
# cross-sentence fallbacks bound counts to favorites/removal dates in the NEXT
# sentence - fabricated provenance. Either order inside one sentence is fine.
RE_PAIR_PUR = re.compile(
    r"(?:As of (" + DATE + r")[,.]?\s*(?:it\s+)?(?:has\s+|had\s+)?(?:been|was) purchased ([\d,]+) times"
    r"|(?:been|was) purchased ([\d,]+) times[^.\n]*?\b[Aa]s of (" + DATE + r"))", re.I)
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
    # identity must come from inside the infobox span; a literal <nowiki>| id = 999</nowiki
    # example in the page body must never shadow the real parameter (Astra 2.1c).
    box = RE_INFOBOX.search(wt)
    scope = box.group(0) if box else wt
    m = RE_ID.search(scope)
    if not m:
        m = RE_BUNDLE_ID.search(scope)
        if m:
            notes.append("id_from_bundle_id")
            notes.append("entity_type:bundle")
        else:
            notes.append("no_infobox_span_found") if not box else None
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

    # Fail closed on unresolved date templates (Astra 2.1c): a {{Date|...}}
    # the parser cannot resolve means the page carries availability/count info
    # we did NOT consume. The record stays parseable but parse_ok=False so the
    # engine and merger refuse it rather than trusting a clean-looking subset.
    unresolved = re.findall(r"\{\{\s*Date\s*\|[^}]*\}\}", wt)
    if unresolved:
        rec["parse_ok"] = False
        rec["parse_notes"].append("unresolved_date_template:" + ";".join(unresolved[:3]))

    p = RE_PAIR_PUR.search(wt)
    if p:
        if p.group(1):
            rec["purchased_as_of"], rec["purchased"] = p.group(1), int(p.group(2).replace(",", ""))
        else:
            rec["purchased"], rec["purchased_as_of"] = int(p.group(3).replace(",", "")), p.group(4)
    else:
        up = RE_UNPAIRED_PUR.search(wt)
        if up:
            rec["unpaired_purchased"] = int(up.group(1).replace(",", ""))
            notes.append("purchased_unpaired_no_asof: strict binding found no same-sentence date")

    f = RE_PAIR_FAV.search(wt)
    if f:
        rec["favorites"], rec["favorites_as_of"] = int(f.group(2).replace(",", "")), f.group(1)
    else:
        f2 = RE_PAIR_FAV2.search(wt)
        if f2:
            rec["favorites"], rec["favorites_as_of"] = int(f2.group(1).replace(",", "")), f2.group(2)
    rec["parse_notes"] = notes
    return rec
