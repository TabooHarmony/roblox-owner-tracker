"""Re-scrape all wiki anchor titles with the hardened parser (parse_wiki.py).
Writes anchors_harden_rescrape.jsonl with revision IDs pinned per record.

Run semantics (Astra 2.10): a run RESUMES only within the same run identity.
`--resume` continues an interrupted run (checkpoint = existing output tail,
repaired: a truncated final line is dropped before appending). WITHOUT
--resume, a fresh harvest starts a NEW run: existing output is moved aside
(<OUT>.prev) so seen titles are always re-fetched and refreshed - resume is
never silently treated as refresh.
"""
import json, sys, time, os
import urllib.request, urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import parse_wiki

# Repo-relative output; HARVEST_OUT_DIR env var overrides (dev tree points one level up).
ROOT = os.environ.get(
    "HARVEST_OUT_DIR",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
)
OUT = os.path.join(ROOT, "anchors_harden_rescrape.jsonl")
UA = "roblox-owner-tracker/0.2 (github.com/TabooHarmony/roblox-owner-tracker)"


def api(params, tries=3):
    url = "https://roblox.fandom.com/api.php?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for a in range(tries):
        try:
            j = json.loads(urllib.request.urlopen(req, timeout=30).read())
            if "error" in j:
                return ("API_ERROR", j["error"].get("code"))
            return ("OK", j)
        except Exception:
            time.sleep(2 + a * 3)
    return ("FAIL", None)


def done_titles():
    """Checkpoint = titles in complete (non-truncated) lines only. A truncated
    final line is dropped from consideration AND repaired on disk by the caller
    (Astra 2.10): it must not linger to corrupt the next append."""
    seen = set()
    if not os.path.exists(OUT):
        return seen
    with open(OUT) as f:
        lines = f.readlines()
    complete, tail = [], []
    for line in lines:
        try:
            json.loads(line)
            complete.append(line)
        except Exception:
            tail = [line]  # assume truncated tail; earlier lines already complete
    if tail and lines and tail[0] == lines[-1]:
        # repair: rewrite without the truncated final line
        with open(OUT, "w") as f:
            f.writelines(complete)
        print(f"repaired truncated checkpoint tail: {tail[0][:60]!r}", flush=True)
    for line in complete:
        try:
            seen.add(json.loads(line)["title"])
        except Exception:
            pass
    return seen


def main():
    if "--resume" not in sys.argv:
        # NEW RUN: never treat a stale checkpoint as refresh-complete (Astra 2.10)
        if os.path.exists(OUT):
            prev = OUT + ".prev"
            os.replace(OUT, prev)
            print(f"new run: checkpoint moved to {prev} (use --resume to continue it)", flush=True)
    # Title sources are always repo-internal; only OUT honors HARVEST_OUT_DIR.
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    titles = []
    for fn in ["anchors_wiki.jsonl", "anchors_wiki_extra.jsonl"]:
        for l in open(os.path.join(repo_root, "anchors", fn)):
            titles.append(json.loads(l)["title"])
    titles = sorted(set(titles))

    seen = done_titles()
    todo = [t for t in titles if t not in seen]
    print(f"total unique: {len(titles)} | done: {len(seen)} | todo: {len(todo)}", flush=True)

    batch_fail = 0
    start = time.time()
    with open(OUT, "a") as f:
        for i in range(0, len(todo), 10):
            batch = todo[i:i + 10]
            status, j = api({"action": "query", "prop": "revisions", "rvprop": "content|ids|timestamp",
                             "rvslots": "main", "titles": "|".join(batch),
                             "format": "json", "redirects": 1})
            if status != "OK":
                batch_fail += 1
                print(f"BATCH {i} FAIL: {j}", flush=True)
                continue
            for pid, p in j["query"]["pages"].items():
                if "revisions" not in p:
                    f.write(json.dumps({"title": p.get("title"), "missing": True}) + "\n")
                    continue
                rev = (p.get("revisions") or [{}])[0]
                wt = rev.get("slots", {}).get("main", {}).get("*") or rev.get("*") or ""
                rec = parse_wiki.parse(wt)
                rec["title"] = p.get("title")
                rec["rev_id"] = rev.get("revid")
                rec["rev_timestamp"] = rev.get("timestamp")
                f.write(json.dumps(rec) + "\n")
            f.flush()
            if (i // 10) % 100 == 0:
                el = time.time() - start
                print(f"{i + len(batch)}/{len(todo)} elapsed {el:.0f}s fail_batches={batch_fail}", flush=True)
            time.sleep(1.0)
    print(f"DONE in {time.time()-start:.0f}s fail_batches: {batch_fail}", flush=True)
    return 0 if batch_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
