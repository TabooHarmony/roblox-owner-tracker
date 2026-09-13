"""Pool walk provenance manifest. Every saved pool MUST carry this header.

A pool without a complete manifest is rejected by the estimator: a walk whose
pages were served from inconsistent shards is not one ranking, and dedupe
cannot prove otherwise.
"""
import hashlib
import json


def make_manifest(query_params, pages, started_utc, finished_utc, complete,
                  item_ids, notes=None):
    """query_params: exact request params (keyword, sortType, salesTypeFilter,
    IncludeNotForSale, taxonomy, limit, cursor chain).
    pages: list of per-page dicts {cursor, next_cursor, fetched_utc, count,
    raw_response_sha256}.
    complete: False if any page failed / walk aborted mid-way.
    item_ids: the final ordered id list."""
    return {
        "manifest_version": 2,
        "query": query_params,
        "pages": pages,
        "started_utc": started_utc,
        "finished_utc": finished_utc,
        "complete": complete,
        "n_items": len(item_ids),
        "n_duplicate_ids": len(item_ids) - len(set(item_ids)),
        "item_ids_sha256": hashlib.sha256(
            json.dumps(item_ids).encode()).hexdigest(),
        "notes": notes or [],
        "reject_if": {
            "not_complete": "incomplete walks are not rankings - abstain, do not estimate",
            "duplicate_ids": "any duplicate id means the ranking moved mid-walk; invalid",
        },
    }


def validate(manifest, item_ids=None):
    """Validate a pool manifest. If item_ids (the pool blob's stored list) is
    given, the recorded digest is CHECKED against the actual content - a hash
    nobody verifies proves nothing (Astra 2.3). Duplicates of ANY size fail:
    duplicate occurrences mean the ranking moved mid-walk, so positions are
    ambiguous and self-bracketing becomes possible (Astra 2.5)."""
    errs = []
    if manifest.get("manifest_version") != 2:
        errs.append(f"unsupported manifest_version: {manifest.get('manifest_version')!r}")
    q = manifest.get("query") or {}
    # Roblox API casing is SortType/SortAggregation; accept either casing but REQUIRE both
    keys = {k.lower(): k for k in q}
    if "sorttype" not in keys:
        errs.append("query missing SortType (explicit ordering semantics required)")
    if "sortaggregation" not in keys:
        errs.append("query missing SortAggregation (explicit aggregation semantics required; "
                    "do not rely on an undocumented default - Astra 1.2)")
    # sort values must be present and non-null (round-3 5B: null sort accepted)
    for label in ("sorttype", "sortaggregation"):
        k = keys.get(label)
        if k is not None and q[k] is None:
            errs.append(f"query {k} is null: ordering semantics undefined")
    if not manifest.get("complete"):
        errs.append("incomplete walk")
    pages = manifest.get("pages", [])
    if manifest.get("complete") and not pages:
        errs.append("complete=true but pages list is empty (no per-page provenance)")
    if manifest.get("complete") and not manifest.get("finished_utc"):
        errs.append("complete=true but no finished_utc (snapshot timestamp required)")
    if manifest.get("complete") and not manifest.get("started_utc"):
        errs.append("complete=true but no started_utc")
    if manifest.get("complete") and pages:
        if not any(p.get("count") for p in pages):
            errs.append("pages present but all have count=0/missing")
        # FIRST page must have been fetched with the EMPTY cursor (round-3 5B):
        # a supplied initial Cursor skips a prefix of the ranking; the walk is
        # then not the full ordering the manifest claims.
        if pages[0].get("cursor") != "":
            errs.append("page 0: initial request cursor is not empty "
                        f"({pages[0].get('cursor')!r}); walk skipped a ranking prefix")
        # cursor chain must be faithful: page i+1's request cursor is page i's next_cursor
        for i in range(1, len(pages)):
            if pages[i].get("cursor") != pages[i - 1].get("next_cursor"):
                errs.append(f"page {i}: request cursor does not continue page {i-1}'s next_cursor")
        for i, p in enumerate(pages):
            if p.get("next_cursor") and p.get("count", 0) == 0:
                errs.append(f"page {i}: empty page with continuation (marked complete anyway?)")
            for k in ("cursor", "next_cursor", "fetched_utc", "count", "raw_response_sha256"):
                if k not in p:
                    errs.append(f"page {i} missing {k}")
            # count must be a real nonnegative int, never null/None (round-3 5B:
            # a mocked errors-object page defaulted missing fields to empty and
            # passed as successful exhaustion)
            c = p.get("count")
            if not isinstance(c, int) or isinstance(c, bool) or c < 0:
                errs.append(f"page {i}: count must be a nonnegative integer, got {c!r}")
    # terminal page must END the chain (round-3 5B: nonempty terminal cursor passed)
    if manifest.get("complete") and pages and pages[-1].get("next_cursor"):
        errs.append("complete=true but the last page still has a next_cursor "
                    "(walk did not exhaust the ranking)")
    if manifest.get("n_items", 0) == 0:
        errs.append("manifest records zero items")
    if manifest.get("n_duplicate_ids", 0) > 0:
        errs.append(f"{manifest.get('n_duplicate_ids')} duplicate ids: ranking moved mid-walk; invalid")
    # digest check against the ACTUAL stored ids
    if item_ids is not None:
        if manifest.get("n_items") != len(item_ids):
            errs.append(f"n_items={manifest.get('n_items')} but pool holds {len(item_ids)} ids")
        actual = hashlib.sha256(json.dumps([str(x) for x in item_ids]).encode()).hexdigest()
        if manifest.get("item_ids_sha256") != actual:
            errs.append("item_ids_sha256 does not match stored pool ids (substituted/edited list)")
    # Round-4 finding 5a: a walk that started with a SUPPLIED cursor skips a
    # ranking prefix. The walker must record the cursor it ACTUALLY sent for
    # page 0 (request_cursor) separately from any echoed response cursor; a
    # manifest claiming cursor="" without that evidence is rejected.
    if manifest.get("complete") and pages:
        for i, p in enumerate(pages):
            if "request_cursor" not in p:
                errs.append(f"page {i} missing request_cursor (the cursor actually "
                            f"sent for this request; without it a skipped ranking "
                            f"prefix is undetectable)")
            elif i == 0 and p["request_cursor"] not in ("", None):
                errs.append(f"page 0 request_cursor={p['request_cursor']!r}: "
                            f"walk started mid-ranking (supplied initial cursor)")
    # Round-4 finding 5b: completion requires positive evidence. A page whose
    # HTTP body was an errors object ({"errors":[...]}) is NOT successful
    # exhaustion; treat recorded error bodies as walk failure.
        for i, p in enumerate(pages):
            if p.get("response_errors") or p.get("http_status") not in (None, 200):
                errs.append(f"page {i}: page not successfully fetched "
                            f"(response_errors={p.get('response_errors')!r}, "
                            f"http_status={p.get('http_status')!r}); walk did not "
                            f"exhaust the ranking successfully")
    # Round-4 finding 5c: page hashes must bind to reconstructable response
    # content. Each page stores response_sha256 over its canonical id list;
    # reordering ids and refreshing only the aggregate digest must fail.
    if item_ids is not None and manifest.get("complete") and pages:
        # ids are appended in walk order; verify per-page id-count consistency
        # and that per-page digests exist and are checked by the walker's
        # rehash step (raw_response_sha256 alone is unbound).
        pos = 0
        for i, p in enumerate(pages):
            n = p.get("count") or 0
            if not isinstance(n, int) or n < 0:
                break
            if "page_ids_sha256" not in p:
                errs.append(f"page {i} missing page_ids_sha256 (per-page digest "
                            f"binding ids to walk order; aggregate digest alone "
                            f"cannot detect reordering)")
            else:
                seg = [str(x) for x in item_ids[pos:pos + n]]
                seg_digest = hashlib.sha256(json.dumps(seg).encode()).hexdigest()
                if seg_digest != p["page_ids_sha256"]:
                    errs.append(f"page {i} page_ids_sha256 does not match the ids "
                                f"it claims to cover (ids reordered/edited after walk)")
            pos += n
        if pos != len(item_ids):
            errs.append(f"page counts sum to {pos} but pool holds {len(item_ids)} ids")
    return errs
