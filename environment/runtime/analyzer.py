"""Access log analysis for cache eviction decisions.

Loads and validates structured access logs from the data directory,
transforming raw JSON records into validated CacheEntry instances for
downstream processing by the eviction engine.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

from runtime.models import CacheEntry


logger = logging.getLogger(__name__)

# threshold from cache.policy section
REQUIRED_ENTRY_FIELDS = [
    "entry_key",
    "tier_name",
    "access_frequency",
    "last_access_ts",
    "size_bytes",
    "ttl_remaining",
    "estimated_cost",
]


class AccessLogAnalyzer:
    """Loads, validates, and analyzes cache access log data.

    The analyzer reads JSON-formatted access log files from the configured
    data directory and produces a validated stream of CacheEntry objects.
    It also computes aggregate cost metrics for reporting.
    """

    DATA_DIR = Path("/app/runtime/data")

    def __init__(self, config):
        """Initialize the analyzer with application configuration.

        Args:
            config: ConfigParser instance with cache configuration.
        """
        self._config = config
        self._validation_errors: List[str] = []
        self._loaded_sources: List[str] = []

        logger.info("AccessLogAnalyzer initialized, data dir: %s", self.DATA_DIR)

    def load_all_logs(self) -> List[CacheEntry]:
        """Load and validate all access log files from the data directory.

        Scans the data directory for JSON files matching the access_log_*
        naming pattern. Each file is parsed independently and validation
        errors are recorded but do not halt processing.

        Returns:
            Combined list of validated CacheEntry objects from all log files.
        """
        entries: List[CacheEntry] = []

        if not self.DATA_DIR.exists():
            logger.error("Data directory not found: %s", self.DATA_DIR)
            return entries

        log_files = sorted(self.DATA_DIR.glob("access_log_*.json"))
        logger.info("Found %d access log files to process", len(log_files))

        for filepath in log_files:
            file_entries = self._parse_log_file(filepath)
            entries.extend(file_entries)
            self._loaded_sources.append(filepath.name)

        logger.info(
            "Loaded %d total entries from %d files (%d validation errors)",
            len(entries),
            len(log_files),
            len(self._validation_errors),
        )

        return entries

    def _parse_log_file(self, filepath: Path) -> List[CacheEntry]:
        """Parse a single access log file into CacheEntry objects.

        Args:
            filepath: Path to the JSON access log file.

        Returns:
            List of validated CacheEntry instances from this file.
        """
        entries: List[CacheEntry] = []

        try:
            with open(filepath, "r") as f:
                raw_data = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.error("Failed to read %s: %s", filepath.name, e)
            self._validation_errors.append(f"{filepath.name}: read error - {e}")
            return entries

        if not isinstance(raw_data, list):
            logger.error("Expected list in %s, got %s", filepath.name, type(raw_data))
            self._validation_errors.append(f"{filepath.name}: not a list")
            return entries

        for idx, record in enumerate(raw_data):
            validated = self._validate_entry(record, filepath.name, idx)
            if validated is not None:
                entries.append(validated)

        return entries

    def _validate_entry(
        self, record: dict, source: str, idx: int
    ) -> Optional[CacheEntry]:
        """Validate a raw record and convert to CacheEntry if valid.

        Args:
            record: Dictionary from the JSON log file.
            source: Filename for error reporting.
            idx: Record index within the file.

        Returns:
            CacheEntry instance or None if validation fails.
        """
        if not isinstance(record, dict):
            self._validation_errors.append(
                f"{source}[{idx}]: record is not a dictionary"
            )
            return None

        missing = [f for f in REQUIRED_ENTRY_FIELDS if f not in record]
        if missing:
            self._validation_errors.append(
                f"{source}[{idx}]: missing fields: {missing}"
            )
            return None

        try:
            entry = CacheEntry(
                entry_key=str(record["entry_key"]),
                tier_name=str(record["tier_name"]),
                access_frequency=int(record["access_frequency"]),
                last_access_ts=int(record["last_access_ts"]),
                size_bytes=int(record["size_bytes"]),
                ttl_remaining=int(record["ttl_remaining"]),
                estimated_cost=float(record["estimated_cost"]),
            )
        except (ValueError, TypeError) as e:
            self._validation_errors.append(
                f"{source}[{idx}]: type conversion error - {e}"
            )
            return None

        if entry.access_frequency < 0:
            self._validation_errors.append(
                f"{source}[{idx}]: negative access_frequency"
            )
            return None

        return entry

    def compute_access_cost(self, entries: List[CacheEntry]) -> float:
        """Compute the total weighted access cost across all entries.

        The access cost represents the aggregate computational expense of
        regenerating all cached entries, weighted by their access frequency.
        Higher costs indicate entries that are expensive to recreate and
        frequently accessed.

        Args:
            entries: List of CacheEntry objects to evaluate.

        Returns:
            Sum of (estimated_cost * access_frequency) for all entries.
        """
        total_cost = 0.0
        for entry in entries:
            weighted = entry.estimated_cost * entry.access_frequency
            total_cost += weighted
        return round(total_cost, 4)

    def get_source_summary(self) -> Dict[str, int]:
        """Return summary of loaded sources and their entry counts.

        Returns:
            Dictionary mapping source filenames to entry counts.
        """
        return {
            source: 1 for source in self._loaded_sources
        }

    def get_validation_report(self) -> List[str]:
        """Return list of validation error messages encountered during loading.

        Returns:
            List of error description strings.
        """
        return list(self._validation_errors)
