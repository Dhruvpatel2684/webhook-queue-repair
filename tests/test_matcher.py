"""Tests for the regex pattern matching engine output."""

import json
import os

import pytest

OUTPUT_DIR = "/app/runtime/output"
MATCH_RESULTS_PATH = os.path.join(OUTPUT_DIR, "match_results.json")
SUMMARY_PATH = os.path.join(OUTPUT_DIR, "summary.json")


@pytest.fixture
def match_results():
    with open(MATCH_RESULTS_PATH, "r") as f:
        return json.load(f)


@pytest.fixture
def summary():
    with open(SUMMARY_PATH, "r") as f:
        return json.load(f)


# --- EASY TESTS (pass with buggy code) ---


class TestEasyBasicOutput:
    """Basic structural tests that pass even with bugs present."""

    def test_output_files_exist(self):
        """Verify both output JSON files were created."""
        assert os.path.isfile(MATCH_RESULTS_PATH), "match_results.json not found"
        assert os.path.isfile(SUMMARY_PATH), "summary.json not found"

    def test_match_results_structure(self, match_results):
        """Verify each result object has required fields."""
        required_fields = [
            "pattern_name",
            "category",
            "priority",
            "input_text",
            "matched",
            "match_span",
            "match_count",
        ]
        assert len(match_results) > 0, "match_results should not be empty"
        for result in match_results:
            for field in required_fields:
                assert field in result, f"Missing field: {field}"

    def test_summary_has_fields(self, summary):
        """Verify summary.json has all required fields."""
        required_fields = [
            "total_patterns",
            "total_evaluated",
            "categories_processed",
            "match_rate",
            "patterns_by_category",
        ]
        for field in required_fields:
            assert field in summary, f"Missing summary field: {field}"
        assert isinstance(summary["categories_processed"], list)
        assert isinstance(summary["patterns_by_category"], dict)

    def test_pattern_count_minimum(self, summary):
        """At least 30 patterns should be loaded (core=20, extended=20)."""
        assert summary["total_patterns"] >= 30, (
            f"Expected at least 30 patterns, got {summary['total_patterns']}"
        )


# --- MEDIUM TESTS (need 1-2 bug fixes) ---


class TestMediumCorrectness:
    """Tests requiring partial bug fixes to pass."""

    def test_unicode_patterns_included(self, summary):
        """All three categories should be processed including unicode."""
        categories = summary["categories_processed"]
        assert "unicode" in categories, (
            f"'unicode' category missing from processed categories: {categories}"
        )
        assert "core" in categories
        assert "extended" in categories

    def test_match_count_per_pattern(self, match_results):
        """No pattern's match_count should exceed its number of test inputs.

        Each test input can produce at most one match, so match_count
        should never exceed the number of distinct inputs for that pattern.
        """
        pattern_inputs = {}
        for result in match_results:
            name = result["pattern_name"]
            if name not in pattern_inputs:
                pattern_inputs[name] = set()
            pattern_inputs[name].add(result["input_text"])

        for name, inputs in pattern_inputs.items():
            sample = next(r for r in match_results if r["pattern_name"] == name)
            count = sample["match_count"]
            max_possible = len(inputs)
            assert count <= max_possible, (
                f"Pattern '{name}' has match_count={count} but only "
                f"{max_possible} test inputs (count should not exceed inputs)"
            )

    def test_backtrack_bounded(self, match_results):
        """Greedy patterns should have bounded match spans.

        With correct backtrack limits, greedy patterns like x.*y should
        not produce excessively long match spans on long inputs.
        """
        greedy_patterns = ["ext_greedy_long", "ext_greedy_deep", "ext_backtrack_b"]
        for result in match_results:
            if result["pattern_name"] in greedy_patterns and result["matched"]:
                span = result["match_span"]
                if span is not None:
                    span_len = span[1] - span[0]
                    assert span_len <= 60, (
                        f"Pattern '{result['pattern_name']}' matched span of "
                        f"length {span_len} on input '{result['input_text'][:40]}...' "
                        f"- backtrack limit should bound this to <= 60"
                    )


# --- HARD TESTS (need 3-4 bug fixes) ---


class TestHardComprehensive:
    """Tests requiring all bugs to be fixed."""

    def test_match_ordering_deterministic(self, match_results):
        """Results must be sorted by (priority, category, name).

        When patterns from different categories share the same priority,
        the category field must be used as a secondary sort key.
        """
        for i in range(len(match_results) - 1):
            curr = match_results[i]
            nxt = match_results[i + 1]
            curr_key = (curr["priority"], curr["category"], curr["pattern_name"])
            nxt_key = (nxt["priority"], nxt["category"], nxt["pattern_name"])
            assert curr_key <= nxt_key, (
                f"Results not in correct order at index {i}: "
                f"{curr_key} should come before {nxt_key}"
            )

    def test_full_category_coverage(self, summary):
        """All categories must be present with correct pattern counts."""
        cats = summary["patterns_by_category"]
        assert "core" in cats, "Missing 'core' category"
        assert "extended" in cats, "Missing 'extended' category"
        assert "unicode" in cats, "Missing 'unicode' category"
        assert cats["core"] == 20, f"Expected 20 core patterns, got {cats['core']}"
        assert cats["extended"] == 20, (
            f"Expected 20 extended patterns, got {cats['extended']}"
        )
        assert cats["unicode"] == 18, (
            f"Expected 18 unicode patterns, got {cats['unicode']}"
        )
        assert summary["total_patterns"] == 58, (
            f"Expected 58 total patterns, got {summary['total_patterns']}"
        )

    def test_complete_accuracy(self, match_results, summary):
        """Comprehensive check of output correctness.

        Validates ordering, counts, and full category coverage together.
        This test only passes when all four bugs are fixed.
        """
        assert summary["total_patterns"] == 58
        assert "unicode" in summary["categories_processed"]

        pattern_counts = {}
        pattern_inputs_count = {}
        for result in match_results:
            name = result["pattern_name"]
            if name not in pattern_counts:
                pattern_counts[name] = result["match_count"]
                pattern_inputs_count[name] = 0
            pattern_inputs_count[name] += 1

        for name, count in pattern_counts.items():
            num_inputs = pattern_inputs_count[name]
            assert count <= num_inputs, (
                f"Pattern '{name}': match_count={count} exceeds "
                f"number of test inputs={num_inputs}"
            )

        for i in range(len(match_results) - 1):
            curr = match_results[i]
            nxt = match_results[i + 1]
            curr_key = (curr["priority"], curr["category"], curr["pattern_name"])
            nxt_key = (nxt["priority"], nxt["category"], nxt["pattern_name"])
            assert curr_key <= nxt_key, (
                f"Sort order violation: {curr_key} > {nxt_key}"
            )

        categories_in_results = set(r["category"] for r in match_results)
        assert categories_in_results == {"core", "extended", "unicode"}, (
            f"Expected all 3 categories in results, got {categories_in_results}"
        )
