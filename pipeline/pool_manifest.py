"""Pool walk provenance manifest. Every saved pool MUST carry this header.

A pool without a complete manifest is rejected by the estimator: a walk whose
pages were served from inconsistent shards is not one ranking, and dedupe
cannot prove otherwise.
"""
import json


def make_manifest(query_params, pages, started_utc, finished_utc, complete,
                  item_ids, notes=None):
    """query_params: exact request params (keyword, sortType, salesTypeFilter,
    IncludeNotForSale, taxonomy, limit, cursor chain).
    pages: list of per-page dicts {cursor, fetched_utc, count, raw_response_sha256}.
    complete: False if any page failed / walk aborted mid-way.
    item_ids: the final ordered id list."""
    return {
        "manifest_version": 1,
        "query": query_params,
        "pages": pages,
        "started_utc": started_utc,
        "finished_utc": finished_utc,
        "complete": complete,
        "n_items": len(item_ids),
        "n_duplicate_ids": len(item_ids) - len(set(item_ids)),
        "notes": notes or [],
        "reject_if": {
            "not_complete": "incomplete walks are not rankings - abstain, do not estimate",
            "duplicate_ids_gt_1pct": "server-side mutation mid-walk; treat walk as invalid",
        },
    }


def validate(manifest):
    errs = []
    if not manifest.get("complete"):
        errs.append("incomplete walk")
    if manifest.get("n_duplicate_ids", 0) > manifest.get("n_items", 0) * 0.01:
        errs.append("duplicate ratio exceeds 1%")
    for i, p in enumerate(manifest.get("pages", [])):
        for k in ("cursor", "fetched_utc", "count"):
            if k not in p:
                errs.append(f"page {i} missing {k}")
    return errs
