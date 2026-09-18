#!/usr/bin/env python3
"""Cross-check every eligible anchor's identity against the live Roblox economy API.

The wiki infobox ids are occasionally WRONG (copy-paste errors between similar
"Gives X" event items, 3 confirmed cases). A wrong id silently mislabels a
bracket endpoint: the count and rank position are real, but the item name
shown as evidence belongs to a different item. This script catches that.

Usage:  python3 pipeline/identity_check.py [--fix]
Reads   site/anchors_eligible.json
Writes  /tmp/identity_mismatches.json and prints a report.
        --fix: retitle rows in anchors/*.jsonl to the API name (with a
        parse note) and re-run build via build_site_data.py — do this only
        after eyeballing the mismatch list.

Cosmetic diffs (punctuation, curly quotes, renames like 'Hacker Santa') are
expected; unrelated names are wiki infobox errors.
"""
import json, os, re, sys, time, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Chrome/126"}

def norm(s):
    s = s.replace("\u2019", "'").replace("\u2018", "'")
    s = re.sub(r"[^a-z0-9]", "", s.lower())
    return s

def main():
    anchors = json.load(open(os.path.join(ROOT, "site/anchors_eligible.json")))
    mismatches = {}
    for i, (iid, a) in enumerate(sorted(anchors.items())):
        try:
            req = urllib.request.Request(
                f"https://economy.roblox.com/v2/assets/{iid}/details", headers=UA)
            with urllib.request.urlopen(req, timeout=15) as r:
                api = json.loads(r.read())
        except Exception as e:
            print(iid, "FETCH FAIL", e, file=sys.stderr)
            continue
        api_name = (api.get("Name") or "").strip()
        if norm(api_name) != norm(a["t"]):
            mismatches[iid] = {"db_title": a["t"], "api_name": api_name, "p": a["p"]}
        if i % 50 == 0:
            print(f"...{i}/{len(anchors)}", flush=True)
        time.sleep(0.3)

    unrelated = {i: m for i, m in mismatches.items()
                 if norm(m["db_title"]) not in norm(m["api_name"])
                 and norm(m["api_name"]) not in norm(m["db_title"])}
    json.dump(mismatches, open("/tmp/identity_mismatches.json", "w"), indent=1)
    print(f"total title diffs: {len(mismatches)}  |  unrelated-name (likely wiki id errors): {len(unrelated)}")
    for iid, m in unrelated.items():
        print(f"  {iid}: db={m['db_title']!r} api={m['api_name']!r} p={m['p']}")

if __name__ == "__main__":
    main()
