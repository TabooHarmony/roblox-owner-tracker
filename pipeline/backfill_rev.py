"""Backfill rev_id/rev_timestamp for rescraped anchors (ids-only API pass, cheap)."""
import json, time, os, sys
import urllib.request, urllib.parse

OUT = "/root/roblox-owner-estimator/anchors_harden_rescrape.jsonl"
UA = "roblox-owner-tracker/0.2 (github.com/TabooHarmony/roblox-owner-tracker)"

def api(params, tries=3):
    url = "https://roblox.fandom.com/api.php?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for a in range(tries):
        try:
            return json.loads(urllib.request.urlopen(req, timeout=30).read())
        except Exception:
            time.sleep(2 + a * 3)
    return None

rows = [json.loads(l) for l in open(OUT)]
by_title = {}
for r in rows:
    if not r.get("missing") and not r.get("rev_id"):
        by_title[r["title"]] = r
print(f"rows: {len(rows)}, need rev backfill: {len(by_title)}")
titles = list(by_title)
fixed = 0
for i in range(0, len(titles), 50):  # ids+timestamp only: 50/batch is fine
    batch = titles[i:i+50]
    j = api({"action":"query","prop":"revisions","rvprop":"ids|timestamp",
             "titles":"|".join(batch),"format":"json"})
    if not j: continue
    for pid, p in j["query"]["pages"].items():
        rev = (p.get("revisions") or [{}])[0]
        r = by_title.get(p.get("title"))
        if r and rev.get("revid"):
            r["rev_id"] = rev["revid"]; r["rev_timestamp"] = rev.get("timestamp"); fixed += 1
    if (i//50) % 20 == 0: print(f"{i}/{len(titles)} fixed={fixed}", flush=True)
    time.sleep(0.5)
with open(OUT, "w") as f:
    for r in rows:
        f.write(json.dumps(r) + "\n")
print(f"DONE fixed={fixed}")
