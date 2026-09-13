"""Delta re-fetch: only pages whose hardened parse found NO purchase info at all.
Many use the wiki's 'it was purchased N times' phrasing, which the first hardened
pass missed ('been purchased' only). Saves the raw wikitext this time so future
parser fixes never require re-fetching.
"""
import json, os, sys, time, urllib.request, urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import parse_wiki

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..","..","anchors_delta_raw.jsonl")
DONE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..","..","anchors_delta_parsed.jsonl")
SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..","..","anchors_harden_rescrape.jsonl")
API = "https://roblox.fandom.com/api.php"


def api(params):
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "roblox-owner-tracker/0.2 (deterministic wiki harvest)"})
    for attempt in range(4):
        try:
            return json.loads(urllib.request.urlopen(req, timeout=30).read())
        except Exception:
            time.sleep(2 * (attempt + 1))
    return {}


def main():
    done_titles = set()
    if os.path.exists(DONE):
        for l in open(DONE):
            done_titles.add(json.loads(l)["title"])
    todo = []
    for l in open(SRC):
        r = json.loads(l)
        if r["title"] in done_titles:
            continue
        if r["purchased"] is None and r["unpaired_purchased"] is None:
            todo.append(r["title"])
    print(f"delta titles: {len(todo)}", flush=True)

    with open(OUT, "a") as fraw, open(DONE, "a") as fpar:
        for i in range(0, len(todo), 10):
            batch = todo[i:i + 10]
            j = api({"action": "query", "prop": "revisions", "rvprop": "content|ids|timestamp",
                     "rvslots": "main", "titles": "|".join(batch), "format": "json"})
            for p in (j.get("query", {}).get("pages") or {}).values():
                if "revisions" not in p:
                    continue
                rev = p["revisions"][0]
                wt = rev.get("slots", {}).get("main", {}).get("*") or ""
                rec = parse_wiki.parse(wt)
                rec["title"] = p["title"]
                rec["rev_id"] = rev.get("revid")
                rec["rev_timestamp"] = rev.get("timestamp")
                fpar.write(json.dumps(rec) + "\n")
                fraw.write(json.dumps({"title": p["title"], "revid": rev.get("revid"), "wt": wt}) + "\n")
            fraw.flush()
            fpar.flush()
            if (i // 10) % 100 == 0:
                print(f"{i}/{len(todo)}", flush=True)
            time.sleep(1.0)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
