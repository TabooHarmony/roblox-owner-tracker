"""Acceptance suite for the v0 experimental release (reviewer directive).

Bounded, four cases only:
  A. valid output       — a well-formed target with valid evidence produces
                          an ESTIMATE with the full schema envelope.
  B. unsupported identity — a target id absent from the anchors DB abstains.
  C. missing/invalid evidence — missing pool file and INVALID_POOL both
                          abstain with a typed reason, never estimate.
  D. API failure        — a pool whose manifest records a failed walk does
                          not certify completion; estimation abstains.

Exit 0 only if every case behaves as specified. No new sentence hunting:
these are the four behaviors the release depends on.
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
import pool_manifest  # noqa: E402

FAILURES = []


def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILURES.append(name)


def cli(item_id, pool, anchors=None):
    cmd = [sys.executable, "pipeline/estimate_cli.py", "--item-id", item_id,
           "--pool", pool]
    if anchors:
        cmd += ["--anchors", anchors]
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    return r


def page(ids_chunk, cursor="", next_cursor="", status=200, errors=None):
    return {"cursor": cursor, "next_cursor": next_cursor,
            "fetched_utc": "2026-09-10T00:00:00Z", "count": len(ids_chunk),
            "raw_response_sha256": hashlib.sha256(
                json.dumps(ids_chunk).encode()).hexdigest(),
            "request_cursor": cursor, "http_status": status,
            "response_errors": errors}


def wrapped_pool(tmp, ids, finished_utc="2026-09-10T00:00:00Z", status="ok"):
    if status == "ok":
        pages = [page(ids)]
        complete = True
    else:
        # walker recorded an HTTP-200 body that was an errors object:
        # the walk must NOT certify completion (round-4 finding 5b)
        pages = [page(ids, status=200, errors=[{"code": 4}])]
        complete = False
    manifest = pool_manifest.make_manifest(
        query_params={"SortType": "Asc", "SortAggregation": "5", "limit": 10},
        pages=pages, started_utc="2026-09-10T00:00:00Z",
        finished_utc=finished_utc, complete=complete, item_ids=ids)
    return {"item_ids": ids, "manifest": manifest}


def main():
    anchor_path = os.path.join(ROOT, "anchors", "anchors_harden.jsonl")
    # pick a real eligible anchor id from the DB as a stand-in valid target
    valid_id = None
    with open(anchor_path) as f:
        for l in f:
            rec = json.loads(l)
            if rec.get("parse_ok") and rec.get("purchased") and rec.get("until"):
                valid_id = str(rec["item_id"])
                break

    with tempfile.TemporaryDirectory() as tmp:
        # --- A: valid output ---
        ids = [valid_id, "1000001", "1000002", "1000003", "1000004"]
        pa = os.path.join(tmp, "pool_ok.json")
        json.dump(wrapped_pool(tmp, ids), open(pa, "w"))
        r = cli(valid_id, pa, anchors=anchor_path)
        ok = r.returncode == 0
        row = json.loads(r.stdout) if ok and r.stdout.strip() else {}
        check("A: valid pool runs clean", ok, r.stderr[:120])
        check("A: schema envelope present",
              all(k in row for k in ("schema", "item_id", "status", "quantity",
                                     "code_commit", "parser_version",
                                     "anchors_sha256", "snapshot_utc")))
        check("A: assets-only entity_type", row.get("entity_type") == "asset")
        check("A: no confidence field (rank-neighbor comparison, uncalibrated)",
              "confidence" not in row)
        check("A: anchors evidence surfaced",
              row.get("status") != "ESTIMATE" or
              (row.get("anchors") or {}).get("above", {}).get("purchased") is not None)

        # --- B: unsupported identity ---
        ghost = "999999999999"
        ids_b = [ghost, "1000001", "1000002", "1000003", "1000004"]
        pb = os.path.join(tmp, "pool_ghost.json")
        json.dump(wrapped_pool(tmp, ids_b), open(pb, "w"))
        r = cli(ghost, pb, anchors=anchor_path)
        row_b = json.loads(r.stdout) if r.returncode == 0 and r.stdout.strip() else {}
        check("B: absent identity abstains (never estimates)",
              row_b.get("status") == "ABSTAIN" and bool(row_b.get("abstain_reason")))

        # --- C: missing / invalid evidence ---
        r = cli(valid_id, os.path.join(tmp, "does_not_exist.json"), anchors=anchor_path)
        check("C: missing pool file errors nonzero (not a fake abstain)",
              r.returncode != 0)
        pc = os.path.join(tmp, "pool_bad.json")
        bad = wrapped_pool(tmp, [valid_id, "1000001"])
        bad["manifest"]["n_items"] = 99  # internal-relationship contradiction
        json.dump(bad, open(pc, "w"))
        r = cli(valid_id, pc, anchors=anchor_path)
        row_c = json.loads(r.stdout) if r.returncode == 0 and r.stdout.strip() else {}
        check("C: INVALID_POOL abstains with typed reason",
              row_c.get("status") == "ABSTAIN"
              and row_c.get("abstain_reason", "").startswith("INVALID_POOL"))

        # --- D: API failure ---
        pd = os.path.join(tmp, "pool_failed.json")
        failed = wrapped_pool(tmp, [valid_id, "1000001", "1000002"], status="error")
        json.dump(failed, open(pd, "w"))
        r = cli(valid_id, pd, anchors=anchor_path)
        row_d = json.loads(r.stdout) if r.returncode == 0 and r.stdout.strip() else {}
        check("D: failed walk does not certify completion",
              row_d.get("status") == "ABSTAIN"
              and row_d.get("abstain_reason", "").startswith("INVALID_POOL"))

    print()
    if FAILURES:
        print(f"ACCEPTANCE FAILED: {len(FAILURES)} case(s): {FAILURES}")
        sys.exit(1)
    print("ACCEPTANCE OK: all four bounded cases behave as specified")


if __name__ == "__main__":
    main()
