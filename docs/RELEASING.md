# Release identity and artifact reproduction

## `code_commit` convention

Every estimate row embeds `code_commit`: the git SHA of the source tree that
PRODUCED the row. Because the SHA of a commit cannot include itself, a row
generated during commit C's authoring pins C's PARENT. Convention:

- Rows generated at working tree HEAD pin `HEAD` (via `git rev-parse HEAD`).
- Shipped artifacts therefore pin the commit one before the release commit.
- A regen at the release commit differs from shipped artifacts ONLY in this
  field (verified byte-identical otherwise; see clean-checkout procedure).

## Exact regeneration procedure (artifact replay)

1. `git checkout <release_commit>`
2. `make anchors` (requires network; harvests and merges anchors)
3. `make estimate`
4. Compare against shipped `estimates_bracketed.jsonl`:
   `diff <(jq -c 'del(.code_commit)' shipped) <(jq -c 'del(.code_commit)' regen)`
   Expected: empty. This is the artifact-replay test; running the pipeline
   twice and comparing those two runs is NOT a replay test.
5. Verify `code_commit` in every regenerated row equals `<release_commit>~1`
   (parent), or the explicit `RELEASE_COMMIT` override.

## CI replay step

The workflow's replay step performs steps 2-4 from a clean checkout and FAILS
the run on any non-`code_commit` diff. It reconstructs shipped artifacts from
their declared evidence; it is not a consecutive-run stability check.

## Clean-checkout verification

`make verify-clean` clones the repo to a temp dir, runs steps 2-4, and
diffs against the shipped artifacts (excluding `code_commit`).
