"""Canonical v2 estimate schema - THE one serializer for every entry point.

Canonical schema (one shape for every row, batch and CLI identical):
{
  "schema": 2,
  "item": str,            # title, human-readable
  "item_id": int,         # catalog id (numeric, always)
  "entity_type": "asset"|"bundle",
  "quantity": str,        # what the number measures (always present, estimate or not)
  "snapshot_utc": str,    # pool walk finished_utc - NOT wall clock
  "pool": str|null,       # pool artifact path/reference (validator-required)
  "status": "ESTIMATE" | "ABSTAIN",
  "confidence": "LOW"|"MEDIUM"|null,
  "bracket": [int, int]|null,
  "warnings": [str],
  "anchors": {...}|null,
  "abstain_reason": str|null
}

Rejected from v1: favorites-derived point estimates, free-text status, rows
without snapshot dates, mixed schemas, 'UNCHANGED' carry-forward.
Method/currency disclosures are fixed constants, not per-run choices
(Astra 2.8: divergent serializers silently drop semantics).
"""
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Fixed method/currency disclosure (Astra 1.3/1.5): every row states WHAT the
# number claims to measure and its calibration status. Neither is negotiable.
QUANTITY = ("estimated lifetime purchases of the original item "
            "(rank-neighbor heuristic; NOT distinct current owners, NOT copies)")
CALIBRATION = "uncalibrated"
METHOD = "rank_neighbor_heuristic"


def _git_commit():
    # Release builds pin this via RELEASE_COMMIT env (set by CI/tag process);
    # otherwise we report the commit the code last ran at. NOTE: self-referential
    # if embedded in a committed artifact - one commit behind HEAD by design.
    env = os.environ.get("RELEASE_COMMIT")
    if env:
        return env
    # Round-3 finding 5D: unpinned regeneration must be LOUD about its identity,
    # never silently one-commit-behind. estimate.py/CI set RELEASE_COMMIT at
    # release; local runs print the warning once per process.
    try:
        import sys as _s
        print("WARNING: RELEASE_COMMIT not set; code_commit = working-tree HEAD",
              file=_s.stderr)
    except Exception:
        pass
    try:
        import subprocess
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                              text=True, cwd=root).stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def anchors_digest(path=None):
    """Digest of the anchors file ACTUALLY used (Astra round-3 finding 5C):
    the caller passes the path it loaded; a custom --anchors file must
    fingerprint itself, not the default database. No import-time caching:
    the digest is computed per call from the real bytes."""
    if path is None:
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "anchors", "anchors_harden.jsonl")
    try:
        return hashlib.sha256(open(path, "rb").read()).hexdigest()
    except OSError:
        return "missing"


CODE_COMMIT = _git_commit()
PARSER_VERSION = "2.2"  # window model, assertion binding, channel-scope status


def row(item, item_id, result, snapshot_utc, pool=None,
        entity_type="asset", anchors_path=None):
    """snapshot_utc is REQUIRED and must come from the pool manifest
    (finished_utc of the walk that produced the pool). No wall-clock fallback:
    identical inputs must produce identical bytes (Astra #7 regression fix).
    `pool` is the pool artifact reference; it is kept for BOTH statuses so a
    copied JSON record still identifies its evidence (Astra 2.11 partial)."""
    base = {
        "schema": 2,
        "item": item,
        "item_id": int(item_id),
        "entity_type": entity_type,
        "quantity": QUANTITY,
        "calibration_status": CALIBRATION,
        "method": METHOD,
        "snapshot_utc": None,
        "pool": pool,
        "status": None,
        "confidence": None,
        "bracket": None,
        "warnings": [],
        "anchors": None,
        "abstain_reason": None,
        # reproducibility envelope (Astra 2.11): a copied record must pin its
        # evidence. A timestamp alone is not a snapshot identifier.
        "code_commit": CODE_COMMIT,
        "parser_version": PARSER_VERSION,
        "anchors_sha256": anchors_digest(anchors_path),
    }
    if not snapshot_utc:
        base["status"] = "ABSTAIN"
        base["abstain_reason"] = ("NO_SNAPSHOT_PROVENANCE: pool manifest has no finished_utc; "
                                  "a bracket needs a timestamped walk (no wall-clock substitution)")
        return base
    base["snapshot_utc"] = snapshot_utc
    base["status"] = result["status"]
    if result["status"] == "ESTIMATE":
        base["confidence"] = result.get("confidence")
        base["bracket"] = result["bracket"]
        base["warnings"] = result.get("warnings", [])
        base["anchors"] = result.get("anchors")
    else:
        base["abstain_reason"] = result.get("reason", "UNSPECIFIED") + (
            ": " + result.get("detail", "") if result.get("detail") else "")
    return base


def dumps(row_obj, indent=None):
    """One serialization path. CLI and batch both call this."""
    return json.dumps(row_obj, indent=indent)


if __name__ == "__main__":
    print("import me; estimate.py and estimate_cli.py share this serializer")
