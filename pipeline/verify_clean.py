#!/usr/bin/env python3
"""verify-clean: artifact REPLAY gate (Astra round-4 finding 4).

Rebuilds estimates from declared evidence in a clean clone at HEAD and diffs
against the COMMITTED shipped artifacts. Fail-fast at every stage; a missing
file, failed producer, or altered committed artifact each fail the gate.

This replaces the old shell process-substitution recipe which:
- ran under /bin/sh (no process substitution support),
- cloned from a wrong relative path,
- did not fail fast on producer failures,
- compared a filename production never writes,
- could pass on two empty streams.
"""
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHIPPED = os.path.join(ROOT, "estimates", "estimates_v2.jsonl")
REPLAY_REL = "estimates/estimates_v2.jsonl"


def fail(msg):
    print(f"REPLAY FAILED: {msg}", file=sys.stderr)
    sys.exit(1)


def run(cmd, cwd=None):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        fail(f"command {' '.join(cmd)} failed rc={r.returncode}: "
             f"{(r.stderr or r.stdout)[-400:]}")
    return r.stdout


def main():
    head = run(["git", "rev-parse", "HEAD"], cwd=ROOT).strip()

    if not os.path.exists(SHIPPED):
        fail(f"committed artifact missing: {SHIPPED}")
    with open(SHIPPED) as f:
        shipped = [json.loads(l) for l in f if l.strip()]
    if not shipped:
        fail("committed artifact is empty")

    tmp = tempfile.mkdtemp(prefix="verify-clean-")
    repo = os.path.join(tmp, "repo")
    run(["git", "clone", "--quiet", "--no-hardlinks", ROOT, repo])
    run(["git", "checkout", "--quiet", head], cwd=repo)

    replay = os.path.join(repo, REPLAY_REL)
    if not os.path.exists(replay):
        fail(f"clean clone is missing the committed artifact {REPLAY_REL}")

    # save the committed copy, then DELETE it: the producer must rebuild it
    # from committed evidence alone. If generation fails or writes nothing,
    # the gate fails (no two-empty-streams pass).
    with open(replay, "rb") as f:
        committed_bytes = f.read()

    # producers run with committed evidence only; failure aborts the gate
    os.remove(replay)
    run([sys.executable, "pipeline/estimate.py"], cwd=repo)
    run([sys.executable, "pipeline/validate.py"], cwd=repo)

    if not os.path.exists(replay):
        fail("producer did not regenerate estimates/estimates_v2.jsonl")
    with open(replay) as f:
        replayed = [json.loads(l) for l in f if l.strip()]
    if not replayed:
        fail("replayed artifact is empty (producer produced nothing)")

    def key(rows):
        # ignore only the self-referential code_commit field
        out = []
        for r in rows:
            r = dict(r)
            r.pop("code_commit", None)
            out.append(json.dumps(r, sort_keys=True))
        return sorted(out)

    if key(shipped) != key(replayed):
        fail("committed artifact does not match clean replay "
             f"({len(shipped)} shipped vs {len(replayed)} replayed rows)")

    print(f"REPLAY OK: {len(shipped)} rows identical modulo code_commit")


if __name__ == "__main__":
    main()
