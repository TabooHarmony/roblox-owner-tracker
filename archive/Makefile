# roblox-owner-tracker pipeline entry points.
# NOTE (Astra 4.3): Make variables are NOT a safe transport for untrusted
# strings (shell interpolation). The CLI path for untrusted input is
# estimate_cli.py with direct argv; these targets are operator conveniences.

ITEM_ID ?= 92137983874490
POOL ?= pools/crown_pool_nfl_wrapped.json

.PHONY: tests validate estimate cli refresh verify-clean

tests:
	python3 -m unittest discover -s tests -v

validate:
	python3 pipeline/validate.py

estimate:
	python3 pipeline/estimate.py

cli:
	python3 pipeline/estimate_cli.py --item-id "$(ITEM_ID)" --pool "$(POOL)"

refresh:
	python3 pipeline/rescrape_all.py
	python3 pipeline/walk_pools.py pools/walk_targets.json
	python3 pipeline/merge_anchors.py anchors_harden_rescrape.jsonl anchors_delta_parsed.jsonl
	python3 pipeline/estimate.py
	python3 pipeline/validate.py

# Astra round-3 5D / round-4 finding 4: artifact REPLAY, not consecutive-run
# stability. Implemented as a fail-fast program (pipeline/verify_clean.py):
# clean clone at HEAD, producers must succeed, output compared against the
# COMMITTED estimates/estimates_v2.jsonl. Missing files, failed generation, and
# altered committed artifacts each fail the gate.
verify-clean:
	python3 pipeline/verify_clean.py
