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


def walk(query, keyword_for_log):
    params = dict(query)
    params.setdefault("Limit", 120)  # API caps ~110-120 regardless; walk via cursor
    pages, ids, seen = [], [], set()
    cursor = ""
    started = now_utc()
    while True:
        p = dict(params)
        if cursor:
            p["Cursor"] = cursor
        status, raw = fetch(p)
        j = json.loads(raw)
        body = j.get("data") or []
        pages.append({
            "cursor": cursor,
            "fetched_utc": now_utc(),
            "count": len(body),
            "raw_response_sha256": hashlib.sha256(raw).hexdigest(),
        })
        for it in body:
            i = it.get("id")
            if i is not None:
                ids.append(str(i))
                seen.add(str(i))
        cursor = j.get("nextPageCursor") or ""
        if not cursor or not body:
            break
        time.sleep(PAGE_DELAY_S)
    finished = now_utc()
    return {
        "manifest": pool_manifest.make_manifest(
            params, pages, started, finished, True, ids,
            notes=[f"keyword={keyword_for_log}"]),
        "item_ids": ids,
    }


def main():
    targets = json.load(open(sys.argv[1]))
    for t in targets:
        out = t["out"]
        print(f"walking {t['name']} -> {out}", flush=True)
        blob = walk(t["query"], t.get("name", ""))
        errs = pool_manifest.validate(blob["manifest"])
        if errs:
            # never write a pool that would fail its own gate
            raise SystemExit(f"{out}: walk produced invalid manifest: {errs}")
        with open(out, "w") as f:
            json.dump(blob, f)
        print(f"  n={len(blob['item_ids'])} pages={len(blob['manifest']['pages'])} ok", flush=True)


if __name__ == "__main__":
    main()
