"""Data models for the multi-tier cache eviction engine.

Provides structured representations of cache entries and eviction decisions
used throughout the evaluation and scoring process.
"""

from dataclasses import dataclass


@dataclass
class CacheEntry:
    """Represents a single entry in one of the cache tiers.

    Attributes:
        entry_key: Unique identifier for the cache entry within its tier.
        tier_name: Name of the cache tier where this entry resides.
        access_frequency: Number of accesses recorded during the observation window.
        last_access_ts: Unix timestamp of the most recent access.
        size_bytes: Size of the cached object in bytes.
        ttl_remaining: Seconds remaining before natural expiration.
        estimated_cost: Estimated computational cost to regenerate this entry.
    """
    entry_key: str
    tier_name: str
    access_frequency: int
    last_access_ts: int
    size_bytes: int
    ttl_remaining: int
    estimated_cost: float


@dataclass
class EvictionResult:
    """Represents the outcome of an eviction evaluation for a single entry.

    Attributes:
        entry_key: Identifier of the evaluated cache entry.
        tier_name: Tier from which this entry would be evicted.
        eviction_score: Computed score indicating eviction priority.
        time_window: The processing window in which this entry was evaluated.
        hit_count: Normalized hit count derived from access frequency.
        decision: Either 'evict' or 'retain' based on threshold comparison.
    """
    entry_key: str
    tier_name: str
    eviction_score: float
    time_window: int
    hit_count: int
    decision: str
