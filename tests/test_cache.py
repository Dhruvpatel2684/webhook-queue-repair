"""Graduated test suite for the multi-tier cache eviction engine.

Three difficulty tiers:
  - TestEasyBasicOutput: structural checks that pass even with bugs present
  - TestMediumCorrectness: require fixing 1-2 bugs to pass
  - TestHardComprehensive: require fixing 3-4 bugs to pass
"""

import json
import os
import unittest

EVICTION_PLAN_PATH = "/app/runtime/output/eviction_plan.json"
CACHE_REPORT_PATH = "/app/runtime/output/cache_report.json"
TOTAL_ENTRIES = 58
PERSISTENT_ENTRY_KEYS = {"cache-051", "cache-054", "cache-056", "cache-058"}

REQUIRED_PLAN_FIELDS = [
    "entry_key",
    "tier_name",
    "eviction_score",
    "time_window",
    "hit_count",
    "decision",
]

REQUIRED_REPORT_FIELDS = [
    "total_entries",
    "entries_evaluated",
    "tiers_processed",
    "total_windows",
    "eviction_rate",
    "entries_per_tier",
]


def load_json(path):
    with open(path, "r") as f:
        return json.load(f)


class TestEasyBasicOutput(unittest.TestCase):
    """Basic structural tests that pass regardless of bug presence."""

    def test_output_files_exist(self):
        """Both output files must be present after engine execution."""
        self.assertTrue(
            os.path.isfile(EVICTION_PLAN_PATH),
            f"Missing eviction plan at {EVICTION_PLAN_PATH}",
        )
        self.assertTrue(
            os.path.isfile(CACHE_REPORT_PATH),
            f"Missing cache report at {CACHE_REPORT_PATH}",
        )

    def test_eviction_plan_structure(self):
        """Each entry in the eviction plan must contain all required fields."""
        plan = load_json(EVICTION_PLAN_PATH)
        self.assertIsInstance(plan, list)
        self.assertGreater(len(plan), 0, "Eviction plan is empty")
        for idx, entry in enumerate(plan):
            for field in REQUIRED_PLAN_FIELDS:
                self.assertIn(
                    field,
                    entry,
                    f"Entry {idx} missing field '{field}'",
                )

    def test_report_has_fields(self):
        """Cache report must contain all metadata fields."""
        report = load_json(CACHE_REPORT_PATH)
        for field in REQUIRED_REPORT_FIELDS:
            self.assertIn(
                field,
                report,
                f"Report missing field '{field}'",
            )

    def test_minimum_entries_evaluated(self):
        """At least 40 entries must be evaluated (l1/l2/l3 tiers always pass)."""
        report = load_json(CACHE_REPORT_PATH)
        self.assertGreaterEqual(
            report["entries_evaluated"],
            40,
            "Too few entries evaluated; check data loading",
        )


class TestMediumCorrectness(unittest.TestCase):
    """Correctness tests requiring 1-2 bug fixes."""

    def test_persistent_tier_included(self):
        """The persistent tier must be included in processed tiers."""
        report = load_json(CACHE_REPORT_PATH)
        self.assertIn(
            "persistent",
            report["tiers_processed"],
            "Tier 'persistent' not found in tiers_processed. "
            "Check how cache_tiers are parsed from config.",
        )

    def test_hit_count_reasonable(self):
        """No entry should have a hit_count exceeding reasonable bounds."""
        plan = load_json(EVICTION_PLAN_PATH)
        for entry in plan:
            self.assertLessEqual(
                entry["hit_count"],
                60,
                f"Entry {entry['entry_key']} has unreasonable hit_count "
                f"{entry['hit_count']}. Check hit accumulation logic.",
            )

    def test_eviction_threshold_applied(self):
        """Eviction rate must be between 0.3 and 0.7 for proper threshold."""
        report = load_json(CACHE_REPORT_PATH)
        rate = report["eviction_rate"]
        self.assertGreaterEqual(
            rate,
            0.3,
            f"Eviction rate {rate} too low. "
            "Verify the correct eviction_threshold is being read.",
        )
        self.assertLessEqual(
            rate,
            0.7,
            f"Eviction rate {rate} too high. "
            "Check threshold comparison logic.",
        )


class TestHardComprehensive(unittest.TestCase):
    """Comprehensive tests requiring 3-4 bug fixes."""

    def test_eviction_ordering_deterministic(self):
        """Eviction plan must be sorted by (eviction_score, tier_name, entry_key)."""
        plan = load_json(EVICTION_PLAN_PATH)
        self.assertGreater(len(plan), 0, "Plan is empty")

        sort_keys = [
            (e["eviction_score"], e["tier_name"], e["entry_key"]) for e in plan
        ]
        expected = sorted(sort_keys)
        self.assertEqual(
            sort_keys,
            expected,
            "Entries must be sorted by (eviction_score, tier_name, entry_key). "
            "Check sort key in run_cache.py",
        )

    def test_full_entry_coverage(self):
        """All 58 entries must be evaluated with valid hit counts."""
        plan = load_json(EVICTION_PLAN_PATH)
        self.assertEqual(
            len(plan),
            TOTAL_ENTRIES,
            f"Expected {TOTAL_ENTRIES} entries in plan, got {len(plan)}. "
            "Check tier filtering includes all configured tiers.",
        )

        for entry in plan:
            self.assertGreater(
                entry["hit_count"],
                0,
                f"Entry {entry['entry_key']} has zero hit_count",
            )
            self.assertLessEqual(
                entry["hit_count"],
                55,
                f"Entry {entry['entry_key']} hit_count {entry['hit_count']} "
                "exceeds maximum expected value of 55",
            )

    def test_complete_cache_accuracy(self):
        """Full validation: entry count, eviction rate, ordering, and tier coverage."""
        plan = load_json(EVICTION_PLAN_PATH)
        report = load_json(CACHE_REPORT_PATH)

        self.assertEqual(
            len(plan),
            TOTAL_ENTRIES,
            f"Expected {TOTAL_ENTRIES} entries, got {len(plan)}",
        )

        rate = report["eviction_rate"]
        self.assertGreaterEqual(rate, 0.3, f"Eviction rate {rate} too low")
        self.assertLessEqual(rate, 0.7, f"Eviction rate {rate} too high")

        sort_keys = [
            (e["eviction_score"], e["tier_name"], e["entry_key"]) for e in plan
        ]
        self.assertEqual(
            sort_keys,
            sorted(sort_keys),
            "Plan is not correctly sorted",
        )

        self.assertIn("persistent", report["tiers_processed"])

        persistent_in_plan = {
            e["entry_key"] for e in plan if e["tier_name"] == "persistent"
        }
        self.assertEqual(
            persistent_in_plan,
            PERSISTENT_ENTRY_KEYS,
            "Not all persistent entries are present in eviction plan",
        )


if __name__ == "__main__":
    unittest.main()
