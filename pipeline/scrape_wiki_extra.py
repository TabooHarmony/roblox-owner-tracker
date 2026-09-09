#!/usr/bin/env python3
"""Extra-category harvest for roblox.fandom.com catalog pages.
Scrapes wikitext for titles in harvest_titles.json (union of 7 main categories),
skips titles already in anchors_wiki.jsonl, appends to anchors_wiki_extra.jsonl
(resume-safe by title). Same extraction regexes as scrape_wiki.py, plus a
'N copies' fallback for limited items."""
import json, re, time, urllib.request, urllib.parse, os, sys

BASE = os.path.expanduser("~/roblox-owner-estimator")
OUT = f"{BASE}/anchors_wiki_extra.jsonl"
OLD = f"{BASE}/anchors_wiki.jsonl"
TITLES = sys.argv[1] if len(sys.argv) > 1 else f"{BASE}/harvest_titles.json"
UA = {"User-Agent": "OwnerCountResearch/1.0 (contact: research script)"}

def api(params, tries=5):
    url = "https://roblox.fandom.com/api.php?" + urllib.parse.urlencode(params)
    for a in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except Exception as e:
            time.sleep(5 * (a + 1))
    return None

RE_ID = re.compile(r"^\s*\|\s*id\s*=\s*(\d+)", re.M)
RE_ID_CAT = re.compile(r"^\s*\|\s*catalog id\s*=\s*(\d+)", re.M)  # Infobox bundle/dynamic head
RE_PUR = re.compile(r"been purchased ([\d,]+) times?")
RE_PUR2 = re.compile(r"purchased ([\d,]+) times")
RE_FAV = re.compile(r"favorited ([\d,]+) times")
RE_ASOF = re.compile(r"As of ([A-Z][a-z]+ \d{1,2}, \d{4})")
RE_UNTIL = re.compile(r"^\s*\|\s*until\s*=\s*(.+?)\s*$", re.M)
RE_COPIES = re.compile(r"\b([\d,]{1,8})\s+copies\b")

def parse(wt):
    m = RE_ID.search(wt) or RE_ID_CAT.search(wt)
    pur = RE_PUR.search(wt) or RE_PUR2.search(wt)
    fav = RE_FAV.search(wt)
    asof = RE_ASOF.search(wt)
    untils = RE_UNTIL.findall(wt)  # first = release history until (off-sale date)
    rec = {
        "item_id": int(m.group(1)) if m else None,
        "purchased": int(pur.group(1).replace(",", "")) if pur else None,
        "favorites": int(fav.group(1).replace(",", "")) if fav else None,
        "as_of": asof.group(1) if asof else None,
        "still_available": any("Still available" in u for u in untils),
        "until": untils[0].strip() if untils else None,
    }
    if rec["purchased"] is None:
        mc = RE_COPIES.search(wt)
        if mc:
            rec["purchased"] = int(mc.group(1).replace(",", ""))
    return rec

def done_titles():
    seen = set()
    for path in (OLD, OUT):
        if os.path.exists(path):
            with open(path) as f:
                for line in f:
                    try:
                        seen.add(json.loads(line)["title"])
                    except Exception:
                        pass
    return seen

catmap = json.load(open(TITLES))
order = ["Hair accessories", "Face accessories", "Faces obtained in the Marketplace",
         "Gear obtained in the Marketplace", "Bundles obtained in the Marketplace",
         "Dynamic head bundles", "Heads obtained in the Marketplace"]
seen = done_titles()
todo = [t for t in catmap if t not in seen]
print(f"union titles: {len(catmap)} | already done: {len(catmap)-len(todo)} | to do: {len(todo)}", flush=True)

cat_pages = {c: 0 for c in order}
rows_written = 0
rows_both = 0
parse_failures = 0

with open(OUT, "a") as f:
    for i in range(0, len(todo), 10):
        batch = todo[i:i+10]
        j = api({"action": "query", "prop": "revisions", "rvprop": "content",
                 "rvslots": "main", "titles": "|".join(batch),
                 "format": "json", "redirects": 1})
        if not j:
            print(f"batch {i} fetch fail, skipping", flush=True)
            continue
        for pid, p in j["query"]["pages"].items():
            if int(pid) < 0 or "revisions" not in p:
                continue
            rev = p["revisions"][0]
            wt = (rev.get("slots", {}).get("main", {}).get("*")
                  or rev.get("*") or "")
            rec = parse(wt)
            title = p["title"]
            rec = {"title": title, **rec, "src": "wiki"}
            f.write(json.dumps(rec) + "\n")
            rows_written += 1
            if rec["item_id"] is not None and rec["purchased"] is not None:
                rows_both += 1
            if rec["item_id"] is None and rec["purchased"] is None and \
               rec["favorites"] is None and rec["as_of"] is None:
                parse_failures += 1
            # attribute to first category for reporting
            for c in catmap.get(title, []):
                if c in cat_pages:
                    cat_pages[c] += 1
                    break
        f.flush()
        if (i // 10) % 25 == 0:
            print(f"progress: {i+len(batch)}/{len(todo)} rows={rows_written} "
                  f"both={rows_both} fails={parse_failures}", flush=True)
        time.sleep(1.0)

print("DONE", flush=True)
print(json.dumps({"categories": cat_pages, "rows_written": rows_written,
                  "rows_with_id_and_purchased": rows_both,
                  "parse_failures": parse_failures}), flush=True)
