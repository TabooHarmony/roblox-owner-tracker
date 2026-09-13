"""Hardened wikitext parser for Roblox wiki item pages.

Round-3 fixes (Astra HOLD at 4acbc0f):
- Window MODEL, not a date list: every (fromN, untilN) pair becomes a window
  record classified resolved / open / unknown. An unparseable or blank closure
  is UNRESOLVED EVIDENCE - it can never be silently skipped (the old guard
  admitted a mid-second-window count whenever until2 was Unknown/blank/Feb-30).
- A window with an opening but no closure field at all is OPEN: the item was
  re-released and never re-closed => sale_state is still_available, never
  "closed on the first window".
- Assertion-level date binding: sentences are enumerated; a purchase count
  pairs with an As-of date ONLY inside the same sentence, only when the
  sentence is unambiguous (one purchase assertion, one date). Optional
  punctuation before the next sentence no longer bridges two sentences.
- Channel scope is a STATUS, not a phrase blacklist: markup/whitespace is
  normalized before detection, aliases are recognized, and every record gets
  purchase_count_scope in {single, dual, unknown} with scope_evidence.
  Absence of a matched phrase means UNKNOWN, never trusted single-channel.
- parse_ok=False is a hard rejection downstream: eligibility, merger, and
  validator all refuse such records.
- Calendar validation happens once here: impossible dates (Feb 30) become
  unresolved windows, not discarded evidence.
"""
import re

DATE = r"[A-Z][a-z]+ \d{1,2}, \d{4}"
# Scoped identity: search infobox parameter lines ONLY (line starts with | inside the
# infobox span), so literal examples in <nowiki> or prose cannot shadow the real id.
RE_INFOBOX = re.compile(r"\{\{\s*[Ii]nfobox[^}]*\}\}", re.S)
RE_ID = re.compile(r"^\s*\|\s*(?:catalog\s+)?id\s*=\s*(\d+)", re.M | re.I)
RE_BUNDLE_ID = re.compile(r"^\s*\|\s*bundle\s+id\s*=\s*(\d+)", re.M | re.I)

# Window fields: until, until2..untilN, from, from2..fromN (position = window order)
RE_UNTIL_FIELD = re.compile(r"^\s*\|\s*until(\d*)\s*=\s*(.*?)\s*$", re.M)
RE_FROM_FIELD = re.compile(r"^\s*\|\s*from(\d*)\s*=\s*(.*?)\s*$", re.M)
RE_STILL = re.compile(r"still\s+available", re.I)
RE_DATE_ONLY = re.compile(r"^" + DATE + r"$|^\d{1,2} [A-Z][a-z]+ \d{4}$", re.I)

# Purchase assertions (for assertion-level binding). A "purchase assertion" is
# any sentence containing 'purchased N times'; a candidate date is an
# 'As of <date>' / 'as of <date>' in the SAME sentence.
RE_PURCHASE = re.compile(r"(?:been|was)\s+purchased\s+([\d,]+)\s+times", re.I)
RE_ASOF = re.compile(r"\b[Aa]s\s+of\s+(" + DATE + r")", re.I)
RE_FAVORITED = re.compile(r"favorited\s+[\d,]+\s+times", re.I)

# Dual-channel detection operates on NORMALIZED text (links flattened,
# quotes/whitespace collapsed). Channel words and experience mentions are
# detected separately; scope is dual only when BOTH appear in an affirmative
# availability/purchase statement about this item.
RE_CHANNEL_MARKET = re.compile(
    r"\b(?:marketplace|catalog|avatar\s+shop|item\s+shop)\b", re.I)
RE_CHANNEL_EXPERIENCE = re.compile(
    r"\b(?:in|during|for)\s+(?:the\s+)?(?:experience|game|event|"
    r"\[\[[^\]]+\]\]|[A-Z][A-Za-z0-9_'!]+(?:\s+[A-Z][A-Za-z0-9_'!]+)*)\b")
RE_AVAILABILITY = re.compile(
    r"\b(?:was|is|are|became|available|purchasable|sold|obtainable|obtained|"
    r"purchased|could\s+(?:also\s+)?be\s+(?:bought|purchased|obtained))\b",
    re.I)
RE_NEGATED = re.compile(
    r"\b(?:no longer|not|never|cannot|can't|removed from|unavailable)\b", re.I)
RE_PAGE_SUBJECT = re.compile(r"'''([^']+)'''")


def _page_subject(wt):
    """The page item is the first bolded entity in the wikitext."""
    m = RE_PAGE_SUBJECT.search(wt)
    return m.group(1).lower() if m else None


def _channel_scope(wt_norm, subject=None):
    """Channel-scope STATUS about THIS item, from normalized sentences.

    dual:    affirmative statements about this item, taken TOGETHER, name both
             a marketplace-family channel and an experience -> wiki count may
             cover one channel only. Dual DOMINATES: any dual sentence wins
             over single evidence elsewhere (safety-critical direction).
    single:  an affirmative statement about this item that (a) names a
             marketplace-family channel and (b) carries a sale/availability
             assertion in the same sentence, with no dual evidence anywhere.
    unknown: no affirmative channel statement about this item. NOT trusted
             single - absence of a phrase is not evidence of one channel.

    Round-4 (Astra finding 1) hard invariants:
      - Category/link metadata ([[Category:Catalog items]], bare 'Catalog',
        [[Catalog:X]] nav links) is NEVER channel evidence. normalize_markup
        strips those namespaces; this function additionally refuses to count a
        marketplace token in a sentence that has no sale/availability verb
        (a bare mention is metadata, not a coverage statement).
      - Channel statements COMBINE across sentences: 'purchased on the
        marketplace' + a separate 'obtainable in The Hunt' sentence is dual,
        not single. Availability-only marketplace sentences also accumulate.
      - Count coverage (a paired purchase assertion) stays distinct from mere
        availability; both feed scope, neither is subordinate to the other.

    Sentences with negated availability are never affirmative evidence, and
    sentences whose subject is a different named item are skipped (Astra
    round-3 finding 3 false positives).
    """
    subj = subject or _page_subject(wt_norm)
    saw_market = None    # first affirmative marketplace mention w/ sale verb
    saw_exp = None       # first affirmative experience mention w/ sale verb
    for sent in re.split(r"[.;:\n]", wt_norm):
        sent = sent.strip()
        if not sent:
            continue
        if RE_NEGATED.search(sent):
            continue  # negated availability is not affirmative evidence
        low = " " + sent.lower() + " "
        about = (" it " in low or re.match(r"^it\b", low) or
                 (subj and subj in low))
        if not about:
            named = re.match(r"^([A-Z][A-Za-z0-9_'’]+(?:\s+[A-Z][A-Za-z0-9_'’]+)+)",
                             sent)
            if named and (not subj or named.group(1).lower() != subj):
                continue  # statement about another item
        has_m = RE_CHANNEL_MARKET.findall(sent)
        has_e = RE_CHANNEL_EXPERIENCE.search(sent)
        # two DIFFERENT marketplace-family channels named: the count may cover
        # either one -> same distrust as dual (conservative).
        m_kinds = {x.lower() for x in has_m}
        if len(m_kinds) > 1:
            return "dual", f"multi-marketplace channels: {sorted(m_kinds)}"
        if has_m and has_e:
            return "dual", f"{has_m[0]} + {has_e.group(0)}"
        # a marketplace/experience token only becomes trusted evidence when the
        # sentence asserts sale/availability of this item; a bare category or
        # nav mention carries no coverage information (round-4 finding 1)
        if not RE_AVAILABILITY.search(sent):
            continue
        if has_m and saw_market is None:
            saw_market = has_m[0]
        if has_e and saw_exp is None:
            saw_exp = has_e.group(0)
    if saw_market and saw_exp:
        return "dual", f"{saw_market} + {saw_exp} (separate sentences)"
    if saw_market:
        return "single", saw_market
    return "unknown", None


def strip_comments(wt):
    return re.sub(r"<!--.*?-->", "", wt, flags=re.S)


def normalize_markup(wt):
    """Flatten links, bold/italic, templates-in-prose, and whitespace so the
    channel detector cannot be bypassed by [[The Hunt]], '''marketplace''',
    or a newline inside the phrase (Astra round-3 finding 3).

    Round-4 (Astra 4.1 finding 1): Category/Catalog-NAMESPACE links are pure
    metadata/navigation - they are REMOVED before the general flatten so they
    can never contribute a marketplace-family token. Merely adding
    [[Category:Catalog items]] must never promote unknown count coverage into
    trusted single-channel coverage."""
    t = re.sub(r"\[\[\s*[Cc]ategory\s*:[^\]]*\]\]", " ", wt)   # [[Category:x]]: metadata
    t = re.sub(r"\[\[\s*[Cc]atalog\s*:[^\]]*\]\]", " ", t)     # [[Catalog:x]]: nav link
    t = re.sub(r"\[\[(?:[^\|\]]*\|)?([^\]]+)\]\]", r"\1", t)   # [[a|b]]->b, [[a]]->a
    t = re.sub(r"'+", "", t)                                    # '''bold'''/''ital''
    t = re.sub(r"<!--.*?-->", "", t, flags=re.S)
    # flattened category/catalog namespace remnants (e.g. 'Category:Catalog items'
    # left by a non-wiki-link mention) must not read as a channel token either
    t = re.sub(r"\b[Cc]ategory\s*:\S+", " ", t)
    t = re.sub(r"\b[Cc]atalog\s*:\S+", " ", t)
    t = re.sub(r"\s+", " ", t)
    return t


def split_sentences(text):
    """Sentences end at '.', ';', ':', or newline. A date like 'January 1,
    2019' contains periods only as part of nothing - commas are safe. Year
    forms 'in 2014' stay inside their sentence."""
    return [s.strip() for s in re.split(r"[.;:\n]", text) if s.strip()]


def _validate_date(s):
    """Canonical validation: 'March 1, 2022' / '1 March 2022' -> canonical
    'Month D, YYYY' string; impossible calendar dates -> None (unresolved,
    never discarded - Astra round-3 finding 1)."""
    m = re.match(r"^([A-Za-z]+) (\d{1,2}), (\d{4})$", s.strip())
    months = {m.lower(): i + 1 for i, m in enumerate(
        ["January","February","March","April","May","June","July","August",
         "September","October","November","December"])}
    months.update({m[:3].lower(): i + 1 for i, m in enumerate(
        ["January","February","March","April","May","June","July","August",
         "September","October","November","December"])})
    if m and m.group(1).lower() in months:
        try:
            import datetime as _dt
            d = _dt.date(int(m.group(3)), months[m.group(1).lower()], int(m.group(2)))
            return d.strftime("%B %d, %Y").replace(" 0", " ")
        except ValueError:
            return None
    m = re.match(r"^(\d{1,2}) ([A-Za-z]+),? (\d{4})$", s.strip())
    if m and m.group(2).lower() in months:
        try:
            import datetime as _dt
            d = _dt.date(int(m.group(3)), months[m.group(2).lower()], int(m.group(1)))
            return d.strftime("%B %d, %Y").replace(" 0", " ")
        except ValueError:
            return None
    return None


def extract_windows(scope):
    """Build ordered window records from fromN/untilN fields.

    Returns (windows, sale_state, notes):
      window: {"index", "from", "until", "state": resolved|open|unknown}
      - resolved: closure parses to a real calendar date
      - open:     opening present, closure field ABSENT (item still on sale)
      - unknown:  closure present but blank/unparseable/template
    Position in the infobox = window order (until2 before until still sorts
    by text position).
    """
    fields = []
    for m in RE_UNTIL_FIELD.finditer(scope):
        fields.append((m.start(), "until", m.group(1), m.group(2)))
    for m in RE_FROM_FIELD.finditer(scope):
        fields.append((m.start(), "from", m.group(1), m.group(2)))
    fields.sort(key=lambda t: t[0])

    windows = {}
    for _, kind, num, val in fields:
        w = windows.setdefault(num or "1", {"index": num or "1", "from": None,
                                            "until": None, "state": "unknown"})
        if kind == "from":
            if w["from"] is not None:
                notes_dup = True  # noqa: F841 (tracked below via windows meta)
                w.setdefault("dup_from", True)
            w["from"] = val or None
        else:
            if w.get("until_raw") is not None:
                if (w["until_raw"] or "") != (val or ""):
                    w["dup_until"] = True   # conflicting values: contradiction
                else:
                    w["dup_until_same"] = True  # harmless edit residue: note only
            w["until_raw"] = val
            w["until"] = val or None

    notes = []
    contradictions = []   # round-4 finding 2: contradictions INVALIDATE, not note
    out = []
    for num in sorted(windows, key=lambda x: (len(x), x)):
        w = windows[num]
        if w.pop("dup_until", False):
            # round-4 finding 2: two conflicting closures for the same window.
            # Order of fields must not decide which is trusted; the evidence is
            # contradictory -> the window is unresolved evidence, page fails.
            contradictions.append(
                f"contradictory_window_{num}:duplicate until field with different values")
        if w.pop("dup_until_same", False):
            notes.append(f"duplicate_until_window_{num}:identical values (edit residue)")
        if w.pop("dup_from", False):
            contradictions.append(
                f"contradictory_window_{num}:duplicate from field with different values")
        u = (w.get("until") or "").strip()
        f = (w.get("from") or "").strip()
        if not u:
            # closure field absent entirely
            if f or w.get("until_raw") == "":
                w["state"] = "open" if not w.get("until_raw") else "unknown"
                if w.get("until_raw") == "":
                    # field present but blank: UNRESOLVED, not absent
                    w["state"] = "unknown"
                    notes.append(f"unresolved_window_{num}:blank_until")
                else:
                    notes.append(f"open_window_{num}:re-released with no closing date")
            else:
                w["state"] = "unknown"
                notes.append(f"unresolved_window_{num}:no_until")
        else:
            if RE_STILL.match(u):
                w["state"] = "open"
                notes.append(f"open_window_{num}:still available")
            else:
                canon = _validate_date(u)
                if canon:
                    w["until"] = canon
                    w["state"] = "resolved"
                else:
                    w["state"] = "unknown"
                    notes.append(f"unresolved_window_{num}:{u!r}")
        fc = _validate_date(f) if f else None
        if f and fc is None and f.lower() not in ("unknown", ""):
            # round-4 finding 2: an impossible opening (February 30) is
            # UNRESOLVED EVIDENCE, not a discarded note. The window cannot be
            # resolved while its opening is impossible.
            w["state"] = "unknown"
            notes.append(f"unresolved_from_{num}:{f!r}")
        if fc and w.get("state") == "resolved" and fc >= _validate_date(w["until"]):
            # round-4 finding 2: opening on/after its own closing: the window
            # evidence is self-contradictory. Never trust either endpoint.
            w["state"] = "unknown"
            contradictions.append(
                f"contradictory_window_{num}:opening {f} is not before closing {w['until']}")
        out.append(w)
    return out, notes, contradictions


def _bind_purchase(wt):
    """Assertion-level binding. Returns (purchased, purchased_as_of,
    unpaired_purchased, notes, contradictions).

    Per sentence: collect purchase assertions and as-of dates.
    - sentence with EXACTLY one purchase and one date and no favorites
      assertion -> paired.
    - sentence with purchase but no date -> unpaired (historical count kept
      honestly, no invented date).
    - ambiguous sentence (multiple purchases or dates) -> rejected entirely:
      recorded as unpaired with an ambiguity note, never first-match.

    Round-4 (Astra finding 2): two PAIRED observations that disagree are a
    CONTRADICTION, not a first-match-wins choice. The binder records which
    observations conflict and reports it via `contradictions`; parse() fails
    the record closed. Sentence order never decides trust.
    """
    notes = []
    contradictions = []
    paired = None
    unpaired = None
    bare_counts = []   # '\d+ times' continuations with no verb/date
    for sent in split_sentences(wt):
        # clause split: 'As of DATE, it was purchased N times and favorited M
        # times' is one sentence whose first clause carries the as-of date.
        # Binding is per-CLAUSE: a purchase pairs with a date only when both
        # live in the same clause. A favorites clause never lends its date.
        clauses = [c.strip() for c in re.split(r"\s+and\s+", sent) if c.strip()]
        clause_pairs = []
        clause_unpaired = []
        bare_counts = []   # '\d+ times' continuations with no verb/date
        for clause in clauses:
            purchases = RE_PURCHASE.findall(clause)
            dates = RE_ASOF.findall(clause)
            if not purchases:
                # bare continuation count ('..., and 200 times before that'):
                # a number+times with no purchase verb and no date. On its own
                # it binds nothing, but sharing a sentence with a paired count
                # it creates coverage ambiguity (round-4 finding 2).
                bare = re.search(r"\b([\d,]+)\s+times\b", clause)
                if bare and not dates:
                    bare_counts.append(int(bare.group(1).replace(",", "")))
                continue
            if RE_FAVORITED.search(clause):
                notes.append("purchase_in_favorites_clause:not paired")
                continue
            if len(purchases) == 1 and len(dates) == 1:
                clause_pairs.append((int(purchases[0].replace(",", "")), dates[0]))
            elif len(purchases) == 1 and not dates:
                clause_unpaired.append(int(purchases[0].replace(",", "")))
            else:
                notes.append(
                    f"ambiguous_clause:{len(purchases)} purchases, {len(dates)} dates; rejected")
        if len(clause_pairs) == 1:
            if paired is None:
                paired = clause_pairs[0]
            elif clause_pairs[0] != paired:
                # round-4 finding 2: disagreeing paired observations (e.g. two
                # as-of counts that don't fit one monotone history) are
                # unresolved contradictions; the record must not ship either.
                contradictions.append(
                    f"contradictory_purchase_observations:{paired} vs {clause_pairs[0]}")
            # equal duplicate restatement of the same observation: harmless
        elif len(clause_pairs) > 1:
            uniq = set(clause_pairs)
            if len(uniq) > 1:
                contradictions.append(
                    f"contradictory_purchase_observations:{sorted(uniq)} in one sentence")
            else:
                notes.append(f"duplicate_purchase_observation:{clause_pairs[0]}")
        if clause_unpaired and paired is None and not clause_pairs:
            if unpaired is None:
                unpaired = clause_unpaired[0]
    if paired and unpaired is not None:
        # a paired assertion supersedes unpaired counts in other sentences
        unpaired = None
    # round-4 finding 2: an unpaired count inside a sentence that ALSO carries a
    # paired observation ('100 times as of D1, and 200 times before that') is a
    # binding contradiction: the two counts cannot both describe the item's
    # displayed total, and the undated one cannot be positionally ordered.
    if paired and unpaired is not None:
        contradictions.append(
            f"contradictory_purchase_binding:{paired[0]} paired with date vs "
            f"{unpaired} undated in same context")
        unpaired = None
    if paired and bare_counts:
        contradictions.append(
            f"contradictory_purchase_binding:{paired[0]} paired with date vs "
            f"undated bare count(s) {bare_counts} in same sentence")
    return (paired + (unpaired, notes, contradictions) if paired else
            (None, None, unpaired, notes, contradictions))


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

    windows, wnotes, wcontras = extract_windows(wt)  # whole page: windows live in
    notes.extend(wnotes)                   # {{Availability history}}, not the infobox
    contradictions = list(wcontras)

    still = any(w["state"] == "open" for w in windows) or \
        (not windows and bool(RE_STILL.search(scope)))
    resolved = [w["until"] for w in windows if w["state"] == "resolved"]
    rec = {
        "item_id": int(m.group(1)) if m else None,
        "purchased": None,
        "purchased_as_of": None,
        "unpaired_purchased": None,
        "favorites": None,
        "favorites_as_of": None,
        "sale_state": "still_available" if still else ("closed" if resolved else "unknown"),
        "until": resolved[-1] if resolved else None,
        "until_history": [w["until"] if w["state"] == "resolved" else (w.get("until") or "Unknown")
                          for w in windows],
        # window MODEL (round-3): machine-readable, replaces string sniffing
        "windows": windows,
        "parse_ok": True,
        "parse_notes": notes,
    }

    # unresolved ANY window => finality can never be established from this page.
    # parse_ok=False makes the whole record fail closed downstream (eligibility,
    # merger, validator all refuse it).
    unresolved = [w for w in windows if w["state"] == "unknown"]
    if unresolved:
        rec["parse_ok"] = False
        for w in unresolved:
            rec["parse_notes"].append(
                f"unresolved_window_{w['index']}:finality not establishable")

    # unresolved {{Date|...}} template anywhere: page carries info we did not consume
    for t in re.findall(r"\{\{\s*Date\s*\|[^}]*\}\}", wt)[:3]:
        rec["parse_notes"].append("unresolved_date_template:" + t)
        rec["parse_ok"] = False

    # channel-scope STATUS (round-3): explicit unknown, never blacklist absence
    wt_norm = normalize_markup(wt)
    scope_status, scope_evidence = _channel_scope(wt_norm)
    rec["sale_channels"] = (
        ["marketplace", "experience"] if scope_status == "dual"
        else (["marketplace"] if scope_status == "single" else []))
    rec["purchase_count_scope"] = scope_status
    rec["scope_evidence"] = scope_evidence
    if scope_status == "dual":
        rec["parse_notes"].append(
            "multi_channel_sale:wiki count may cover one channel only")

    pc, pa, up, pnotes, pcontras = _bind_purchase(wt)
    rec["purchased"], rec["purchased_as_of"], rec["unpaired_purchased"] = pc, pa, up
    notes.extend(pnotes)
    contradictions.extend(pcontras)

    # Round-4 finding 2: contradictory evidence is RECORDED and ENFORCED. A
    # contradiction (duplicate differing window fields, opening after closing,
    # conflicting paired purchase observations) means the page cannot decide
    # which evidence to trust -> parse_ok=False, fail closed downstream.
    # Informational notes without conflict stay notes.
    rec["contradictions"] = contradictions
    if contradictions:
        rec["parse_ok"] = False
        notes.extend(contradictions)

    f = re.search(r"As of (" + DATE + r")[^.]*(?:been |was )?favorited ([\d,]+) times",
                  wt, re.I)
    if f:
        rec["favorites"], rec["favorites_as_of"] = int(f.group(2).replace(",", "")), f.group(1)
    else:
        f2 = re.search(r"(?:been |was )?favorited ([\d,]+) times[^.]*?[Aa]s of (" + DATE + r")",
                       wt, re.I)
        if f2:
            rec["favorites"], rec["favorites_as_of"] = int(f2.group(1).replace(",", "")), f2.group(2)
    rec["parse_notes"] = notes
    return rec
