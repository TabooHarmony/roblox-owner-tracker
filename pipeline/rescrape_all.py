"""Re-scrape all wiki anchor titles with the hardened parser (parse_wiki.py).
Writes anchors_harden_rescrape.jsonl with revision IDs pinned per record.
Resume-safe: skips titles already present in the output file.
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
    seen = set()
    if os.path.exists(OUT):
        with open(OUT) as f:
            for line in f:
                try:
                    seen.add(json.loads(line)["title"])
                except Exception:
                    pass
    return seen


def main():
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
