# roblox-owner-tracker

Tracks and estimates Roblox catalog item sales (owner counts) that Roblox itself no longer publishes.

**Method credit: [Maggy (Maggy Rarefication)](https://www.youtube.com/watch?v=7a-ViNgReAo)** — the rank-bracketing technique this project automates is Maggy's discovery, described in ["How To Estimate The Amount Of Sales A Roblox Item Has"](https://www.youtube.com/watch?v=7a-ViNgReAo) (Jan 2025). This repo turns that manual method into a deterministic pipeline.

## How it works

Roblox removed public owner counts from the catalog. The wiki (roblox.fandom.com) records purchase counts for many items, but only as of whenever a wiki editor last updated the page — and pages stop being updated once an item goes off sale.

The method: catalog search orders items by sales (best-selling sort, off-sale items included). Take the item you care about, find where it sits in that ordering, and read the wiki purchase counts of the nearest *closed-final* neighbors (items whose sale ended, so their wiki number is final). Those two numbers bracket the target's true sales.

Pools are built with a keyword + rainbow-color padding recipe (`red orange yellow green blue pink white`), which keeps the neighborhood same-era and locally ordered by sales. Items are resolved by catalog ID, never by name string.

## What's in here

- `anchors/` — the wiki anchor database (JSONL): title, item ID, purchased count, favorites, as-of date, off-sale date. ~16k unique titles, ~8k with purchase counts.
- `estimates/` — bracketed estimates with provenance for each target item.
- `pipeline/` — deterministic scripts: wiki harvester, pool walker, bracket engine with runtime guards.

## Known limits (measured, not guessed)

- **Search serving is non-deterministic across days.** Pool walks that are byte-identical within a day can be nearly disjoint a day later. Brackets are snapshot-local: valid when computed, stamped with a date, never diffed across time.
- **SortType=2 is only approximately sales-ordered.** ~17% of closed-final anchor pairs locally invert, mostly from era-mixing. Guards: anchors must have a recorded off-sale date of 2012+, pre-2012 wiki snapshots rejected, brackets wider than ~4x flagged low-confidence.
- **Search results cap at ~920–1000 items per query.** This is a serving window, not the full universe. Hat accessories and gear (huge categories) can't be fully browsed without keywords.
- **Favorites are useless for estimating sales.** Measured across 31 double-annotated anchors: purchase/favorite ratio spans 0.23–36.8. Favorites track attention, not conversion.
- **Limited-unique items count resales** in their owner figures — poor anchors unless very new.

## License

MPL-2.0. Wiki data sourced from [roblox.fandom.com](https://roblox.fandom.com) (CC-BY-SA); used with attribution.
