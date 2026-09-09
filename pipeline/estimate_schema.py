"""Regenerate estimates/estimates_bracketed.jsonl under the canonical v2 schema.

Canonical schema (one shape for every row):
{
  "schema": 2,
  "item": str,            # title, human-readable
  "item_id": int,         # catalog id (numeric, always)
  "snapshot_utc": str,    # when THIS estimate was computed
  "status": "ESTIMATE" | "ABSTAIN",
  "confidence": "LOW"|"MEDIUM"|null,
  "bracket": [int, int]|null,
  "warnings": [str],
  "anchors": {...}|null,
  "pool_manifest": path|null,
  "abstain_reason": str|null
}

Rejected from v1: favorites-derived point estimates (contradicts measured
fav/purchase spread), free-text status, rows without snapshot dates, mixed
schemas for the same item, 'UNCHANGED' carry-forward (failed revalidation
abstains with STALE_RESULT instead of silently repeating an old number).
"""
import json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bracket

CANON = {
    "schema": 2,
    "item": None, "item_id": None, "snapshot_utc": None,
    "status": None, "confidence": None, "bracket": None,
    "warnings": [], "anchors": None, "pool_manifest": None,
    "abstain_reason": None,
}


def row(item, item_id, result, snapshot_utc, pool_manifest=None):
    """snapshot_utc is REQUIRED and must come from the pool manifest
    (finished_utc of the walk that produced the pool). No wall-clock fallback:
    identical inputs must produce identical bytes (Astra #7 regression fix)."""
    if not snapshot_utc:
        return {"schema": 2, "item": item, "item_id": int(item_id),
                "status": "ABSTAIN",
                "abstain_reason": "NO_SNAPSHOT_PROVENANCE: pool manifest has no finished_utc; "
                                  "a bracket needs a timestamped walk (no wall-clock substitution)",
                "warnings": [], "anchors": None, "pool_manifest": pool_manifest,
                "confidence": None, "bracket": None}
    r = dict(CANON)
    r.update({
        "item": item,
        "item_id": int(item_id),
        "snapshot_utc": snapshot_utc,
        "status": result["status"],
    })
    if result["status"] == "ESTIMATE":
        r["confidence"] = result.get("confidence")
        r["bracket"] = result["bracket"]
        r["warnings"] = result.get("warnings", [])
        r["anchors"] = result.get("anchors")
        r["pool_manifest"] = pool_manifest
    else:
        r["abstain_reason"] = result.get("reason", "UNSPECIFIED") + (
            ": " + result.get("detail", "") if result.get("detail") else "")
    return r


if __name__ == "__main__":
    print("regenerate via estimate_cli.py after anchors re-scrape completes")
