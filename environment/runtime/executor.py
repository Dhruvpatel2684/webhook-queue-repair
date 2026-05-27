"""Execution scheduler for distributing jobs across processing rounds.

Manages the allocation of jobs into concurrent execution rounds,
respecting capacity limits and computing expected execution times
for each job based on its priority factor and estimated duration.
"""

import logging
from configparser import ConfigParser
from typing import Dict, List, Tuple

from .models import Job, ScheduleEntry

logger = logging.getLogger(__name__)


class ExecutionScheduler:
    """Schedules jobs into execution rounds with capacity constraints."""

    def __init__(self, config: ConfigParser):
        self._config = config
        self._max_concurrent = config.getint("scheduler", "max_concurrent")
        self._max_rounds = config.getint("scheduler.limits", "max_rounds")
        self._time_budget = config.getfloat("scheduler.limits", "time_budget")
        self._default_timeout = config.getint("scheduler", "default_timeout")
        self._retry_limit = config.getint("scheduler", "retry_limit")
        logger.info(
            f"Execution scheduler initialized: max_concurrent="
            f"{self._max_concurrent}, max_rounds={self._max_rounds}"
        )

    def schedule_jobs(
        self, weighted_jobs: List[Tuple[Job, int, float]]
    ) -> List[ScheduleEntry]:
        """Schedule weighted jobs into execution rounds.

        Takes jobs with assigned weights and factors, distributes them
        into rounds respecting concurrency limits, and computes
        expected execution times.
        """
        if not weighted_jobs:
            logger.warning("No jobs to schedule")
            return []

        valid_jobs = self._prefilter_jobs(weighted_jobs)
        if not valid_jobs:
            logger.warning("No valid jobs after prefiltering")
            return []

        results: Dict[str, Dict] = {}
        for job, weight, factor in valid_jobs:
            results[job.job_id] = {
                "job": job,
                "weight": weight,
                "factor": factor,
                "execution_time": 0.0,
                "scheduled_round": 0,
                "status": "pending",
            }

        self._estimate_execution_times(valid_jobs, results)
        self._assign_rounds(valid_jobs, results)

        entries = []
        for job, weight, factor in valid_jobs:
            rec = results[job.job_id]
            entry = ScheduleEntry(
                job_id=job.job_id,
                queue_name=job.queue_name,
                priority=job.priority,
                scheduled_round=rec["scheduled_round"],
                execution_time=round(rec["execution_time"], 3),
                status=rec["status"],
            )
            entries.append(entry)

        logger.info(f"Scheduled {len(entries)} jobs successfully")
        return entries

    def _prefilter_jobs(
        self, weighted_jobs: List[Tuple[Job, int, float]]
    ) -> List[Tuple[Job, int, float]]:
        """Remove jobs that exceed retry limits or have invalid timeouts."""
        valid = []
        for job, weight, factor in weighted_jobs:
            if job.retry_count > self._retry_limit:
                logger.debug(
                    f"Skipping {job.job_id}: retry_count "
                    f"{job.retry_count} exceeds limit {self._retry_limit}"
                )
                continue
            if job.timeout <= 0 or job.timeout > self._default_timeout * 10:
                logger.debug(
                    f"Skipping {job.job_id}: invalid timeout {job.timeout}"
                )
                continue
            if job.estimated_duration <= 0:
                logger.debug(
                    f"Skipping {job.job_id}: invalid duration "
                    f"{job.estimated_duration}"
                )
                continue
            valid.append((job, weight, factor))
        return valid

    def _estimate_execution_times(
        self,
        valid_jobs: List[Tuple[Job, int, float]],
        results: Dict[str, Dict],
    ) -> None:
        """Pre-calculate execution times based on duration and factor."""
        for job, weight, factor in valid_jobs:
            duration = job.estimated_duration * factor
            if duration > self._time_budget:
                duration = self._time_budget
            results[job.job_id]["execution_time"] += duration

    def _assign_rounds(
        self,
        valid_jobs: List[Tuple[Job, int, float]],
        results: Dict[str, Dict],
    ) -> None:
        """Distribute jobs across rounds respecting concurrency limit."""
        current_round = 1
        slots_in_round = 0
        cumulative_time = 0.0

        for job, weight, factor in valid_jobs:
            if slots_in_round >= self._max_concurrent:
                current_round += 1
                slots_in_round = 0

            if current_round > self._max_rounds:
                results[job.job_id]["status"] = "deferred"
                logger.debug(
                    f"Job {job.job_id} deferred: exceeded max rounds"
                )
                continue

            duration = job.estimated_duration * factor
            cumulative_time += duration

            results[job.job_id]["execution_time"] += duration
            results[job.job_id]["scheduled_round"] = current_round
            results[job.job_id]["status"] = "scheduled"
            slots_in_round += 1

    def get_round_summary(self, entries: List[ScheduleEntry]) -> Dict:
        """Generate a summary of job distribution across rounds."""
        round_counts: Dict[int, int] = {}
        round_times: Dict[int, float] = {}
        for entry in entries:
            if entry.scheduled_round not in round_counts:
                round_counts[entry.scheduled_round] = 0
                round_times[entry.scheduled_round] = 0.0
            round_counts[entry.scheduled_round] += 1
            round_times[entry.scheduled_round] += entry.execution_time

        return {
            "total_rounds": len(round_counts),
            "jobs_per_round": round_counts,
            "time_per_round": {
                k: round(v, 3) for k, v in round_times.items()
            },
        }
