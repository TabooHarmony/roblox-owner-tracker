#!/usr/bin/env python3
"""Scrape roblox.fandom.com Catalog pages -> anchor DB (JSONL).
Extracts: item id, purchased count, as-of date, favorites, off-sale status.
Append-safe: skips titles already in output. ~10 titles per API call."""
import json, re, time, urllib.request, urllib.parse, os, sys

OUT = os.path.expanduser("~/roblox-owner-estimator/anchors_wiki.jsonl")
CAT = "Category:Accessories_obtained_in_the_Marketplace"
UA = {"User-Agent": "OwnerCountResearch/1.0 (contact: research script)"}

def api(params, tries=4):
    url = "https://roblox.fandom.com/api.php?" + urllib.parse.urlencode(params)
    for a in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except Exception as e:
            time.sleep(5 * (a + 1))
    return None

def done_titles():
    seen = set()
    if os.path.exists(OUT):
        with open(OUT) as f:
            for line in f:
                try: seen.add(json.loads(line)["title"])
                except Exception: pass
    return seen

# 1) list all category members
titles = []
cont = {}
while True:
    j = api({"action": "query", "list": "categorymembers", "cmtitle": CAT,
             "cmtype": "page", "cmlimit": 500, "format": "json", **cont})
    if not j: print("LIST FAIL", flush=True); sys.exit(1)
    titles += [m["title"] for m in j["query"]["categorymembers"]]
    cont = j.get("continue")
    if not cont: break
    cont = {"cmcontinue": cont["cmcontinue"]}
print(f"total pages in category: {len(titles)}", flush=True)

seen = done_titles()
todo = [t for t in titles if t not in seen]
print(f"already scraped: {len(seen)} | to do: {len(todo)}", flush=True)

RE_ID = re.compile(r"^\s*\|\s*id\s*=\s*(\d+)", re.M)
RE_PUR = re.compile(r"been purchased ([\d,]+) times?")
RE_PUR2 = re.compile(r"purchased ([\d,]+) times")
RE_FAV = re.compile(r"favorited ([\d,]+) times")
RE_ASOF = re.compile(r"As of ([A-Z][a-z]+ \d{1,2}, \d{4})")
RE_UNTIL = re.compile(r"^\s*\|\s*until\s*=\s*(.+?)\s*$", re.M)

with open(OUT, "a") as f:
    for i in range(0, len(todo), 10):
        batch = todo[i:i+10]
        j = api({"action": "query", "prop": "revisions", "rvprop": "content",
                 "rvslots": "main", "titles": "|".join(batch),
                 "format": "json", "redirects": 1})
        if not j:
            print(f"batch {i} fetch fail", flush=True); continue
        for pid, p in j["query"]["pages"].items():
            if "revisions" not in p: continue
            rev = p["revisions"][0]
            wt = (rev.get("slots", {}).get("main", {}).get("*")
                  or rev.get("*") or "")
            m = RE_ID.search(wt)
            pur = RE_PUR.search(wt) or RE_PUR2.search(wt)
            fav = RE_FAV.search(wt)
            asof = RE_ASOF.search(wt)
            until = RE_UNTIL.search(wt)
            rec = {
                "title": p["title"],
                "item_id": int(m.group(1)) if m else None,
                "purchased": int(pur.group(1).replace(",", "")) if pur else None,
                "favorites": int(fav.group(1).replace(",", "")) if fav else None,
                "as_of": asof.group(1) if asof else None,
                "still_available": bool(until and "Still Available" in until.group(1)),
                "until": until.group(1).strip() if until else None,
            }
            f.write(json.dumps(rec) + "\n")
        f.flush()
        if (i // 10) % 20 == 0:
            print(f"progress: {i+len(batch)}/{len(todo)}", flush=True)
        time.sleep(1.0)

print("DONE", flush=True)
