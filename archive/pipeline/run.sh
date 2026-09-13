#!/usr/bin/env bash
# CLI entry point. Run from repo root: pipeline/run.sh <command>
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${PYTHON:-python3}"

cmd="${1:-help}"
case "$cmd" in
  tests)
    "$PY" tests/test_pipeline.py
    ;;
  validate)
    "$PY" pipeline/validate.py
    ;;
  harvest)
    "$PY" pipeline/rescrape_all.py
    "$PY" pipeline/merge_anchors.py
    "$PY" pipeline/validate.py
    ;;
  pools)
    # provenance-complete pool re-walk for all published targets
    "$PY" pipeline/walk_pools.py pools/walk_targets.json
    ;;
  estimate)
    # pools must exist and carry valid manifests; estimates abstain otherwise
    "$PY" pipeline/estimate.py
    "$PY" pipeline/validate.py
    ;;
  all)
    "$0" harvest
    "$0" pools
    "$0" estimate
    ;;
  help)
    echo "usage: pipeline/run.sh {tests|validate|harvest|pools|estimate|all}"
    ;;
  *)
    # unknown commands FAIL (Astra 4.4): a misspelled scheduled command must
    # never masquerade as a successful no-op.
    echo "error: unknown command '$cmd'" >&2
    echo "usage: pipeline/run.sh {tests|validate|harvest|pools|estimate|all}" >&2
    exit 2
    ;;
esac
