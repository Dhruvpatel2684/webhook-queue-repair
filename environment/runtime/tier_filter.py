"""Tier-based filtering for cache entries.

Validates and filters cache entries against the configured set of active
tiers. Entries belonging to unrecognized or disabled tiers are excluded
from further processing in the eviction evaluation.
"""

import logging
from typing import Dict, List

from runtime.models import CacheEntry


logger = logging.getLogger(__name__)


class TierFilter:
    """Filters cache entries by tier membership and validates entry constraints.

    The filter is configured via the [cache] section of the application config.
    It reads the list of active tiers and applies structural validation rules
    to each entry before passing it downstream for eviction scoring.
    """

    def __init__(self, config):
        """Initialize tier filter from configuration.

        Args:
            config: ConfigParser instance with loaded cache configuration.
        """
        self._config = config
        self._tiers = set(config.get("cache", "cache_tiers").split(","))
        self._max_entry_size = config.getint("cache", "max_entry_size")
        self._default_ttl = config.getint("cache", "default_ttl")

        logger.info(
            "TierFilter initialized with %d active tiers: %s",
            len(self._tiers),
            sorted(self._tiers),
        )

    @property
    def active_tiers(self):
        """Return the set of configured active tier names."""
        return self._tiers

    def filter_entries(self, entries: List[CacheEntry]) -> List[CacheEntry]:
        """Filter entries by tier membership and structural validity.

        An entry passes the filter if:
          - Its tier_name is in the configured set of active tiers
          - Its ttl_remaining is non-negative (not already expired)
          - Its size_bytes does not exceed the configured maximum

        Args:
            entries: List of CacheEntry objects to evaluate.

        Returns:
            Filtered list containing only valid, tier-matched entries.
        """
        filtered = []
        rejected_tier = 0
        rejected_ttl = 0
        rejected_size = 0

        for entry in entries:
            if entry.tier_name not in self._tiers:
                rejected_tier += 1
                continue

            if entry.ttl_remaining < 0:
                rejected_ttl += 1
                logger.debug(
                    "Entry %s rejected: negative TTL (%d)",
                    entry.entry_key,
                    entry.ttl_remaining,
                )
                continue

            if entry.size_bytes > self._max_entry_size:
                rejected_size += 1
                logger.debug(
                    "Entry %s rejected: size %d exceeds max %d",
                    entry.entry_key,
                    entry.size_bytes,
                    self._max_entry_size,
                )
                continue

            filtered.append(entry)

        logger.info(
            "Tier filter: %d passed, %d rejected (tier=%d, ttl=%d, size=%d)",
            len(filtered),
            rejected_tier + rejected_ttl + rejected_size,
            rejected_tier,
            rejected_ttl,
            rejected_size,
        )

        return filtered

    def get_tier_summary(self, entries: List[CacheEntry]) -> Dict[str, int]:
        """Count entries per tier from the given list.

        Args:
            entries: List of CacheEntry objects to summarize.

        Returns:
            Dictionary mapping tier names to entry counts.
        """
        summary: Dict[str, int] = {}
        for entry in entries:
            tier = entry.tier_name
            if tier in summary:
                summary[tier] += 1
            else:
                summary[tier] = 1
        return summary

    def validate_tier_capacity(self, entries: List[CacheEntry]) -> Dict[str, float]:
        """Compute capacity utilization per tier as a fraction of max size.

        This is used for reporting and does not affect eviction decisions.

        Args:
            entries: List of entries to compute capacity for.

        Returns:
            Dictionary mapping tier names to utilization ratios (0.0 to 1.0+).
        """
        tier_sizes: Dict[str, int] = {}
        for entry in entries:
            tier = entry.tier_name
            if tier not in tier_sizes:
                tier_sizes[tier] = 0
            tier_sizes[tier] += entry.size_bytes

        capacity_limit = self._max_entry_size * 100
        return {
            tier: total / capacity_limit
            for tier, total in tier_sizes.items()
        }
