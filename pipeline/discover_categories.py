#!/usr/bin/env python3
"""Discover relevant categories on roblox.fandom.com.
1) list=allcategories with page counts (acprop=size)
2) for a sample of pages containing 'been purchased', list their categories
   and rank by how often they co-occur with purchase language."""
import json, re, time, urllib.request, urllib.parse, collections, sys

UA = {"User-Agent": "OwnerCountResearch/1.0 (contact: research script)"}

def api(params, tries=5):
    url = "https://roblox.fandom.com/api.php?" + urllib.parse.urlencode(params)
    for a in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except Exception as e:
            print("api err", e, flush=True)
            time.sleep(5 * (a + 1))
    return None

# 1) all categories with size
cats = {}
cont = {}
while True:
    j = api({"action": "query", "list": "allcategories", "acprop": "size",
             "acmin": 5, "aclimit": 5000, "format": "json", **cont})
    if not j:
        print("ALLCATS FAIL"); sys.exit(1)
    for c in j["query"]["allcategories"]:
        cats[c["*"]] = c["size"]
    cont = j.get("continue")
    if not cont:
        break
    cont = {"acfrom": cont["accontinue"]}
    time.sleep(1.0)

print(f"total categories (>=5 pages): {len(cats)}", flush=True)

# 2) sample pages whose wikitext contains 'been purchased', collect their categories
purchased_pages = []
cont = {}
while len(purchased_pages) < 2000:
    j = api({"action": "query", "list": "search", "srsearch": "intext:\"been purchased\"",
             "srnamespace": 0, "srlimit": 500, "format": "json", **cont})
    if not j:
        break
    purchased_pages += [s["title"] for s in j["query"]["search"]]
    cont = j.get("continue")
    if not cont:
        break
    cont = {"sroffset": cont["sroffset"]}
    time.sleep(1.0)

print(f"sample pages with 'been purchased': {len(purchased_pages)}", flush=True)

cat_hits = collections.Counter()
total_hits = 0
for i in range(0, len(purchased_pages), 50):
    batch = purchased_pages[i:i+50]
    j = api({"action": "query", "prop": "categories", "cllimit": "max",
             "titles": "|".join(batch), "format": "json", "redirects": 1})
    if not j:
        continue
    for p in j["query"]["pages"].values():
        if "categories" not in p:
            continue
        total_hits += 1
        for c in p["categories"]:
            cat_hits[c["title"]] += 1
    time.sleep(1.0)

# relevance: category name hints + appears on purchase pages
HINTS = re.compile(r"(hair|face|bundle|head|gear|event|hat|marketplace|accessor|furnitur|decal|emote|shirt|pant|t-shirt|ear|wing|crown|dominus|valk)", re.I)
rows = []
for cat, n in cat_hits.most_common():
    name = cat.replace("Category:", "")
    if name in ("Categories",):
        continue
    hint = bool(HINTS.search(name))
    if hint or n >= 50:
        rows.append((name, n, cats.get(name, 0), hint))

with open("/root/roblox-owner-estimator/discovered_categories.json", "w") as f:
    json.dump({"all_cats": cats, "purchased_sample": len(purchased_pages),
               "ranked": [{"name": n, "purchased_hits": h, "size": s, "hint": hh} for n, h, s, hh in rows]}, f, indent=1)
print("wrote discovered_categories.json", flush=True)
print(f"pages sampled w/ cats: {total_hits}", flush=True)
for name, n, s, hh in rows[:80]:
    print(f"{name}\t purchased_sample={n}\t size={s}\t hint={hh}", flush=True)
