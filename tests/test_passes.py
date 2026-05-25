"""Test suite for compiler pass scheduler output validation."""

import json
import hashlib
import os

import pytest

OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "/app/output")


@pytest.fixture(scope="module")
def schedule():
    path = os.path.join(OUTPUT_DIR, "schedule.json")
    assert os.path.exists(path), "schedule.json not found in output directory"
    with open(path) as f:
        return json.load(f)


@pytest.fixture(scope="module")
def report():
    path = os.path.join(OUTPUT_DIR, "report.json")
    assert os.path.exists(path), "report.json not found in output directory"
    with open(path) as f:
        return json.load(f)


# --- Tier 1: Basic structural tests (pass with buggy code) ---


class TestBasicStructure:
    def test_output_files_exist(self):
        """Both output files must be present."""
        assert os.path.exists(os.path.join(OUTPUT_DIR, "schedule.json")), \
            "schedule.json missing from output"
        assert os.path.exists(os.path.join(OUTPUT_DIR, "report.json")), \
            "report.json missing from output"

    def test_schedule_has_required_fields(self, schedule):
        """Schedule JSON must contain all required top-level fields."""
        required = ["total_phases", "total_scheduled", "total_rejected",
                    "total_blocked", "assignments", "rejected_passes", "blocked_passes"]
        for field in required:
            assert field in schedule, f"Missing field '{field}' in schedule.json"

    def test_report_has_required_fields(self, report):
        """Report JSON must contain all required top-level fields."""
        assert "category_summaries" in report, "Missing 'category_summaries' in report.json"
        assert "statistics" in report, "Missing 'statistics' in report.json"
        stats = report["statistics"]
        assert "total_passes_processed" in stats, "Missing 'total_passes_processed' in statistics"
        assert "total_phases" in stats, "Missing 'total_phases' in statistics"

    def test_pass_assignments_structure(self, schedule):
        """Each assignment entry must have the expected fields."""
        required_keys = ["pass_id", "module_name", "category", "priority", "phase", "position"]
        for entry in schedule["assignments"]:
            for key in required_keys:
                assert key in entry, f"Assignment missing field '{key}'"

    def test_report_categories_sorted(self, report):
        """Category summaries must be in alphabetical order."""
        categories = [s["category"] for s in report["category_summaries"]]
        assert categories == sorted(categories), \
            "Category summaries are not in alphabetical order"

    def test_assignments_ordered_by_phase(self, schedule):
        """Assignments must be ordered by phase number."""
        phases = [a["phase"] for a in schedule["assignments"]]
        assert phases == sorted(phases), \
            "Assignments are not ordered by phase"

    def test_total_passes_processed(self, schedule, report):
        """Total passes processed must equal scheduled + rejected + blocked."""
        total = (schedule["total_scheduled"] + schedule["total_rejected"]
                 + schedule["total_blocked"])
        assert total == 55, \
            f"Expected 55 total passes processed, got {total}"
        assert report["statistics"]["total_passes_processed"] == 55, \
            f"Report statistics show {report['statistics']['total_passes_processed']} passes, expected 55"


# --- Tier 2: Medium tests (require Bug A fix) ---


class TestCategoryFiltering:
    def test_no_rejected_passes(self, schedule):
        """All passes in the manifest should be schedulable.

        Expected 0 rejected passes when all categories are recognized.
        """
        rejected_count = schedule["total_rejected"]
        assert rejected_count == 0, \
            f"Expected 0 rejected, got {rejected_count}. All passes in the manifest should be schedulable."

    def test_total_categories_count(self, report):
        """Report must contain summaries for all active categories."""
        cat_count = len(report["category_summaries"])
        assert cat_count == 4, \
            f"Expected 4 categories in report, got {cat_count}."

    def test_lowering_category_present(self, report):
        """The lowering category must appear in the output summaries."""
        categories = [s["category"] for s in report["category_summaries"]]
        assert "lowering" in categories, \
            "lowering category must appear in output."


# --- Tier 3: Hard tests (require Bugs B + C + E) ---


class TestSchedulingCorrectness:
    def test_total_phases(self, schedule):
        """Phase count must match expected value for production capacity."""
        phase_count = schedule["total_phases"]
        assert phase_count == 10, \
            f"Expected 10 phases, got {phase_count}. Check the phase capacity parameter."

    def test_category_pass_counts(self, report):
        """Per-category pass counts must reflect single-phase values."""
        summaries = {s["category"]: s for s in report["category_summaries"]}

        for cat, summary in summaries.items():
            assert summary["total_passes"] <= 6, \
                f"Category '{cat}' shows {summary['total_passes']} passes. " \
                f"Pass counts per category are too high for a single phase."

    def test_no_incorrectly_blocked(self, schedule):
        """Passes with chain depth exactly at the limit should be schedulable."""
        blocked = set(schedule["blocked_passes"])
        depth_4_passes = [
            "pass-F13", "pass-F14", "pass-F17",
            "pass-M14", "pass-M15", "pass-M17",
            "pass-B13", "pass-B14", "pass-B17", "pass-B18",
        ]
        incorrectly_blocked = [p for p in depth_4_passes if p in blocked]
        assert len(incorrectly_blocked) == 0, \
            f"Passes with chain depth 4 should be schedulable, not blocked. " \
            f"Found {len(incorrectly_blocked)} incorrectly blocked."


# --- Tier 4: Hardest tests (require ALL bugs fixed) ---


class TestFullCorrectness:
    def test_schedule_digest(self, schedule):
        """Schedule content hash must match expected value."""
        digest_input = json.dumps(schedule, sort_keys=True)
        digest = hashlib.sha256(digest_input.encode()).hexdigest()[:16]
        expected = "b95bca74771a1b80"
        assert digest == expected, \
            f"Schedule digest mismatch: got {digest}, expected {expected}."

    def test_priority_tiebreaker(self, schedule):
        """Passes with identical priority and submission order must be ordered deterministically."""
        assignments = schedule["assignments"]
        position_map = {}
        for i, entry in enumerate(assignments):
            position_map[entry["pass_id"]] = i

        assert "pass-M08" in position_map, "pass-M08 not found in schedule"
        assert "pass-F12" in position_map, "pass-F12 not found in schedule"

        m08_idx = position_map["pass-M08"]
        f12_idx = position_map["pass-F12"]
        assert m08_idx < f12_idx, \
            f"pass-M08 should appear before pass-F12 in the schedule."
