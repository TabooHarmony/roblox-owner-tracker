# roblox-owner-tracker

Deterministic owner-count bracketing for limited Roblox catalog items, using
wiki-documented purchase counts of neighboring items as anchors. No LLM in the
loop: every step is a plain script with pinned inputs.

Method origin: the bestseller/rainbow-anchor approach was invented and documented
by **Maggy (Maggy Rarefication)**. This repo is a deterministic reimplementation
of her method; the anchors dataset and tooling are ours, the idea is hers.

## Status: EXPERIMENTAL — uncalibrated

This is **not** a trusted estimator yet. The intervals are rank-neighbor
heuristics, not confidence bounds. Known limits (measured, see
`docs/VALIDATION.md`):

- ~17% of adjacent anchor pairs are locally inverted (the wiki purchase counts
  do not perfectly respect search-rank ordering).
- Anchor agreement does **not** prove the target lies between them. Two anchors
  can agree while the target sits far outside their interval; nothing in the
  method detects this.
- No held-out coverage study exists yet. Until one does, every interval here is
  a lead for manual investigation, not a measurement.

The engine therefore **abstains** instead of guessing: a target not in the pool
snapshot, with no eligible anchors, or with conflicting pools produces an
explicit `ABSTAIN` record with a reason — never a made-up interval.

## Repo layout

    pipeline/parse_wiki.py      hardened wikitext -> anchor record parser
    pipeline/bracket.py         pool walk + rank-bracket engine with abstention
    pipeline/rescrape_all.py    full wiki re-harvest (resume-safe, rev-pinned)
    pipeline/rescrape_delta.py  delta re-harvest (rows lacking purchase info)
    pipeline/backfill_rev.py    pin revision IDs onto existing records
    pipeline/run.sh             CLI entry point: fetch/parse/bracket/validate
    anchors/                    anchor database (JSONL, schema v2)
    pools/                      pool-walk manifests (provenance + item IDs)
    estimates/                  bracket outputs (JSONL, schema 2, snapshot-dated)
    tests/                      offline fixture tests (no network)
    .github/workflows/          scheduled re-harvest + reproducibility CI

## Reproduce

    git clone https://github.com/TabooHarmony/roblox-owner-tracker
    cd roblox-owner-tracker
    pipeline/run.sh tests        # offline fixture tests, no network
    pipeline/run.sh validate     # schema-validate anchors + estimates

Full re-harvest (network, ~35 min, resumable):

    pipeline/run.sh harvest

Every anchor record pins the wiki revision ID it was parsed from, so any
published estimate can be traced to the exact page revision it used.

## Schema

Anchor record (anchors/*.jsonl): `title, item_id, purchased, purchased_as_of,
unpaired_purchased, favorites, favorites_as_of, sale_state (still_available |
closed | unknown), until, until_history, rev_id, rev_timestamp, parse_ok,
parse_notes`.

Parser rules that matter:

- Purchase/favorite counts are kept ONLY when paired with an `As of <date>` in
  the same or the immediately following sentence. Unpaired counts are stored
  separately (`unpaired_purchased`) as lower-bound candidates, never used as
  exact anchors. The old "N copies available" fallback is gone: copies
  available is not copies sold.
- Availability is case-insensitive and 3-state. `Still available` and
  `Still Available` are the same thing; the old harvesters disagreed and misfiled
  6,256 rows because of a capital letter.
- All `until` rows are kept (`until_history`); a re-opened item's last date
  wins. HTML comments are stripped before any extraction.

Estimate record (estimates/*.jsonl, schema 2): `schema, item, item_id,
snapshot_utc, pool, status (ESTIMATE | ABSTAIN), confidence, bracket, warnings,
anchors{above,below}, quantity, note, abstain_reason`.

## License

MPL-2.0. See LICENSE.
