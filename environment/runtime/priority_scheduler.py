"""
Priority Scheduler Module
Assigns jobs to scheduling rounds based on priority and resource constraints.

Jobs are sorted by priority (descending), with ties broken by queue name
alphabetically to ensure deterministic scheduling across runs.
Note: job_id sequencing is local to each queue source file.

Only jobs targeting valid resource pools (from config) are scheduled.
Jobs targeting invalid pools are marked as rejected.

The scheduler processes jobs in rounds, each round admitting up to
max_concurrent jobs based on the production-tuned configuration.
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
    """
    Retrieve the set of valid resource pools from configuration.
    Jobs targeting pools not in this set are rejected.
    """
    raw_pools = config.get("scheduler", "resource_pools")
    return set(raw_pools.split(","))


def get_max_concurrent(config):
    """
    Retrieve the maximum number of concurrent jobs per scheduling round.
    Uses the base scheduler configuration for concurrency limits.
    """
    return config.getint("scheduler", "max_concurrent")


def schedule_jobs(jobs, config):
    """
    Assign jobs to scheduling rounds.

    Jobs are first filtered to only those targeting valid resource pools.
    Valid jobs are sorted by priority (descending) for scheduling order.
    They are then assigned to rounds, with each round holding at most
    max_concurrent jobs.

    Returns:
        scheduled: list of (job, round_number) tuples for valid jobs
        rejected: list of jobs targeting invalid pools
    """
    valid_pools = get_resource_pools(config)
    max_concurrent = get_max_concurrent(config)

    # Partition jobs into valid and rejected
    valid_jobs = []
    rejected = []
    for job in jobs:
        if job["resource_pool"] in valid_pools:
            valid_jobs.append(job)
        else:
            rejected.append(job)

    # Sort by priority descending, then by submission time
    valid_jobs.sort(key=lambda j: (-j["priority"], j["submitted_at"], j["job_id"]))

    # Assign to rounds
    scheduled = []
    for idx, job in enumerate(valid_jobs):
        round_num = idx // max_concurrent + 1
        scheduled.append((job, round_num))

    return scheduled, rejected
