"""RETIRED - do not run.

This script attached CURRENT wiki revision ids/timestamps to purchase counts
that had been parsed from EARLIER snapshots. That is false provenance: the
rev_id claimed the count was observed at the backfill time, when the wikitext
may have changed since the parse. Astra re-audit, new finding #2.

Correct pattern (used by rescrape_all.py): fetch content AND ids in ONE call
(rvprop=content|ids|timestamp) so every record's rev_id is the exact revision
its wikitext came from. There is no valid post-hoc backfill.

Kept only so old Makefile targets fail loudly instead of silently corrupting.
"""
import sys

sys.exit(
    "backfill_rev.py is retired: it fabricates provenance. "
    "Use rescrape_all.py (rvprop=content|ids|timestamp in one call)."
)
