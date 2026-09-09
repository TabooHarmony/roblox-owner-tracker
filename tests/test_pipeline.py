"""Fixture tests for the hardened pipeline. Run: python3 tests/test_pipeline.py"""
import json, os, sys, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pipeline"))
import parse_wiki, bracket


class TestParser(unittest.TestCase):
    def test_comment_poisoning(self):
        wt = "As of January 1, 2026 <!-- old value: purchased 9,999,999 times --> it has been purchased 1,000 times. As of January 1, 2026."
        r = parse_wiki.parse(wt)
        self.assertEqual(r["purchased"], 1000)

    def test_purchase_without_asof_not_paired(self):
        r = parse_wiki.parse("It has been purchased 5,000 times.")
        self.assertIsNone(r["purchased"])
        self.assertEqual(r["unpaired_purchased"], 5000)
        self.assertIn("purchased_unpaired_no_asof", r["parse_notes"])

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

    def test_template_residue_flagged_not_consumed(self):
        r = parse_wiki.parse("| until = | kind = clothing\n| id = 12345")
        self.assertEqual(r["sale_state"], "unknown")
        self.assertIsNone(r["until"])
        self.assertTrue(any(n.startswith("unparsed_until") for n in r["parse_notes"]))
        self.assertEqual(r["item_id"], 12345)

    def test_paired_sentence_real_phrasing(self):
        r = parse_wiki.parse("As of January 1, 2020, it has been purchased 8,891 times and favorited 1,719 times.")
        self.assertEqual(r["purchased"], 8891)
        self.assertEqual(r["purchased_as_of"], "January 1, 2020")
        self.assertEqual(r["favorites"], 1719)

    def test_bundle_id_fallback(self):
        r = parse_wiki.parse("| catalog id = \n| bundle id = 555")
        self.assertEqual(r["item_id"], 555)
        self.assertIn("id_from_bundle_id", r["parse_notes"])

    def test_was_purchased_adjacent_asof_sentence(self):
        # Wiki off-sale convention: count sentence, then As-of sentence next.
        # ("Before going off-sale, it was purchased N times. As of X, ...")
        r = parse_wiki.parse("Before going off-sale, it was purchased 67,497 times. As of June 16, 2018, it has been favorited 1,000 times.")
        self.assertEqual(r["purchased"], 67497)
        self.assertEqual(r["purchased_as_of"], "June 16, 2018")

    def test_was_purchased_case_abbrev_month(self):
        r = parse_wiki.parse("| until = 14 mar 2016\n\nIt was purchased 8,891 times. As of NOVEMBER 24, 2023, things happened.")
        self.assertEqual(r["sale_state"], "closed")
        self.assertEqual(r["until"], "14 mar 2016")

    def test_times_backtracking_bug(self):
        # 'times?' + '[^.]*?' could eat the s and match ACROSS the period.
        r = parse_wiki.parse("It was purchased 100 times. Some unrelated sentence. As of January 1, 2020, things happened.")
        self.assertIsNone(r["purchased"])
        self.assertEqual(r["unpaired_purchased"], 100)

    def test_adjacent_sentence_gap_limited(self):
        # Count -> unrelated sentence -> As-of: must NOT pair.
        r = parse_wiki.parse("It has been purchased 5,000 times. Unrelated filler here. As of May 1, 2021, it was favorited 30 times.")
        self.assertIsNone(r["purchased"])
        self.assertEqual(r["unpaired_purchased"], 5000)


class TestEngine(unittest.TestCase):
    def test_no_anchors_abstains(self):
        r = bracket.rank_bracket([1, 2], 2, {})
        self.assertEqual(r["status"], "ABSTAIN")
        self.assertEqual(r["reason"], "NO_ELIGIBLE_ANCHOR_ABOVE_AND_BELOW")

    def test_target_missing_abstains(self):
        r = bracket.rank_bracket([1], 9, {"1": {"purchased": 5, "sale_state": "closed", "until": "June 12, 2019"}})
        self.assertEqual(r["status"], "ABSTAIN")
        self.assertEqual(r["reason"], "TARGET_NOT_IN_POOL")

    def test_pre2012_anchor_rejected(self):
        anchors = {
            "1": {"purchased": 50000, "sale_state": "closed", "until": "June 12, 2011", "title": "old"},
            "3": {"purchased": 3000, "sale_state": "closed", "until": "March 5, 2020", "title": "ok"},
        }
        r = bracket.rank_bracket([1, 2, 3], 2, anchors)
        self.assertEqual(r["status"], "ABSTAIN")  # no eligible anchor above

    def test_still_available_anchor_rejected(self):
        anchors = {
            "1": {"purchased": 50000, "sale_state": "still_available", "until": "Still available"},
            "3": {"purchased": 3000, "sale_state": "closed", "until": "March 5, 2020"},
        }
        r = bracket.rank_bracket([1, 2, 3], 2, anchors)
        self.assertEqual(r["status"], "ABSTAIN")

    def test_unpaired_upper_flagged(self):
        anchors = {
            "1": {"purchased": None, "unpaired_purchased": 20000, "sale_state": "closed", "until": "June 12, 2019"},
            "3": {"purchased": 3000, "sale_state": "closed", "until": "March 5, 2020"},
        }
        r = bracket.rank_bracket([1, 2, 3], 2, anchors)
        self.assertEqual(r["status"], "ESTIMATE")
        self.assertTrue(any("unpaired" in w for w in r["warnings"]))

    def test_wide_bracket_low_confidence(self):
        anchors = {
            "1": {"purchased": 1000000, "sale_state": "closed", "until": "June 12, 2019"},
            "3": {"purchased": 1000, "sale_state": "closed", "until": "March 5, 2020"},
        }
        r = bracket.rank_bracket([1, 2, 3], 2, anchors)
        self.assertEqual(r["confidence"], "LOW")

    def test_conflicting_pools_abstain(self):
        r = bracket.merge_pools(
            [{"status": "ESTIMATE", "bracket": [9000, 10000]},
             {"status": "ESTIMATE", "bracket": [20000, 22000]}], 1)
        self.assertEqual(r["status"], "ABSTAIN")
        self.assertEqual(r["reason"], "CONFLICTING_POOLS")

    def test_overlapping_pools_intersect(self):
        r = bracket.merge_pools(
            [{"status": "ESTIMATE", "bracket": [9000, 10500]},
             {"status": "ESTIMATE", "bracket": [9500, 10000]}], 1)
        self.assertEqual(r["status"], "ESTIMATE")
        self.assertEqual(r["bracket"], [9500, 10000])

    def test_no_point_estimate_ever(self):
        anchors = {
            "1": {"purchased": 10000, "sale_state": "closed", "until": "June 12, 2019"},
            "3": {"purchased": 9000, "sale_state": "closed", "until": "March 5, 2020"},
        }
        r = bracket.rank_bracket([1, 2, 3], 2, anchors)
        self.assertNotIn("point", json.dumps(r).lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
