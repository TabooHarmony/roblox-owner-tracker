# Validation

Status: **experimental**. These are uncalibrated rank-neighbor estimates —
leads, not bounds. Published numbers below are from the held-out experiment
described here, run against the shipped (provenance-clean) anchors and pools.

Method origin: the bestseller/rainbow-anchor bracketing method is Maggy's
(Maggy Rarefication). This repo is an engineering implementation of it.

## What the method can and cannot claim

- An anchor's post-closure purchase count is exact (observed on the wiki).
- The target's count is bracketed between two such anchors by sales rank.
- The identifiability gap is real: anchor agreement does NOT prove the target
  sits between them. Rank order is a proxy, not a guarantee. Treat every
  bracket as a plausible range, never as a bound.
- Brackets do not carry a coverage probability. Width is not confidence.

## Eligibility rules (enforced by the engine, not by convention)

An anchor is eligible only if ALL hold:

1. `sale_state == "closed"` with a parsed `until` date.
2. Paired purchase count: `purchased` with `purchased_as_of` in the same
   sentence. Unpaired counts are lower bounds and are never endpoints.
3. The count was observed AT OR AFTER closure (`purchased_as_of >= until`).
   Stale pre-closure counts are rejected (the first hardened pass carried 73;
   all are now flagged as warnings by `validate.py` and rejected as anchors).

## Pool provenance

Every pool ships a manifest: query parameters, per-page cursors, per-page
fetch timestamps and response SHA-256s, and a `finished_utc`. The batch and
CLI estimators both refuse a pool whose manifest does not prove a complete,
timestamped walk (`ABSTAIN / INVALID_POOL`). Snapshot timestamps in
`estimates_v2.jsonl` come from the manifest, never from the wall clock.

## Held-out coverage experiment

`pipeline/coverage_test.py`: for each eligible anchor, hide the eligible
anchors within rank radius R, bracket the target from outside R only, and
check containment. Every skipped target (no eligible neighbor in R) is
counted and reported; coverage is computed over attempts (estimate + abstain),
never over estimates only; the aggregate sums pools, it does not average
percentages.

Run against the shipped data (2026-09-09):

    party (74 eligible of 948):      R=1 21/22  R=2 30/31  R=5 38/40  R=10 56/61
    stormbreak (34 of 936):          R=1  0/2   R=2  5/7   R=5 12/13  R=10 22/23
    crown (43 of 939):               R=1  0/0   R=2  6/6   R=5 16/16  R=10 31/31
    confetti (26 of 732):            R=1  2/2   R=2  6/6   R=5 13/13  R=10 15/15
    aggregate (pools summed):        R=1 23/26=88%   R=2 47/50=94%
                                     R=5 79/82=96%   R=10 124/130=95%

Median bracket widths: 1.3x-4.5x across R=1-10. Zero engine abstentions in
attempts (abstentions shown separately where they occurred: party R=10 had 3).

Honest caveats:

- Per-pool cells are small (2-31 attempts). 100% at n=6 says little.
- The crown pool's earlier 82-88% reading came from a run with stale-count
  anchors allowed as endpoints; under the corrected eligibility rules it
  reads 100% at R>=2, but n is too small to call that improvement rather
  than noise. The aggregate (88-96% with skips reported) is the number to
  quote, not any single pool.
- Coverage measured this way is in-sample for the eligibility rules. It is
  not a guarantee on future, unseen pools.

## Determinism

Identical inputs produce byte-identical outputs: the engine is pure-Python
over shipped JSONL/JSON files; there is no wall-clock input anywhere in the
estimate path (the snapshot timestamp is read from the pool manifest, and
missing manifests are a hard abstain, not a fabricated timestamp).
`estimate.py` (batch) and `estimate_cli.py` (single item) call the same
`rank_bracket` with string-normalized IDs and return identical results;
verified on all four targets against the shipped pools.

## Release checklist (what blocks v1)

- [x] one harvest -> merge -> estimate -> validate path from a clean checkout
      (`pipeline/run.sh` / `make rescrape && make merge && make estimate`)
- [x] identical CLI/batch behavior (verified per-target above)
- [x] stale and unpaired anchors rejected as endpoints
- [x] manifest-verified pool provenance; no fabricated timestamps
- [x] single output schema (`estimates_v2.jsonl`); legacy files archived
- [x] corrected, skip-aware coverage report (this document)
