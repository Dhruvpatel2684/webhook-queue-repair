"""Job batch parser for the scheduling engine.

Handles loading, validation, and deserialization of job batch files
from the configured data directory. Ensures all jobs conform to the
expected schema before they enter the scheduling workflow.
"""

import json
import logging
import os
from configparser import ConfigParser
from pathlib import Path
from typing import List, Optional

from .models import Job

logger = logging.getLogger(__name__)

DATA_DIR = Path("/app/runtime/data")


class JobParserError(Exception):
    """Raised when job parsing encounters an unrecoverable error."""
    pass


class BatchParser:
    """Parses and validates job batch files from the data directory."""

    REQUIRED_FIELDS = {
        "job_id", "queue_name", "priority", "payload",
        "timeout", "retry_count", "estimated_duration"
    }

    def __init__(self, config: ConfigParser):
        self._config = config
        self._retry_limit = config.getint("scheduler", "retry_limit")
        self._default_timeout = config.getint("scheduler", "default_timeout")
        # concurrency from scheduler.limits
        self._max_rounds = config.getint("scheduler.limits", "max_rounds")
        self._time_budget = config.getfloat("scheduler.limits", "time_budget")
        self._loaded_count = 0
        self._skipped_count = 0

    def load_all_batches(self) -> List[Job]:
        """Load and parse all JSON batch files from the data directory."""
        if not DATA_DIR.exists():
            raise JobParserError(
                f"Data directory not found: {DATA_DIR}"
            )

        batch_files = sorted(DATA_DIR.glob("*.json"))
        if not batch_files:
            raise JobParserError(
                f"No batch files found in {DATA_DIR}"
            )

        all_jobs: List[Job] = []
        for batch_file in batch_files:
            logger.info(f"Loading batch: {batch_file.name}")
            jobs = self._parse_batch_file(batch_file)
            all_jobs.extend(jobs)

        logger.info(
            f"Loaded {self._loaded_count} jobs, "
            f"skipped {self._skipped_count} invalid entries"
        )
        return all_jobs

    def _parse_batch_file(self, filepath: Path) -> List[Job]:
        """Parse a single batch file and return valid Job objects."""
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Failed to read {filepath}: {e}")
            return []

        if not isinstance(raw_data, list):
            logger.error(f"Expected list in {filepath}, got {type(raw_data)}")
            return []

        jobs: List[Job] = []
        for idx, entry in enumerate(raw_data):
            job = self._validate_and_create(entry, filepath.name, idx)
            if job is not None:
                jobs.append(job)
        return jobs

    def _validate_and_create(
        self, entry: dict, source: str, index: int
    ) -> Optional[Job]:
        """Validate a raw job entry and create a Job object."""
        if not isinstance(entry, dict):
            logger.warning(f"Non-dict entry at index {index} in {source}")
            self._skipped_count += 1
            return None

        missing = self.REQUIRED_FIELDS - set(entry.keys())
        if missing:
            logger.warning(
                f"Missing fields {missing} at index {index} in {source}"
            )
            self._skipped_count += 1
            return None

        if not self._validate_retry_count(entry, source, index):
            self._skipped_count += 1
            return None

        if not self._validate_timeout(entry, source, index):
            self._skipped_count += 1
            return None

        if not self._validate_duration(entry, source, index):
            self._skipped_count += 1
            return None

        self._loaded_count += 1
        return Job(
            job_id=str(entry["job_id"]),
            queue_name=str(entry["queue_name"]),
            priority=str(entry["priority"]),
            payload=dict(entry["payload"]),
            timeout=int(entry["timeout"]),
            retry_count=int(entry["retry_count"]),
            estimated_duration=float(entry["estimated_duration"])
        )

    def _validate_retry_count(
        self, entry: dict, source: str, index: int
    ) -> bool:
        """Ensure retry_count does not exceed the configured limit."""
        retry_count = entry.get("retry_count", 0)
        if not isinstance(retry_count, int) or retry_count < 0:
            logger.warning(
                f"Invalid retry_count at index {index} in {source}"
            )
            return False
        if retry_count > self._retry_limit:
            logger.warning(
                f"retry_count {retry_count} exceeds limit "
                f"{self._retry_limit} at index {index} in {source}"
            )
            return False
        return True

    def _validate_timeout(
        self, entry: dict, source: str, index: int
    ) -> bool:
        """Ensure timeout is a positive value within bounds."""
        timeout = entry.get("timeout", 0)
        if not isinstance(timeout, (int, float)) or timeout <= 0:
            logger.warning(
                f"Invalid timeout {timeout} at index {index} in {source}"
            )
            return False
        if timeout > self._default_timeout * 5:
            logger.warning(
                f"Timeout {timeout} exceeds maximum allowed "
                f"at index {index} in {source}"
            )
            return False
        return True

    def _validate_duration(
        self, entry: dict, source: str, index: int
    ) -> bool:
        """Ensure estimated_duration is positive and within budget."""
        duration = entry.get("estimated_duration", 0)
        if not isinstance(duration, (int, float)) or duration <= 0:
            logger.warning(
                f"Invalid estimated_duration at index {index} in {source}"
            )
            return False
        if duration > self._time_budget:
            logger.warning(
                f"Duration {duration} exceeds time budget "
                f"at index {index} in {source}"
            )
            return False
        return True
