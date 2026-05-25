"""
Tests for cgroup-scheduler-repair task.
Validates the job scheduler engine output files.

Test tiers:
  - Tier 1 (basic): Structure checks that pass even with buggy code
  - Tier 2 (medium): Require fixing resource pool filtering (Bug A)
  - Tier 3 (hard): Require fixing concurrency limit + aggregation (Bugs B + C)
  - Tier 4 (hardest): Require all bugs fixed simultaneously
"""

import json
import os


OUTPUT_DIR = "/app/runtime/output"
SCHEDULE_PATH = os.path.join(OUTPUT_DIR, "schedule.json")
POOL_REPORT_PATH = os.path.join(OUTPUT_DIR, "pool_report.json")


def load_schedule():
    """Load schedule.json output file."""
    with open(SCHEDULE_PATH, "r") as f:
        return json.load(f)


def load_pool_report():
    """Load pool_report.json output file."""
    with open(POOL_REPORT_PATH, "r") as f:
        return json.load(f)


# ============================================================
# TIER 1: Basic structure (pass even with buggy code)
# ============================================================

def test_output_files_exist():
    """Both output files must be created in /app/runtime/output/ directory."""
    assert os.path.exists(SCHEDULE_PATH), (
        f"schedule.json not found at {SCHEDULE_PATH}"
    )
    assert os.path.exists(POOL_REPORT_PATH), (
        f"pool_report.json not found at {POOL_REPORT_PATH}"
    )


def test_schedule_has_required_fields():
    """Schedule output must have required top-level fields."""
    data = load_schedule()
    required = ["total_scheduled", "total_rejected", "total_rounds",
                "assignments", "rejected"]
    for field in required:
        assert field in data, f"Missing required field '{field}' in schedule.json"
    assert isinstance(data["assignments"], list), "'assignments' must be a list"
    assert data["total_scheduled"] == len(data["assignments"]), (
        "total_scheduled must equal length of assignments array"
    )


def test_pool_report_has_required_fields():
    """Pool report must have all required top-level fields."""
    data = load_pool_report()
    required = ["total_pools", "total_scheduled", "total_rejected",
                "schedule_digest", "pools"]
    for field in required:
        assert field in data, f"Missing required field '{field}' in pool_report.json"


def test_schedule_assignments_structure():
    """Each assignment must have required fields with correct types."""
    data = load_schedule()
    required_fields = ["job_id", "queue_name", "priority", "resource_pool", "round"]
    for entry in data["assignments"][:5]:
        for field in required_fields:
            assert field in entry, f"Assignment missing field '{field}'"


def test_pool_report_pools_sorted():
    """Pool report list must be sorted by pool_id alphabetically."""
    data = load_pool_report()
    pool_ids = [p["pool_id"] for p in data["pools"]]
    assert pool_ids == sorted(pool_ids), (
        "Pools not sorted alphabetically by pool_id"
    )


def test_assignments_ordered_by_round():
    """Assignments within the same round must appear together."""
    data = load_schedule()
    rounds_seen = []
    for entry in data["assignments"]:
        if not rounds_seen or rounds_seen[-1] != entry["round"]:
            rounds_seen.append(entry["round"])
    assert rounds_seen == sorted(rounds_seen), (
        "Assignments not grouped/ordered by round number"
    )


def test_total_jobs_processed():
    """Total scheduled + rejected must equal 54 (all jobs from 3 queues)."""
    data = load_schedule()
    total = data["total_scheduled"] + data["total_rejected"]
    assert total == 54, (
        f"Expected 54 total jobs, got {total} "
        f"(scheduled={data['total_scheduled']}, rejected={data['total_rejected']})"
    )


# ============================================================
# TIER 2: Medium (requires fixing Bug A - pool filtering)
# ============================================================

def test_no_rejected_jobs():
    """All 54 jobs should be scheduled when pool filtering is correct.
    Check how resource_pools are parsed from scheduler.ini -
    all pools listed in the config are valid targets."""
    data = load_schedule()
    assert data["total_rejected"] == 0, (
        f"Expected 0 rejected jobs, got {data['total_rejected']}. "
        f"Check how get_resource_pools() parses the comma-separated pool list "
        f"from scheduler.ini - whitespace in the list may cause pool_network "
        f"to be unrecognized."
    )


def test_total_pools_count():
    """All 4 resource pools must appear in the pool report."""
    data = load_pool_report()
    assert data["total_pools"] == 4, (
        f"Expected 4 pools, got {data['total_pools']}. "
        f"If pool_network is missing, check config parsing for whitespace issues."
    )


def test_pool_network_present():
    """pool_network must be present in the pool report output."""
    data = load_pool_report()
    pool_ids = {p["pool_id"] for p in data["pools"]}
    assert "pool_network" in pool_ids, (
        f"pool_network missing from output. Found pools: {sorted(pool_ids)}. "
        f"Look at get_resource_pools() in priority_scheduler.py."
    )


# ============================================================
# TIER 3: Hard (requires fixing Bugs B + C)
# ============================================================

def test_total_rounds():
    """Scheduler must produce exactly 7 rounds with correct concurrency.
    The production-tuned max_concurrent from [scheduler.production]
    section of scheduler.ini should be used."""
    data = load_schedule()
    assert data["total_rounds"] == 7, (
        f"Expected 7 rounds, got {data['total_rounds']}. "
        f"Check which config section max_concurrent is read from - "
        f"the [scheduler.production] section has the tuned value."
    )


def test_pool_job_counts_last_round():
    """Pool job_count must reflect the most recent scheduling round.
    The pool summary represents current allocation pressure from the
    final round, not cumulative totals across all rounds."""
    data = load_pool_report()
    pools = {p["pool_id"]: p for p in data["pools"]}

    # Last round has few jobs per pool (1-2 each)
    for pool_id, pool_data in pools.items():
        assert pool_data["job_count"] <= 4, (
            f"{pool_id}: job_count={pool_data['job_count']} is too high. "
            f"Expected 1-2 jobs per pool in the final scheduling round. "
            f"Review how round snapshots are combined in round_aggregator.py."
        )


def test_round_size_limit():
    """Each round must have at most 8 jobs (production concurrency limit)."""
    data = load_schedule()
    round_counts = {}
    for entry in data["assignments"]:
        r = entry["round"]
        round_counts[r] = round_counts.get(r, 0) + 1
    for round_num, count in round_counts.items():
        assert count <= 8, (
            f"Round {round_num} has {count} jobs (max should be 8). "
            f"Check which config section provides max_concurrent."
        )


# ============================================================
# TIER 4: Hardest (requires ALL bugs fixed for correct digest)
# ============================================================

def test_schedule_digest():
    """Schedule digest must match the expected deterministic value.
    Requires all bugs to be fixed: pool filtering, concurrency limit,
    aggregation mode, and sort ordering must all be correct."""
    data = load_pool_report()
    assert data["schedule_digest"] == "00bbd58e03e1bb92", (
        f"Expected digest '00bbd58e03e1bb92', got '{data['schedule_digest']}'. "
        f"The digest depends on pool job counts, CPU averages, scheduling totals "
        f"- all upstream bugs must be fixed."
    )


def test_priority_tiebreaker_ordering():
    """When jobs share the same priority and submission time, they must be
    ordered by queue_name alphabetically. At timestamp 1700000015, two
    priority-5 jobs exist: job-B02 (batch_analytics) and job-A02
    (system_maintenance). batch_analytics should be scheduled first.
    Check the sort key in schedule_jobs() for deterministic ordering."""
    data = load_schedule()
    # Find positions of job-B02 and job-A02
    b02_idx = None
    a02_idx = None
    for i, entry in enumerate(data["assignments"]):
        if entry["job_id"] == "job-B02":
            b02_idx = i
        elif entry["job_id"] == "job-A02":
            a02_idx = i
    assert b02_idx is not None, (
        "job-B02 not found in schedule. Check pool filtering."
    )
    assert a02_idx is not None, (
        "job-A02 not found in schedule. Check pool filtering."
    )
    assert b02_idx < a02_idx, (
        f"job-B02 (batch_analytics) should appear before job-A02 (system_maintenance) "
        f"at equal priority and timestamp. Got B02 at position {b02_idx}, A02 at {a02_idx}. "
        f"The sort tiebreaker should use queue_name for deterministic ordering "
        f"when priority and submission time are equal."
    )
