"""Provenance-complete pool walker.

Walks a catalog pool via the v2 search XHR, recording per-page provenance:
cursor chain, fetched_utc, item count and raw-response sha256 for EVERY page,
plus started/finished timestamps. Output satisfies pool_manifest.validate.

Usage: python3 walk_pools.py <targets.json>
targets.json: [{"name": ..., "out": "pools/x_wrapped.json", "query": {...}}, ...]
"""
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pool_manifest  # noqa: E402

UA = "roblox-owner-tracker/0.3 (github.com/TabooHarmony/roblox-owner-tracker)"
SEARCH = "https://catalog.roblox.com/v2/search/items/details"
PAGE_DELAY_S = 6.5  # polite pacing; 429s observed at 1s (skill doctrine)


def now_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch(params):
    url = SEARCH + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    last = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            last = e
            if e.code == 429:
                time.sleep(15 + attempt * 15)  # observed clear time
                continue
            raise
    raise RuntimeError(f"fetch failed after retries: {last}")


MAX_PAGES = 40  # 120/page * 40 >> the ~1000-item serving cap; runaway guard


def walk(query, keyword_for_log):
    """Walk one pool. Returns (blob, ok, reason). complete=True ONLY on a walk
    that exhausted the cursor chain with every page populated (Astra 2.4):
    an empty page WITH a continuation cursor is drift/malformation, not
    exhaustion; repeating cursors are a cycle -> bounded failure."""
    params = dict(query)
    params.setdefault("Limit", 120)  # API caps ~110-120 regardless; walk via cursor
    pages, ids, seen = [], [], set()
    cursor = ""  # the cursor ACTUALLY used for the next request
    started = now_utc()
    ok, reason = False, "unreachable"
    while True:
        if len(pages) >= MAX_PAGES:
            reason = f"page budget exceeded ({MAX_PAGES}); cursor chain never ended"
            break
        p = dict(params)
        if cursor:
            p["Cursor"] = cursor
        status, raw = fetch(p)
        j = json.loads(raw)
        body = j.get("data") or []
        next_cursor = j.get("nextPageCursor") or ""
        pages.append({
            "cursor": cursor,      # request cursor ("" = first page)
            "next_cursor": next_cursor,
            "fetched_utc": now_utc(),
            "count": len(body),
            "raw_response_sha256": hashlib.sha256(raw).hexdigest(),
        })
        for it in body:
            i = it.get("id")
            if i is not None:
                ids.append(str(i))
                seen.add(str(i))
        if not next_cursor:
            ok, reason = True, "cursor exhausted"  # valid termination
            break
        if not body:
            # empty page WITH continuation: malformed/aborted serving, not exhaustion
            ok, reason = False, f"empty page {len(pages)} with continuation cursor; walk incomplete"
            break
        if next_cursor in {pg["cursor"] for pg in pages} or \
                next_cursor in {pg["next_cursor"] for pg in pages[:-1]}:
            ok, reason = False, f"cursor cycle detected at page {len(pages)}"
            break
        cursor = next_cursor
        time.sleep(PAGE_DELAY_S)
    finished = now_utc()
    manifest = pool_manifest.make_manifest(
        params, pages, started, finished, ok, ids,
        notes=[f"keyword={keyword_for_log}"] + ([] if ok else [f"incomplete:{reason}"]))
    return {"manifest": manifest, "item_ids": ids}, ok, reason


def main():
    targets = json.load(open(sys.argv[1]))
    failed = False
    for t in targets:
        out = t["out"]
        print(f"walking {t['name']} -> {out}", flush=True)
        blob, ok, reason = walk(t["query"], t.get("name", ""))
        errs = pool_manifest.validate(blob["manifest"])
        if not ok or errs:
            # never publish a pool that is not a proven, complete walk
            print(f"  FAIL: {reason or errs}", flush=True)
            failed = True
            continue  # keep walking other targets; exit nonzero at the end
        tmp = out + ".tmp"
        with open(tmp, "w") as f:
            json.dump(blob, f)
        os.replace(tmp, out)
        print(f"  n={len(blob['item_ids'])} pages={len(blob['manifest']['pages'])} ok", flush=True)
    if failed:
        raise SystemExit("one or more walks failed validation; pools NOT updated")


if __name__ == "__main__":
    main()
