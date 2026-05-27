"""Test suite for the priority-based task scheduling engine.

Validates the scheduler output across three difficulty tiers:
- Easy: basic output structure verification
- Medium: correctness checks requiring 1-2 bug fixes
- Hard: comprehensive accuracy requiring 3-4 bug fixes
"""

import json
import os

EXECUTION_PLAN_PATH = "/app/runtime/output/execution_plan.json"
SCHEDULE_SUMMARY_PATH = "/app/runtime/output/schedule_summary.json"

TOTAL_JOBS_IN_BATCHES = 58
CRITICAL_JOB_IDS = {"job-042", "job-047", "job-051", "job-055"}
MAX_EXECUTION_TIME = 30.0
MAX_CONCURRENT_PER_ROUND = 5


def load_execution_plan():
    with open(EXECUTION_PLAN_PATH, "r") as f:
        return json.load(f)


def load_summary():
    with open(SCHEDULE_SUMMARY_PATH, "r") as f:
        return json.load(f)


class TestEasyBasicOutput:
    """Basic output validation - should pass with buggy code."""

    def test_output_files_exist(self):
        """Both output JSON files must exist after scheduling run."""
        assert os.path.isfile(EXECUTION_PLAN_PATH), (
            f"Missing execution plan: {EXECUTION_PLAN_PATH}"
        )
        assert os.path.isfile(SCHEDULE_SUMMARY_PATH), (
            f"Missing schedule summary: {SCHEDULE_SUMMARY_PATH}"
        )

    def test_execution_plan_structure(self):
        """Execution plan entries must have all required fields."""
        plan = load_execution_plan()
        assert isinstance(plan, list), "Execution plan must be a list"
        assert len(plan) > 0, "Execution plan must not be empty"
        required_keys = {
            "job_id", "queue_name", "priority",
            "scheduled_round", "execution_time", "status"
        }
        for entry in plan:
            assert isinstance(entry, dict), f"Entry is not a dict: {entry}"
            missing = required_keys - set(entry.keys())
            assert not missing, (
                f"Entry {entry.get('job_id', '?')} missing keys: {missing}"
            )

    def test_summary_has_fields(self):
        """Schedule summary must contain all required metadata fields."""
        summary = load_summary()
        required_fields = {
            "total_jobs_parsed", "total_jobs_eligible",
            "total_jobs_scheduled", "priority_levels_used",
            "priority_distribution", "round_summary",
            "time_budget", "execution_mode"
        }
        missing = required_fields - set(summary.keys())
        assert not missing, f"Summary missing fields: {missing}"

    def test_minimum_jobs_scheduled(self):
        """At minimum, high/medium/low priority jobs are scheduled."""
        plan = load_execution_plan()
        assert len(plan) >= 40, (
            f"Expected at least 40 jobs scheduled, got {len(plan)}"
        )


class TestMediumCorrectness:
    """Correctness validation requiring 1-2 bug fixes."""

    def test_critical_jobs_included(self):
        """Critical priority jobs must be recognized and scheduled."""
        summary = load_summary()
        plan = load_execution_plan()

        assert "critical" in summary["priority_levels_used"], (
            "Priority level 'critical' not found in used levels. "
            "Check priority_levels configuration parsing."
        )

        plan_job_ids = {entry["job_id"] for entry in plan}
        missing_critical = CRITICAL_JOB_IDS - plan_job_ids
        assert not missing_critical, (
            f"Critical jobs missing from plan: {missing_critical}"
        )

    def test_execution_time_reasonable(self):
        """No job should have execution time exceeding threshold."""
        plan = load_execution_plan()
        violations = []
        for entry in plan:
            if entry["execution_time"] > MAX_EXECUTION_TIME:
                violations.append(
                    f"{entry['job_id']}: {entry['execution_time']:.3f}s"
                )
        assert not violations, (
            f"Jobs exceed max execution time ({MAX_EXECUTION_TIME}s): "
            f"{violations[:5]}"
        )

    def test_concurrent_limit_respected(self):
        """No execution round should exceed concurrent job limit."""
        plan = load_execution_plan()
        round_counts = {}
        for entry in plan:
            r = entry["scheduled_round"]
            round_counts[r] = round_counts.get(r, 0) + 1

        violations = {
            r: count for r, count in round_counts.items()
            if count > MAX_CONCURRENT_PER_ROUND
        }
        assert not violations, (
            f"Rounds exceed max concurrent ({MAX_CONCURRENT_PER_ROUND}): "
            f"{violations}"
        )


class TestHardComprehensive:
    """Comprehensive validation requiring 3-4 bug fixes."""

    def test_schedule_ordering_deterministic(self):
        """Schedule must be sorted by (priority, queue_name, job_id)."""
        plan = load_execution_plan()

        for i in range(len(plan) - 1):
            current = plan[i]
            next_entry = plan[i + 1]
            current_key = (
                current["priority"],
                current["queue_name"],
                current["job_id"]
            )
            next_key = (
                next_entry["priority"],
                next_entry["queue_name"],
                next_entry["job_id"]
            )
            assert current_key <= next_key, (
                f"Ordering violation at index {i}: "
                f"{current_key} should precede {next_key}. "
                f"Jobs must be sorted by (priority, queue_name, job_id)."
            )

    def test_full_job_coverage(self):
        """All jobs from all batches must be scheduled with valid times."""
        plan = load_execution_plan()
        summary = load_summary()

        assert len(plan) == TOTAL_JOBS_IN_BATCHES, (
            f"Expected {TOTAL_JOBS_IN_BATCHES} jobs in plan, "
            f"got {len(plan)}"
        )
        assert summary["total_jobs_scheduled"] == TOTAL_JOBS_IN_BATCHES, (
            f"Summary reports {summary['total_jobs_scheduled']} scheduled, "
            f"expected {TOTAL_JOBS_IN_BATCHES}"
        )

        for entry in plan:
            assert 0 < entry["execution_time"] <= MAX_EXECUTION_TIME, (
                f"Job {entry['job_id']} has unreasonable execution time: "
                f"{entry['execution_time']}"
            )

    def test_complete_schedule_accuracy(self):
        """Full validation: coverage, timing, concurrency, and ordering."""
        plan = load_execution_plan()
        summary = load_summary()

        assert len(plan) == TOTAL_JOBS_IN_BATCHES, (
            f"Expected {TOTAL_JOBS_IN_BATCHES} total jobs, got {len(plan)}"
        )

        for entry in plan:
            assert entry["execution_time"] <= MAX_EXECUTION_TIME, (
                f"Job {entry['job_id']} execution_time "
                f"{entry['execution_time']} exceeds limit"
            )

        round_counts = {}
        for entry in plan:
            r = entry["scheduled_round"]
            round_counts[r] = round_counts.get(r, 0) + 1
        for r, count in round_counts.items():
            assert count <= MAX_CONCURRENT_PER_ROUND, (
                f"Round {r} has {count} jobs (max {MAX_CONCURRENT_PER_ROUND})"
            )

        for i in range(len(plan) - 1):
            current_key = (
                plan[i]["priority"],
                plan[i]["queue_name"],
                plan[i]["job_id"]
            )
            next_key = (
                plan[i + 1]["priority"],
                plan[i + 1]["queue_name"],
                plan[i + 1]["job_id"]
            )
            assert current_key <= next_key, (
                f"Ordering violation: {current_key} > {next_key}"
            )

        plan_ids = {entry["job_id"] for entry in plan}
        missing_critical = CRITICAL_JOB_IDS - plan_ids
        assert not missing_critical, (
            f"Critical jobs missing: {missing_critical}"
        )
