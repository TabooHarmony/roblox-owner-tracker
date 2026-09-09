# Validation status

## What was measured (2026-09-09, anchors_harden.jsonl, rev-pinned)

Held-out anchor test on the three published pools (party, stormbreak, crown;
990-1,000 items each, same taxonomy slice). For every eligible closed-final
anchor in a pool, hide the eligible anchors within a rank radius R and bracket
the hidden target from outside R only.

`pipeline/coverage_test.py`, all three published pools:

| pool | R=1 | R=2 | R=5 | R=10 |
|---|---|---|---|---|
| party (37 eligible) | 9/9 (2.2x) | 14/14 (2.8x) | 20/20 (4.4x) | 26/26 (7.0x) |
| stormbreak (27 eligible) | n/a | 6/6 (1.5x) | 14/14 (4.0x) | 17/17 (3.3x) |
| crown (41 eligible) | 2/2 (2.3x) | 7/8 = 88% (2.3x) | 14/17 = 82% (1.8x) | 23/27 = 85% (3.7x) |

Cells: coverage n/n (median bracket width). Aggregate: 154/160 = 96%,
widths 1.5x-7.0x. Zero abstentions (the engine always found outside-R anchors).

Earlier K-gap variant (hide K consecutive pool ranks, K=2..20): 92-100% per
pool. Same picture: the crown pool is the weakest; party is the cleanest.

## Reading this honestly

- Coverage here is measured on anchors that passed the eligibility filter
  (closed-final, post-2012, paired count). It is NOT coverage over all items.
- n is small (2-27 per cell). These are point estimates of coverage with huge
  error bars; 100% at n=9 says little. The crown pool (82-88%) is the honest
  read of the method's hit rate; party's 100% is the small-n mirage.
- Width is the honest cost: brackets that survive holdout grow from ~2x at
  immediate neighbors to ~7x at 10 eligible-neighbors out.
- The 17% adjacent-pair inversion number is a DIFFERENT measurement (local
  ordering noise), not a coverage probability. Do not mix them.
- All pools tested come from one serving regime (SortType=2 bestseller slices,
  same taxonomy). Other regimes are untested.

## What would change these conclusions

- A target whose wiki purchase count is stale or vandalized breaks the
  bracket silently. The parser now strips comments and requires paired
  As-of dating, but the wiki itself is untrusted at some level.
- Pools with mixed acquisition mechanisms (bundles, UARTs, UGC) were not
  tested and the engine flags but does not handle them.

## Status

EXPERIMENTAL. Intervals are leads for manual investigation. Nothing here is a
confidence bound. Confidence labels (HIGH/MEDIUM/LOW) encode width and anchor
agreement heuristics only, calibrated to nothing.

Method by Maggy (Maggy Rarefication); deterministic reimplementation and
validation by this repo.
