# Clean-run: regenerate anchors from scratch in a fresh checkout.
# Determinism contract: identical snapshot (wiki revision set) + code + config => identical bytes.
rescrape:
	python3 pipeline/rescrape_all.py

test:
	python3 tests/test_pipeline.py

estimate:
	python3 pipeline/estimate_cli.py --item-id $(ITEM_ID) --pool $(POOL)
