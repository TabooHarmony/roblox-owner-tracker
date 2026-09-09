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

## What the number measures (estimand)

Every estimate row states it in `quantity`: estimated **lifetime purchases of
the original item** — not copies, not distinct current owners, not secondary
transactions. Roblox documents resale and multi-copy ownership, so these are
different quantities; this pipeline estimates exactly one and claims none of
the others. The wiki's purchase counts and the search `SortType=Sales`
ordering are both presumed to measure this quantity; the presumption is
itself unverified (see "Open spec questions").

## Open spec questions (before lifetime claims)

- The pools explicitly request `SortAggregation=5` (AllTime). Whether the
  endpoint honors it, and exactly which transaction types its "Sales"
  ordering counts, is not verified against observed wiki counts yet.
- `totalQuantity` in the v2 response (where populated for limited-unique
  items) is a different quantity again (issued instances) and is not used.

## Eligibility rules (enforced by the engine, not by convention)

An anchor is eligible only if ALL hold:

1. `sale_state == "closed"` with a parsed `until` date.
2. Paired purchase count: `purchased` with `purchased_as_of` in the same
   sentence. Unpaired counts are lower bounds and are never endpoints.
   (Date binding is strict: a count pairs only with an As-of date in the
   SAME sentence; borrowing a favorites/removal date from the next sentence
   was a real bug and is covered by a release-blocking fixture.)
3. The count was observed AT OR AFTER closure (`purchased_as_of >= until`).
   Stale pre-closure counts are rejected (the first hardened pass carried 73;
   all are now flagged as warnings by `validate.py` and rejected as anchors).
4. The record parses cleanly (`parse_ok`); unresolved date templates fail
   closed. Identities are typed (`asset:` / `bundle:`) end to end.

## Pool provenance

Every pool ships a v2 manifest: explicit query semantics (`SortType`,
`SortAggregation`), per-page request cursors, per-page `fetched_utc` and
response SHA-256, a digest of the ordered id list, and `started_utc` /
`finished_utc`. The manifest validator CHECKS the id digest against the
stored ids, requires a faithful cursor chain, and rejects duplicate ids of
any size (a repeated id means the ranking moved mid-walk). The batch and CLI
estimators both refuse a pool whose manifest does not prove a complete,
timestamped walk (`ABSTAIN / INVALID_POOL`). Snapshot timestamps in
`estimates_v2.jsonl` come from the manifest, never from the wall clock.
Known limit: the digests are self-reported by the same walk that produced
the pool; they detect later tampering, not a biased serving split.

## Held-out coverage experiment

`pipeline/coverage_test.py`: for each eligible anchor, hide the eligible
anchors within rank radius R, bracket the target from outside R only, and
check containment.

Metric naming (precise): with EE = eligible pool-occurrences, AA = attempts
(occurrences with an eligible neighbor in R), NN = emitted estimates, and
CC = emitted intervals containing the held-out label, the table below reports
**C/A — containment over attempts**, NOT conditional coverage C/N and not
C/E over all eligible occurrences. Excluded occurrences (E-A) are cases the
experiment could not attempt at that radius; they are NOT demonstrated
misses and are not counted as failures.

Radius changes both the selected cohort and the available endpoints, so the
R=1/2/5/10 columns are different experiments, not one cohort tested at
different widths.

Run against the shipped data (2026-09-09):

    party (74 eligible of 948):      R=1 21/22  R=2 30/31  R=5 38/40  R=10 56/61
    stormbreak (34 of 936):          R=1  0/2   R=2  5/7   R=5 12/13  R=10 22/23
    crown (43 of 939):               R=1  0/0   R=2  6/6   R=5 16/16  R=10 31/31
    confetti (26 of 732):            R=1  2/2   R=2  6/6   R=5 13/13  R=10 15/15
    aggregate (pools summed):        R=1 23/26=88%   R=2 47/50=94%
                                     R=5 79/82=96%   R=10 124/130=95%

Selection rates A/E (attempts over eligible occurrences): R=1 26/177=15%,
R=2 50/177=28%, R=5 82/177=46%, R=10 130/177=73%. The experiment attempts a
minority of eligible occurrences at small radii; every attempt and skip is
printed by the script.

Honest caveats:

- Selection is severe: at R=1 only 26 of 177 eligible occurrences (15%) are
  attempted. The reported fractions describe the selected attempts only.
- Per-pool cells are small (2-31 attempts). 100% at n=6 says little.
- Labels come from the same anchor database as the evidence — containment
  here cannot independently verify extraction, units, or identity. A scaled
  world (all counts x10) scores identically. Independent adjudicated
  reference data is a Gate-B requirement, not done.
- The crown pool's earlier 82-88% reading came from a run with stale-count
  anchors allowed as endpoints; under the corrected eligibility rules it
  reads 100% at R>=2, but n is too small to call that improvement rather
  than noise. The aggregate (88-95% with skips reported) is the number to
  quote, not any single pool.
- Coverage measured this way is in-sample for the eligibility rules. It is
  not a guarantee on future, unseen pools.
- Multi-pool interval intersection is retired: intersecting heuristic
  intervals does not create confidence (shared anchors are correlated).
  Results are published pool-local only.

## Determinism

Identical inputs produce byte-identical outputs: the engine is pure-Python
over shipped JSONL/JSON files; there is no wall-clock input anywhere in the
estimate path (the snapshot timestamp is read from the pool manifest, and
missing manifests are a hard abstain, not a fabricated timestamp).
`estimate.py` (batch) and `estimate_cli.py` (single item) share ONE
serializer and return identical results; verified on all four targets
against the shipped pools.

## Release checklist

- [x] one harvest -> merge -> estimate -> validate path from a clean checkout
      (`pipeline/run.sh` or `make refresh`)
- [x] identical CLI/batch behavior (shared serializer, verified per-target)
- [x] stale and unpaired anchors rejected as endpoints
- [x] inverted / singleton / self-bracketed results abstain
- [x] manifest-verified pool provenance (digest-checked); no fabricated timestamps
- [x] single output schema (`estimates_v2.jsonl`); legacy files archived
- [x] corrected, skip-aware coverage report with named metrics (this document)
- [x] refresh CI runs the maintained pipeline and validates before publishing
- [ ] Gate B: independently adjudicated reference observations (external
      validation of units/identity) — required before any numbers here are
      treated as measurements
