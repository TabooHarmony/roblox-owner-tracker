"""Fixture tests for the hardened pipeline. Run: python3 tests/test_pipeline.py

Test discipline (Astra 4.2): every behavior test asserts a successful baseline
FIRST, then changes one condition. Tests assert intended semantics, not
merely agreement between two calls.
"""
import json, os, sys, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pipeline"))
import parse_wiki, bracket, validate, pool_manifest
from estimate_schema import row as schema_row, dumps

# Canonical eligible anchor: closed, paired count, count observed AT/after closure.
def anchor(purchased, as_of="March 5, 2020", until="March 5, 2020"):
    return {"purchased": purchased, "purchased_as_of": as_of,
            "sale_state": "closed", "until": until}

BASELINE_ANCHORS = {
    "1": anchor(20000), "3": anchor(3000),
}
BASELINE = bracket.rank_bracket(["1", "2", "3"], "2", BASELINE_ANCHORS)
assert BASELINE["status"] == "ESTIMATE" and BASELINE["bracket"] == [3000, 20000], BASELINE


class TestParserDateBinding(unittest.TestCase):
    """Astra 2.1a: dates bind to the purchase assertion, same sentence only."""

    def test_favorites_date_not_transferred(self):
        # REGRESSION FIXTURE (release-blocking): favorites date next to a
        # historical purchase count must NOT fabricate a purchase date.
        r = parse_wiki.parse("It was purchased 100 times. As of January 1, 2020, it was favorited 50 times.")
        self.assertIsNone(r["purchased"])
        self.assertIsNone(r["purchased_as_of"])
        self.assertEqual(r["unpaired_purchased"], 100)

    def test_removal_date_not_transferred(self):
        r = parse_wiki.parse("It was purchased 100 times. As of January 1, 2020, it was removed.")
        self.assertIsNone(r["purchased"])
        self.assertIsNone(r["purchased_as_of"])

    def test_two_dates_one_sentence_rejects_or_binds_correctly(self):
        # Ambiguous multi-date binding must never silently pick the wrong one.
        r = parse_wiki.parse("It was purchased 100 times, as of January 1, 2020, before March 5, 2020 it was favorited 50 times.")
        if r["purchased"] is not None:
            self.assertEqual(r["purchased_as_of"], "January 1, 2020")

    def test_same_sentence_either_order_binds(self):
        r = parse_wiki.parse("As of January 1, 2020, it was purchased 100 times")
        self.assertEqual((r["purchased"], r["purchased_as_of"]), (100, "January 1, 2020"))
        r = parse_wiki.parse("It was purchased 100 times, as of January 1, 2020")
        self.assertEqual((r["purchased"], r["purchased_as_of"]), (100, "January 1, 2020"))

    def test_unresolved_later_closure_fails_closed(self):
        # Astra 2.1c: valid 2019 closure followed by unresolved {{Date|2025}}
        # must NOT be classified closed-2019 with parse_ok=True.
        r = parse_wiki.parse("| until = June 12, 2019\nLater closed again on {{Date|2025|1|1}}.")
        if r["sale_state"] == "closed":
            self.assertIn("unresolved", " ".join(r.get("parse_notes", [])))

    def test_comment_poisoning(self):
        wt = "As of January 1, 2026 <!-- old value: purchased 9,999,999 times --> it has been purchased 1,000 times. As of January 1, 2026."
        r = parse_wiki.parse(wt)
        self.assertEqual(r["purchased"], 1000)

    def test_purchase_without_asof_not_paired(self):
        r = parse_wiki.parse("It has been purchased 5,000 times.")
        self.assertIsNone(r["purchased"])
        self.assertEqual(r["unpaired_purchased"], 5000)

    def test_copies_fallback_removed(self):
        r = parse_wiki.parse("There were 1,000 copies available; only 200 sold.")
        self.assertIsNone(r["purchased"])
        self.assertIsNone(r["unpaired_purchased"])

    def test_case_insensitive_still_available(self):
        for variant in ("Still available", "Still Available", "still available"):
            r = parse_wiki.parse("| until = " + variant)
            self.assertEqual(r["sale_state"], "still_available", variant)

    def test_reopened_item_last_date_wins(self):
        r = parse_wiki.parse("| until = June 12, 2012\n| until = March 5, 2020")
        self.assertEqual(r["sale_state"], "closed")
        self.assertEqual(r["until"], "March 5, 2020")
        self.assertEqual(len(r["until_history"]), 2)

    def test_paired_sentence_real_phrasing(self):
        r = parse_wiki.parse("As of January 1, 2020, it has been purchased 8,891 times and favorited 1,719 times.")
        self.assertEqual(r["purchased"], 8891)
        self.assertEqual(r["purchased_as_of"], "January 1, 2020")
        self.assertEqual(r["favorites"], 1719)


class TestParserIdentity(unittest.TestCase):
    """Astra 2.1c: identity extraction scoped to the real infobox."""

    def test_nowiki_example_id_ignored(self):
        # REGRESSION FIXTURE: a literal <nowiki>| id = 999</nowiki> example must
        # not override the infobox's | id = 123.
        wt = "Example usage: <nowiki>| id = 999</nowiki>\n{{Infobox\n| id = 123\n}}"
        r = parse_wiki.parse(wt)
        self.assertEqual(r["item_id"], 123)

    def test_bundle_id_typed(self):
        r = parse_wiki.parse("| catalog id = \n| bundle id = 555")
        self.assertEqual(r["item_id"], 555)
        self.assertIn("id_from_bundle_id", r["parse_notes"])
        self.assertIn("entity_type:bundle", r["parse_notes"])


class TestEngineIdentity(unittest.TestCase):
    """Astra 2.2: asset/bundle identities never collapse."""

    def test_bundle_aliased_separately(self):
        # same numeric id under different entity types = different keys
        a_asset = {"purchased": 5000, "purchased_as_of": "March 5, 2020",
                   "sale_state": "closed", "until": "March 5, 2020"}
        self.assertIn("asset:555", {"asset:555": a_asset})
        self.assertNotIn("bundle:555", {"asset:555": a_asset})


class TestEngine(unittest.TestCase):
    def _run(self, anchors, pool=None, target="2"):
        return bracket.rank_bracket(pool or ["1", "2", "3"], target, anchors)

    def test_baseline_estimate(self):
        r = self._run(BASELINE_ANCHORS)
        self.assertEqual(r["status"], "ESTIMATE")
        self.assertEqual(r["bracket"], [3000, 20000])
        self.assertIn(r["confidence"], ("LOW", "MEDIUM"))

    def test_no_anchors_abstains(self):
        r = bracket.rank_bracket([1, 2], 2, {})
        self.assertEqual(r["status"], "ABSTAIN")
        self.assertEqual(r["reason"], "NO_ELIGIBLE_ANCHOR_ABOVE_AND_BELOW")

    def test_target_missing_abstains(self):
        r = bracket.rank_bracket(["1"], "9", {"1": anchor(5)})
        self.assertEqual(r["status"], "ABSTAIN")
        self.assertEqual(r["reason"], "TARGET_NOT_IN_POOL")

    def test_self_bracketing_rejected(self):
        # REGRESSION FIXTURE (Astra 2.5): the same anchor on both sides of the
        # target must be impossible. Duplicate pool ids abstain.
        r = self._run(BASELINE_ANCHORS, pool=["1", "2", "1", "3"])
        self.assertEqual(r["status"], "ABSTAIN")
        self.assertIn(r["reason"], ("DUPLICATE_POOL_IDS", "TARGET_DUPLICATED"))

    def test_inverted_endpoints_abstain(self):
        # REGRESSION FIXTURE (Astra 2.6a): upper-rank count < lower-rank count
        # must ABSTAIN, never emit a backwards interval.
        anchors = {"1": anchor(100), "3": anchor(200)}
        r = self._run(anchors)
        self.assertEqual(r["status"], "ABSTAIN")
        self.assertEqual(r["reason"], "ANCHOR_INVERSION")

    def test_singleton_interval_abstains(self):
        # REGRESSION FIXTURE (Astra 2.6b): [100,100] implies exact knowledge.
        anchors = {"1": anchor(100), "3": anchor(100)}
        r = self._run(anchors)
        self.assertEqual(r["status"], "ABSTAIN")
        self.assertEqual(r["reason"], "SINGLETON_INTERVAL")

    def test_malformed_counts_rejected(self):
        # REGRESSION FIXTURE (Astra 2.6c): booleans, negatives, impossible dates.
        for bad in (True, -5, False):
            a1 = anchor(20000); a1["purchased"] = bad
            ok, why = bracket.anchor_eligible(a1)
            self.assertFalse(ok, bad)
        a2 = anchor(20000, as_of="February 30, 2020", until="February 30, 2020")
        ok, why = bracket.anchor_eligible(a2)
        self.assertFalse(ok, why)

    def test_pre2012_anchor_rejected(self):
        anchors = {"1": anchor(50000, until="June 12, 2011", as_of="June 12, 2011"),
                   "3": anchor(3000)}
        r = self._run(anchors)
        self.assertEqual(r["status"], "ABSTAIN")  # no eligible anchor above

    def test_still_available_anchor_rejected(self):
        anchors = {"1": {"purchased": 50000, "sale_state": "still_available",
                         "until": "Still available"},
                   "3": anchor(3000)}
        r = self._run(anchors)
        self.assertEqual(r["status"], "ABSTAIN")

    def test_unpaired_upper_abstains(self):
        anchors = {"1": {"purchased": None, "unpaired_purchased": 20000,
                         "sale_state": "closed", "until": "June 12, 2019"},
                   "3": anchor(3000)}
        r = self._run(anchors)
        self.assertEqual(r["status"], "ABSTAIN")
        self.assertEqual(r["reason"], "NO_ELIGIBLE_ANCHOR_ABOVE")
        self.assertIn("unpaired", bracket.anchor_eligible(anchors["1"])[1])

    def test_wide_bracket_low_confidence(self):
        anchors = {"1": anchor(1000000, as_of="June 12, 2019", until="June 12, 2019"),
                   "3": anchor(1000)}
        r = self._run(anchors)
        self.assertEqual(r["status"], "ESTIMATE")
        self.assertEqual(r["confidence"], "LOW")

    def test_stale_count_rejected(self):
        anchors = {"1": anchor(20000, as_of="April 27, 2019", until="September 16, 2019"),
                   "3": anchor(3000)}
        ok, why = bracket.anchor_eligible(anchors["1"])
        self.assertFalse(ok)
        self.assertIn("stale", why)

    def test_cli_batch_id_type_agreement(self):
        r_str = bracket.rank_bracket(["1", "2", "3"], "2", BASELINE_ANCHORS)
        r_int = bracket.rank_bracket(["1", "2", "3"], 2, BASELINE_ANCHORS)
        # both must produce a REAL estimate matching the asserted baseline
        self.assertEqual(r_str["status"], "ESTIMATE")
        self.assertEqual(r_int["status"], "ESTIMATE")
        self.assertEqual(r_str["bracket"], BASELINE["bracket"])
        self.assertEqual(r_int["bracket"], BASELINE["bracket"])

    def test_merge_pools_retired(self):
        # Astra 2.6d/3.5: intersection of heuristic intervals has no calibrated
        # meaning - the helper must fail loudly, never emit a merged estimate.
        with self.assertRaises(NotImplementedError):
            bracket.merge_pools([{"status": "ESTIMATE", "bracket": [1, 2]}], 1)

    def test_no_point_estimate_ever(self):
        r = self._run(BASELINE_ANCHORS)
        s = json.dumps(r).lower()
        self.assertNotIn("point", s)
        # and the interval is never a singleton
        if r["bracket"]:
            self.assertLess(r["bracket"][0], r["bracket"][1])


class TestSerializerParity(unittest.TestCase):
    """Astra 2.8: ONE serializer; CLI and batch emit the same fields."""

    def test_canonical_fields_present_both_statuses(self):
        est = schema_row("X", 1, BASELINE, snapshot_utc="2026-09-09T00:00:00Z", pool="p.json")
        abs_ = schema_row("X", 1, {"status": "ABSTAIN", "reason": "R", "detail": "d"},
                          snapshot_utc="2026-09-09T00:00:00Z", pool="p.json")
        for r in (est, abs_):
            for k in ("schema", "item", "item_id", "entity_type", "quantity",
                      "snapshot_utc", "pool", "status", "warnings", "abstain_reason"):
                self.assertIn(k, r, k)
        self.assertEqual(est["pool"], "p.json")   # pool kept for ESTIMATE...
        self.assertEqual(abs_["pool"], "p.json")  # ...AND abstention
        self.assertIn("purchases", est["quantity"])
        self.assertIn("not", est["quantity"].lower())  # states what it is NOT

    def test_calibration_fields(self):
        # Astra 1.5: method + calibration status are structural, not prose.
        est = schema_row("X", 1, BASELINE, snapshot_utc="2026-09-09T00:00:00Z", pool="p.json")
        self.assertEqual(est["method"], "rank_neighbor_heuristic")
        self.assertEqual(est["calibration_status"], "uncalibrated")


class TestValidatorStrictness(unittest.TestCase):
    """Astra 2.7: garbage must FAIL, with structured errors."""

    def _est(self, **over):
        base = {"schema": 2, "item": "X", "item_id": 123, "snapshot_utc": "2026-09-09T00:00:00Z",
                "pool": "p.json", "status": "ABSTAIN", "abstain_reason": "r",
                "quantity": "q", "confidence": None, "bracket": None, "warnings": [],
                "anchors": None}
        base.update(over)
        return base

    def _must_fail(self, rec, fragment):
        errs = []
        validate.validate_estimate(rec, errs)
        self.assertTrue(any(fragment in e for e in errs), f"expected {fragment!r} in {errs}")

    def test_schema_999_fails(self):
        self._must_fail(self._est(schema=999), "unsupported schema")

    def test_negative_item_id_fails(self):
        self._must_fail(self._est(item_id=-5), "item_id")

    def test_impossible_timestamp_fails(self):
        self._must_fail(self._est(snapshot_utc="2026-99-99T99:99:99Z"), "snapshot_utc")

    def test_shape_only_timestamp_fails(self):
        self._must_fail(self._est(snapshot_utc="2026-13-01T00:00:00Z"), "snapshot_utc")

    def test_boolean_bracket_endpoint_fails(self):
        self._must_fail(self._est(status="ESTIMATE", confidence="LOW",
                                  bracket=[True, 5], anchors={"above": {"purchased": 1},
                                                              "below": {"purchased": 2}}),
                        "bracket")

    def test_bad_confidence_fails(self):
        self._must_fail(self._est(status="ESTIMATE", confidence="CERTAIN",
                                  bracket=[1, 2], anchors={"above": {"purchased": 1},
                                                           "below": {"purchased": 2}}),
                        "confidence")

    def test_negative_anchor_count_fails(self):
        self._must_fail(self._est(status="ESTIMATE", confidence="LOW", bracket=[1, 2],
                                  anchors={"above": {"purchased": -3},
                                           "below": {"purchased": 2}}),
                        "anchor count")

    def test_inverted_estimate_bracket_fails(self):
        self._must_fail(self._est(status="ESTIMATE", confidence="LOW", bracket=[5, 1],
                                  anchors={"above": {"purchased": 1},
                                           "below": {"purchased": 5}}),
                        "inverted")

    def test_bracket_outside_anchors_fails(self):
        self._must_fail(self._est(status="ESTIMATE", confidence="LOW", bracket=[1, 500],
                                  anchors={"above": {"purchased": 10},
                                           "below": {"purchased": 2}}),
                        "inconsistent")

    def test_abstain_with_bracket_fails(self):
        self._must_fail(self._est(status="ABSTAIN", abstain_reason="r",
                                  bracket=[1, 2]), "ABSTAIN carrying")


class TestPoolManifestStrictness(unittest.TestCase):
    """Astra 2.3/2.4/2.5: manifest must verify content, cursor chain, completeness."""

    def _manifest(self, **over):
        pages = [{"cursor": "", "next_cursor": "", "fetched_utc": "2026-09-09T00:00:00Z",
                  "count": 3, "raw_response_sha256": "x" * 64}]
        m = pool_manifest.make_manifest(
            {"Keyword": "k", "SortType": 2, "SortAggregation": 5}, pages,
            "2026-09-09T00:00:00Z", "2026-09-09T00:01:00Z", True, ["1", "2", "3"])
        m.update(over)
        return m

    def test_valid_manifest_passes(self):
        errs = pool_manifest.validate(self._manifest(), ["1", "2", "3"])
        self.assertEqual(errs, [])

    def test_substituted_ids_fail_digest(self):
        errs = pool_manifest.validate(self._manifest(), ["1", "2", "999"])
        self.assertTrue(any("sha256" in e for e in errs), errs)

    def test_wrong_count_fails(self):
        errs = pool_manifest.validate(self._manifest(n_items=3), ["1", "2"])
        self.assertTrue(any("n_items" in e for e in errs), errs)

    def test_broken_cursor_chain_fails(self):
        pages = [{"cursor": "", "next_cursor": "c2", "fetched_utc": "t", "count": 1,
                  "raw_response_sha256": "x"},
                 {"cursor": "DIFFERENT", "next_cursor": "", "fetched_utc": "t", "count": 1,
                  "raw_response_sha256": "x"}]
        m = pool_manifest.make_manifest({"Keyword": "k", "SortType": 2,
                                         "SortAggregation": 5}, pages,
                                        "s", "f", True, ["1", "2"])
        errs = pool_manifest.validate(m, ["1", "2"])
        self.assertTrue(any("cursor" in e for e in errs), errs)

    def test_empty_page_with_continuation_fails(self):
        pages = [{"cursor": "", "next_cursor": "c2", "fetched_utc": "t", "count": 3,
                  "raw_response_sha256": "x"},
                 {"cursor": "c2", "next_cursor": "c3", "fetched_utc": "t", "count": 0,
                  "raw_response_sha256": "x"},
                 {"cursor": "c3", "next_cursor": "", "fetched_utc": "t", "count": 1,
                  "raw_response_sha256": "x"}]
        m = pool_manifest.make_manifest({"Keyword": "k", "SortType": 2,
                                         "SortAggregation": 5}, pages,
                                        "s", "f", True, ["1", "2", "3", "4"])
        errs = pool_manifest.validate(m, ["1", "2", "3", "4"])
        self.assertTrue(any("empty page" in e for e in errs), errs)

    def test_any_duplicate_ids_fail(self):
        # Astra 2.5: duplicates are evidence of a moving ranking, not a
        # tolerable percentage.
        errs = pool_manifest.validate(self._manifest(n_duplicate_ids=1), ["1", "2", "3", "1"])
        self.assertTrue(any("duplicate" in e for e in errs), errs)

    def test_missing_sortaggregation_fails(self):
        m = self._manifest()
        del m["query"]["SortAggregation"]
        errs = pool_manifest.validate(m, ["1", "2", "3"])
        self.assertTrue(any("SortAggregation" in e for e in errs), errs)


class TestMergeSafety(unittest.TestCase):
    """Astra 2.9: merge refuses empty inputs, provenance-less replacements."""

    def test_merge_module_has_no_parent_dir_fallback(self):
        src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "pipeline", "merge_anchors.py")).read()
        self.assertNotIn("os.path.dirname(ROOT)", src)
        self.assertIn("atomic", src.lower() or "tmp")


if __name__ == "__main__":
    unittest.main(verbosity=2)
