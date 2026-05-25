"""
Job Scheduler Engine - Main Entry Point
Processes job manifests from multiple queues, applies priority scheduling,
and produces execution plans with resource allocation reports.

Usage: python3 -m runtime.run_scheduler

Reads: queue_batch.csv, queue_realtime.csv, queue_maintenance.csv, scheduler.ini
Produces:
  - output/schedule.json (job-to-round assignments)
  - output/pool_report.json (per-pool resource statistics)
"""

import os
import sys

RUNTIME_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(RUNTIME_DIR))

from runtime.job_loader import load_all_jobs
from runtime.priority_scheduler import load_config, schedule_jobs
from runtime.round_aggregator import compute_round_snapshots, aggregate_pool_summaries
from runtime.report_writer import write_schedule, write_pool_report


def main():
    """Main execution: load jobs, schedule, aggregate, write reports."""
    jobs = load_all_jobs()
    print(f"Loaded {len(jobs)} jobs from queue manifests")

    config = load_config()

    # Schedule jobs into rounds
    scheduled, rejected = schedule_jobs(jobs, config)
    print(f"Scheduled {len(scheduled)} jobs, rejected {len(rejected)}")

    # Compute pool resource summaries
    snapshots = compute_round_snapshots(scheduled, config)
    pool_summaries = aggregate_pool_summaries(snapshots)
    print(f"Aggregated {len(pool_summaries)} pool summaries")

    # Write output files
    sched_path = write_schedule(scheduled, rejected)
    report_path = write_pool_report(pool_summaries, len(scheduled), len(rejected))

    print(f"Output written:")
    print(f"  - {sched_path}")
    print(f"  - {report_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
