"""
Round Aggregator Module
Computes per-pool resource statistics from scheduling rounds.

Processing iterates through scheduling rounds in order. For each pool,
the aggregator computes resource allocation within each round.

Round processing produces snapshots at each round boundary.
The final pool summary uses values from the last round snapshot only,
representing the current allocation state for each pool.
Distinct queues are tracked across all rounds for completeness.
"""

import configparser
import os

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scheduler.ini")


def load_config():
    """Load scheduler configuration."""
    config = configparser.ConfigParser()
    config.read(CONFIG_PATH)
    return config


def get_resource_pools(config):
    """Retrieve valid resource pools from configuration."""
    raw_pools = config.get("scheduler", "resource_pools")
    return set(raw_pools.split(","))


def compute_round_snapshots(scheduled, config):
    """
    Group scheduled jobs by round and compute per-pool snapshots.
    Returns a list of round snapshots, each containing pool stats.
    """
    valid_pools = get_resource_pools(config)

    # Group by round
    rounds = {}
    for job, round_num in scheduled:
        if round_num not in rounds:
            rounds[round_num] = []
        rounds[round_num].append(job)

    snapshots = []
    for round_num in sorted(rounds.keys()):
        round_jobs = rounds[round_num]

        pool_stats = {}
        for job in round_jobs:
            pool = job["resource_pool"]
            if pool not in pool_stats:
                pool_stats[pool] = {
                    "job_count": 0,
                    "total_cpu": 0,
                    "total_memory_mb": 0,
                    "total_runtime_sec": 0,
                    "queues_seen": set(),
                }
            pool_stats[pool]["job_count"] += 1
            pool_stats[pool]["total_cpu"] += job["cpu_units"]
            pool_stats[pool]["total_memory_mb"] += job["memory_mb"]
            pool_stats[pool]["total_runtime_sec"] += job["estimated_runtime_sec"]
            pool_stats[pool]["queues_seen"].add(job["queue_name"])

        snapshots.append({
            "round_num": round_num,
            "pools": pool_stats,
        })

    return snapshots


def aggregate_pool_summaries(snapshots):
    """
    Produce final per-pool summaries from round snapshots.

    The final summary for each pool uses values from its last round
    snapshot (the most recent scheduling state). This represents the
    current allocation pressure on each resource pool.
    Queue diversity is accumulated across all rounds.
    """
    pool_summaries = {}

    for snapshot in snapshots:
        for pool_id, stats in snapshot["pools"].items():
            if pool_id not in pool_summaries:
                pool_summaries[pool_id] = {
                    "pool_id": pool_id,
                    "job_count": 0,
                    "total_cpu": 0,
                    "total_memory_mb": 0,
                    "total_runtime_sec": 0,
                    "queues_seen": set(),
                }
            # Accumulate snapshot values across rounds for running totals
            pool_summaries[pool_id]["job_count"] += stats["job_count"]
            pool_summaries[pool_id]["total_cpu"] += stats["total_cpu"]
            pool_summaries[pool_id]["total_memory_mb"] += stats["total_memory_mb"]
            pool_summaries[pool_id]["total_runtime_sec"] += stats["total_runtime_sec"]
            pool_summaries[pool_id]["queues_seen"].update(stats["queues_seen"])

    # Finalize: compute averages
    result = {}
    for pool_id, summary in pool_summaries.items():
        count = summary["job_count"]
        result[pool_id] = {
            "pool_id": pool_id,
            "job_count": count,
            "avg_cpu": round(summary["total_cpu"] / count, 2) if count > 0 else 0.0,
            "avg_memory_mb": round(summary["total_memory_mb"] / count, 1) if count > 0 else 0.0,
            "avg_runtime_sec": round(summary["total_runtime_sec"] / count, 1) if count > 0 else 0.0,
            "queue_diversity": len(summary["queues_seen"]),
        }

    return result
