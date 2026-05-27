"""Priority filtering and ordering for the scheduling engine.

Applies priority-based filtering to determine which jobs are eligible
for scheduling, and assigns execution weight factors based on their
priority classification level.
"""

import logging
from configparser import ConfigParser
from typing import Dict, List, Tuple

from .models import Job

logger = logging.getLogger(__name__)


PRIORITY_WEIGHTS: Dict[str, int] = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
}

EXECUTION_FACTORS: Dict[str, float] = {
    "critical": 1.0,
    "high": 1.2,
    "medium": 1.5,
    "low": 1.8,
}


class PriorityFilter:
    """Filters and classifies jobs based on configured priority levels."""

    def __init__(self, config: ConfigParser):
        self._config = config
        self._levels = set(
            config.get("scheduler", "priority_levels").split(",")
        )
        self._execution_mode = config.get("scheduler", "execution_mode")
        logger.info(
            f"Initialized priority filter with levels: {self._levels}"
        )

    @property
    def configured_levels(self) -> set:
        """Return the set of configured priority levels."""
        return self._levels

    def filter_eligible(self, jobs: List[Job]) -> List[Job]:
        """Filter jobs to only those with recognized priority levels."""
        eligible = []
        rejected_count = 0
        for job in jobs:
            if job.priority in self._levels:
                eligible.append(job)
            else:
                rejected_count += 1
                logger.debug(
                    f"Job {job.job_id} rejected: priority "
                    f"'{job.priority}' not in configured levels"
                )

        if rejected_count > 0:
            logger.info(
                f"Filtered out {rejected_count} jobs with "
                f"unrecognized priority levels"
            )
        return eligible

    def assign_weights(
        self, jobs: List[Job]
    ) -> List[Tuple[Job, int, float]]:
        """Assign priority weight and execution factor to each job.

        Returns a list of tuples: (job, weight, factor).
        Weight determines scheduling order (lower = higher priority).
        Factor determines execution time multiplier.
        """
        weighted = []
        for job in jobs:
            weight = PRIORITY_WEIGHTS.get(job.priority, 99)
            factor = EXECUTION_FACTORS.get(job.priority, 2.0)
            weighted.append((job, weight, factor))

        weighted.sort(key=lambda item: (item[1], item[0].queue_name))
        return weighted

    def get_priority_summary(self, jobs: List[Job]) -> Dict[str, int]:
        """Generate a count summary of jobs per priority level."""
        summary: Dict[str, int] = {}
        for job in jobs:
            if job.priority not in summary:
                summary[job.priority] = 0
            summary[job.priority] += 1
        return summary

    def compute_total_estimated_load(self, jobs: List[Job]) -> float:
        """Compute the aggregate weighted load for capacity planning."""
        total_load = 0.0
        for job in jobs:
            factor = EXECUTION_FACTORS.get(job.priority, 2.0)
            total_load += job.estimated_duration * factor
        return round(total_load, 2)
