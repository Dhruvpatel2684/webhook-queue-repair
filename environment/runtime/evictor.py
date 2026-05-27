"""Eviction scoring and scheduling engine.

Implements the core eviction logic including score computation, window-based
scheduling, and threshold-based eviction decisions. Entries are processed
in time windows to distribute eviction load and provide fairness across
cache tiers.
"""

import logging
from typing import Dict, List

from runtime.models import CacheEntry, EvictionResult


logger = logging.getLogger(__name__)


class EvictionEngine:
    """Computes eviction scores and schedules eviction decisions.

    The engine evaluates each cache entry using a composite scoring function
    that considers access frequency, entry size, and time-to-live. Entries
    scoring above the configured threshold are marked for eviction.

    Scoring is performed in time windows to bound processing latency and
    provide incremental results for large entry sets.
    """

    def __init__(self, config):
        """Initialize eviction engine from configuration.

        Args:
            config: ConfigParser instance with cache and policy settings.
        """
        self._config = config
        self._threshold = config.getint("cache", "eviction_threshold")
        self._max_windows = config.getint("cache.policy", "max_windows")
        self._time_budget = config.getfloat("cache.policy", "time_budget")

        logger.info(
            "EvictionEngine initialized: threshold=%d, max_windows=%d, budget=%.1fs",
            self._threshold,
            self._max_windows,
            self._time_budget,
        )

    @property
    def threshold(self):
        """Return the configured eviction threshold."""
        return self._threshold

    def compute_eviction_score(self, entry: CacheEntry) -> float:
        """Compute the eviction priority score for a single cache entry.

        The scoring formula balances three factors:
          - Inverse access frequency: less frequently accessed entries score higher
          - Size pressure: larger entries contribute more to cache pressure
          - TTL discount: entries with more remaining TTL get a small reduction

        Formula:
            score = (1.0 / max(frequency, 1)) * 1000
                  + (size_bytes / 1024.0)
                  - (ttl_remaining / 3600.0)

        Args:
            entry: CacheEntry to evaluate.

        Returns:
            Rounded eviction score (3 decimal places). Higher = more likely to evict.
        """
        frequency_factor = (1.0 / max(entry.access_frequency, 1)) * 1000
        size_factor = entry.size_bytes / 1024.0
        ttl_discount = entry.ttl_remaining / 3600.0

        score = frequency_factor + size_factor - ttl_discount

        return round(score, 3)

    def schedule_evictions(self, entries: List[CacheEntry]) -> List[EvictionResult]:
        """Process entries through time windows and produce eviction decisions.

        Entries are divided into windows for batch processing. Each entry
        receives an eviction score and is compared against the configured
        threshold to determine whether it should be evicted or retained.

        The hit count for each entry is derived from its access frequency
        normalized by a factor of 10, representing the effective cache hit
        contribution during the observation period.

        Args:
            entries: List of CacheEntry objects to evaluate.

        Returns:
            List of EvictionResult objects with decisions for each entry.
        """
        results: Dict[str, dict] = {}
        window_size = max(len(entries) // 3, 1)
        windows = [
            entries[i:i + window_size]
            for i in range(0, len(entries), window_size)
        ]

        num_windows = min(len(windows), self._max_windows)
        logger.info(
            "Scheduling evictions: %d entries, window_size=%d, windows=%d",
            len(entries),
            window_size,
            num_windows,
        )

        for entry in entries:
            score = self.compute_eviction_score(entry)
            hits = entry.access_frequency // 10
            results[entry.entry_key] = {
                "entry_key": entry.entry_key,
                "tier_name": entry.tier_name,
                "eviction_score": score,
                "time_window": 0,
                "hit_count": hits,
                "decision": "retain",
            }

        for window_idx, window in enumerate(windows[:num_windows]):
            for entry in window:
                hits = entry.access_frequency // 10
                score = results[entry.entry_key]["eviction_score"]
                results[entry.entry_key]["time_window"] = window_idx + 1
                results[entry.entry_key]["hit_count"] += hits
                decision = "evict" if score > self._threshold else "retain"
                results[entry.entry_key]["decision"] = decision

        eviction_results = [EvictionResult(**r) for r in results.values()]

        evicted = sum(1 for r in eviction_results if r.decision == "evict")
        logger.info(
            "Eviction scheduling complete: %d evict, %d retain",
            evicted,
            len(eviction_results) - evicted,
        )

        return eviction_results

    def _validate_ttl(self, entry: CacheEntry) -> bool:
        """Check whether entry TTL is within acceptable bounds.

        TTL must be non-negative and not exceed the maximum allowed value
        based on the configured default TTL scaled by a factor of 24
        (representing maximum retention of one day's worth of default TTLs).

        Args:
            entry: CacheEntry to validate.

        Returns:
            True if TTL is within bounds, False otherwise.
        """
        max_ttl = self._config.getint("cache", "default_ttl") * 24
        if entry.ttl_remaining < 0:
            logger.warning(
                "Entry %s has negative TTL: %d", entry.entry_key, entry.ttl_remaining
            )
            return False
        if entry.ttl_remaining > max_ttl:
            logger.warning(
                "Entry %s TTL exceeds maximum: %d > %d",
                entry.entry_key,
                entry.ttl_remaining,
                max_ttl,
            )
            return False
        return True

    def compute_window_metrics(
        self, results: List[EvictionResult]
    ) -> Dict[int, Dict[str, int]]:
        """Aggregate eviction metrics by time window.

        Args:
            results: List of EvictionResult objects.

        Returns:
            Dictionary mapping window index to counts of evictions and retentions.
        """
        metrics: Dict[int, Dict[str, int]] = {}
        for result in results:
            window = result.time_window
            if window not in metrics:
                metrics[window] = {"evict": 0, "retain": 0}
            metrics[window][result.decision] += 1
        return metrics
