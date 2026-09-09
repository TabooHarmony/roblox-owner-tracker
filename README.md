# roblox-owner-tracker

Deterministic purchase-count bracketing for limited Roblox catalog items, using
wiki-documented purchase counts of neighboring items as anchors. No LLM in the
loop: every step is a plain script with pinned inputs.

Despite the repo name, the measured quantity is **estimated lifetime purchases
of the original item** — not copies, not distinct current owners (Roblox
documents resale and multi-copy ownership; those are different quantities).
Every estimate row carries this statement in its `quantity` field, plus
`method: rank_neighbor_heuristic` and `calibration_status: uncalibrated`.

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
- The held-out coverage study (C/A ≈ 88-95%) measures internal consistency of
  the shipped dataset, not agreement with platform ground truth.
- Width is width, not confidence: a narrow interval can be precisely wrong.

The engine therefore **abstains** instead of guessing: a target not in the pool
snapshot, with no eligible anchors, or with conflicting pools produces an
explicit `ABSTAIN` record with a reason — never a made-up interval.

## Repo layout

    pipeline/parse_wiki.py      hardened wikitext -> anchor record parser
    pipeline/bracket.py         pool walk + rank-bracket engine with abstention
    pipeline/parse_wiki.py      hardened wikitext -> anchor record parser
    pipeline/bracket.py         rank-bracket engine with abstention
    pipeline/rescrape_all.py    full wiki re-harvest (resume-safe, rev-pinned)
    pipeline/walk_pools.py      provenance-complete pool walker (per-page hashes)
    pipeline/estimate.py        batch estimates (targets defined in-file)
    pipeline/estimate_cli.py    single-item estimates (same engine, same result)
    pipeline/coverage_test.py   held-out anchor coverage experiment
    pipeline/validate.py        schema gate over anchors + estimates
    pipeline/backfill_rev.py    RETIRED (fabricated provenance; fails loudly)
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
published estimate can be traced to the exact page revision it used. Revision
ids are captured in the same API call as the wikitext; post-hoc backfilling is
fabricated provenance and is a hard error (`backfill_rev.py` refuses to run).

Every pool snapshot carries a provenance manifest (query params, per-page
cursors, fetch timestamps, response hashes, finished_utc). A pool whose
manifest cannot prove a complete, timestamped walk is rejected:
`estimates` ABSTAIN with `INVALID_POOL`, they do not fall back to wall-clock
timestamps or unproven walks.

## Schema

Anchor record (anchors/*.jsonl): `title, item_id, purchased, purchased_as_of,
unpaired_purchased, favorites, favorites_as_of, sale_state (still_available |
closed | unknown), until, until_history, rev_id, rev_timestamp, parse_ok,
parse_notes`.

Parser rules that matter:

- Purchase/favorite counts are kept ONLY when paired with an `As of <date>` in
  the same or the immediately following sentence. Unpaired counts are stored
  separately (`unpaired_purchased`) as lower-bound candidates, never used as
  anchor endpoints. The old "N copies available" fallback is gone: copies
  available is not copies sold.
- A closed item's count is final ONLY if observed at or after its closure date
  (`purchased_as_of >= until`). A count observed before closure is stale and
  rejected (73 such rows in the first hardened pass).
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
