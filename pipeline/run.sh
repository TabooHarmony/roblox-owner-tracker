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
    "$PY" pipeline/rescrape_delta.py
    "$PY" pipeline/merge_anchors.py
    "$PY" pipeline/validate.py
    ;;
  estimate)
    "$PY" pipeline/estimate.py
    ;;
  help|*)
    echo "usage: pipeline/run.sh {tests|validate|harvest|estimate}"
    ;;
esac
