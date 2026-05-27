"""Main entry point for the priority-based task scheduling engine.

Orchestrates the full scheduling workflow: configuration loading,
job parsing, priority filtering, execution scheduling, and output
generation for the final execution plan and summary report.
"""

import json
import logging
import os
import sys
from configparser import ConfigParser
from pathlib import Path

from .parser import BatchParser
from .prioritizer import PriorityFilter
from .executor import ExecutionScheduler

CONFIG_PATH = Path("/app/runtime/config.ini")
OUTPUT_DIR = Path("/app/runtime/output")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


def load_configuration() -> ConfigParser:
    """Load and return the scheduler configuration."""
    config = ConfigParser()
    if not CONFIG_PATH.exists():
        logger.error(f"Configuration file not found: {CONFIG_PATH}")
        sys.exit(1)
    config.read(str(CONFIG_PATH))
    return config


def run_scheduling_engine():
    """Execute the complete scheduling workflow."""
    logger.info("Starting scheduling engine")

    config = load_configuration()
    logger.info("Configuration loaded successfully")

    parser = BatchParser(config)
    all_jobs = parser.load_all_batches()
    logger.info(f"Parsed {len(all_jobs)} total jobs from batch files")

    priority_filter = PriorityFilter(config)
    eligible_jobs = priority_filter.filter_eligible(all_jobs)
    weighted_jobs = priority_filter.assign_weights(eligible_jobs)
    priority_summary = priority_filter.get_priority_summary(eligible_jobs)
    logger.info(
        f"Priority filtering complete: {len(eligible_jobs)} eligible jobs"
    )

    scheduler = ExecutionScheduler(config)
    entries = scheduler.schedule_jobs(weighted_jobs)
    round_summary = scheduler.get_round_summary(entries)
    logger.info(f"Scheduling complete: {len(entries)} jobs scheduled")

    scheduled = [
        {
            "job_id": e.job_id,
            "queue_name": e.queue_name,
            "priority": e.priority,
            "scheduled_round": e.scheduled_round,
            "execution_time": e.execution_time,
            "status": e.status,
        }
        for e in entries
    ]

    # Note: job_id is only unique within a queue
    scheduled.sort(key=lambda j: (j["priority"], j["job_id"]))

    os.makedirs(str(OUTPUT_DIR), exist_ok=True)

    execution_plan_path = OUTPUT_DIR / "execution_plan.json"
    with open(str(execution_plan_path), "w", encoding="utf-8") as f:
        json.dump(scheduled, f, indent=2)
    logger.info(f"Execution plan written to {execution_plan_path}")

    summary = {
        "total_jobs_parsed": len(all_jobs),
        "total_jobs_eligible": len(eligible_jobs),
        "total_jobs_scheduled": len(entries),
        "priority_levels_used": sorted(priority_summary.keys()),
        "priority_distribution": priority_summary,
        "round_summary": round_summary,
        "time_budget": config.getfloat("scheduler.limits", "time_budget"),
        "execution_mode": config.get("scheduler", "execution_mode"),
    }

    summary_path = OUTPUT_DIR / "schedule_summary.json"
    with open(str(summary_path), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    logger.info(f"Schedule summary written to {summary_path}")

    logger.info("Scheduling engine completed successfully")


if __name__ == "__main__":
    run_scheduling_engine()
