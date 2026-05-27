"""Data models for the task scheduling engine.

Defines the core data structures used throughout the scheduling system
for representing jobs and their scheduled execution entries.
"""

from dataclasses import dataclass, field
from typing import Dict


@dataclass
class Job:
    """Represents a single schedulable job unit."""

    job_id: str
    queue_name: str
    priority: str
    payload: Dict
    timeout: int
    retry_count: int
    estimated_duration: float


@dataclass
class ScheduleEntry:
    """Represents a scheduled execution slot for a job."""

    job_id: str
    queue_name: str
    priority: str
    scheduled_round: int
    execution_time: float
    status: str


@dataclass
class ScheduleResult:
    """Aggregate result of the scheduling process."""

    entries: list = field(default_factory=list)
    total_rounds: int = 0
    total_jobs: int = 0
    priority_levels_used: list = field(default_factory=list)
    time_budget_remaining: float = 0.0
