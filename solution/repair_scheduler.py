#!/usr/bin/env python3
"""
Repair script for cgroup-scheduler-repair task.
Patches bugs in priority_scheduler.py and round_aggregator.py, then re-runs.

Fixes applied:
1. priority_scheduler.py get_resource_pools(): strip whitespace from pool names
   after splitting on comma (fixes pool_network being stored as " pool_network")
2. priority_scheduler.py get_max_concurrent(): read from [scheduler.production]
   section instead of [scheduler] for the production-tuned concurrency limit
3. round_aggregator.py aggregate_pool_summaries(): use last-write-wins instead of
   accumulating job_count/total_cpu/total_memory/total_runtime across round snapshots
4. priority_scheduler.py schedule_jobs(): sort by (queue_name) instead of (job_id)
   as tiebreaker for deterministic ordering at equal priority and timestamp
"""

import os
import sys


def patch_priority_scheduler():
    """Fix bugs in priority_scheduler.py."""
    path = "/app/runtime/priority_scheduler.py"
    with open(path, "r") as f:
        content = f.read()

    # Fix Bug A: strip whitespace from pool names in comma split
    content = content.replace(
        'return set(raw_pools.split(","))',
        'return set(item.strip() for item in raw_pools.split(","))'
    )

    # Fix Bug B: read max_concurrent from scheduler.production section
    content = content.replace(
        'return config.getint("scheduler", "max_concurrent")',
        'return config.getint("scheduler.production", "max_concurrent")'
    )

    # Fix Bug D: sort tiebreaker should use queue_name, not job_id
    content = content.replace(
        'valid_jobs.sort(key=lambda j: (-j["priority"], j["submitted_at"], j["job_id"]))',
        'valid_jobs.sort(key=lambda j: (-j["priority"], j["submitted_at"], j["queue_name"]))'
    )

    with open(path, "w") as f:
        f.write(content)


def patch_round_aggregator_pools():
    """Fix Bug A in round_aggregator.py: strip whitespace from pool names."""
    path = "/app/runtime/round_aggregator.py"
    with open(path, "r") as f:
        content = f.read()

    content = content.replace(
        'return set(raw_pools.split(","))',
        'return set(item.strip() for item in raw_pools.split(","))'
    )

    with open(path, "w") as f:
        f.write(content)


def patch_round_aggregator():
    """Fix Bug C in round_aggregator.py: use last-write-wins instead of accumulation."""
    path = "/app/runtime/round_aggregator.py"
    with open(path, "r") as f:
        content = f.read()

    # Replace the accumulation logic with last-write-wins
    old_code = '''            # Accumulate snapshot values across rounds for running totals
            pool_summaries[pool_id]["job_count"] += stats["job_count"]
            pool_summaries[pool_id]["total_cpu"] += stats["total_cpu"]
            pool_summaries[pool_id]["total_memory_mb"] += stats["total_memory_mb"]
            pool_summaries[pool_id]["total_runtime_sec"] += stats["total_runtime_sec"]'''

    new_code = '''            # Last-write-wins: use most recent round snapshot values
            pool_summaries[pool_id]["job_count"] = stats["job_count"]
            pool_summaries[pool_id]["total_cpu"] = stats["total_cpu"]
            pool_summaries[pool_id]["total_memory_mb"] = stats["total_memory_mb"]
            pool_summaries[pool_id]["total_runtime_sec"] = stats["total_runtime_sec"]'''

    content = content.replace(old_code, new_code)

    with open(path, "w") as f:
        f.write(content)


def main():
    patch_priority_scheduler()
    patch_round_aggregator_pools()
    patch_round_aggregator()

    # Re-run with fixed code
    sys.path.insert(0, "/app")

    # Clear cached modules
    for key in list(sys.modules.keys()):
        if key.startswith("runtime"):
            del sys.modules[key]

    from runtime.run_scheduler import main as run_main
    run_main()


if __name__ == "__main__":
    main()
