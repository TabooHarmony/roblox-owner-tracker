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
    return errs
