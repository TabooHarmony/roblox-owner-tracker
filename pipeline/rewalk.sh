#!/usr/bin/env bash
# Re-walk every target pool with full page provenance (manifest pages, cursors,
# per-page fetch timestamps and response hashes), then regenerate estimates.
# This is the only path to a valid estimate: pool_manifest.validate demands
# per-page provenance and a finished_utc, so legacy shell manifests abstain.
set -euo pipefail
cd "$(dirname "$0")/.."
python3 pipeline/walk_pools.py pools/walk_targets.json
python3 pipeline/estimate.py
python3 pipeline/validate.py
