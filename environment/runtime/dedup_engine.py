"""
Deduplication engine for event stream processing.

Uses hash-based identification to detect and remove duplicate events,
with an LRU cache for efficient lookup on large event volumes and
configurable eviction policies.
"""

import hashlib
import logging
from collections import OrderedDict
from typing import Dict, List, Optional, Set, Tuple

from .models import Event, ProcessingMetrics

logger = logging.getLogger(__name__)

# Cache configuration
DEFAULT_CACHE_MAX_SIZE = 10000
CACHE_EVICTION_BATCH_SIZE = 100
HASH_ALGORITHM = "sha256"


class LRUDedupCache:
    """
    Least-Recently-Used cache for deduplication hash lookups.

    Maintains an ordered dictionary where access moves items to the end.
    When capacity is exceeded, the oldest entries are evicted in batches
    to amortize eviction overhead.
    """

    def __init__(self, max_size: int = DEFAULT_CACHE_MAX_SIZE):
        self.max_size = max_size
        self._cache: OrderedDict[str, bool] = OrderedDict()
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    def contains(self, key: str) -> bool:
        """Check if key exists in cache, updating access order."""
        if key in self._cache:
            self._cache.move_to_end(key)
            self._hits += 1
            return True
        self._misses += 1
        return False

    def add(self, key: str):
        """Add a key to the cache, triggering eviction if needed."""
        if key in self._cache:
            self._cache.move_to_end(key)
            return

        self._cache[key] = True

        if len(self._cache) > self.max_size:
            self._evict_batch()

    def _evict_batch(self):
        """Remove oldest entries in a batch to reduce eviction frequency."""
        evict_count = min(CACHE_EVICTION_BATCH_SIZE, len(self._cache) // 10)
        evict_count = max(evict_count, 1)

        for _ in range(evict_count):
            if self._cache:
                self._cache.popitem(last=False)
                self._evictions += 1

    @property
    def size(self) -> int:
        return len(self._cache)

    @property
    def stats(self) -> Dict[str, int]:
        return {
            "size": self.size,
            "hits": self._hits,
            "misses": self._misses,
            "evictions": self._evictions,
            "hit_rate_pct": int(
                self._hits / max(self._hits + self._misses, 1) * 100
            ),
        }


# Dedup strategy: events are uniquely identified by their stream, position,
# and schema version. Reprocessed events share coordinates but differ in version.


def compute_dedup_key(event: Event) -> str:
    """
    Compute the deduplication hash key for an event.

    The key uniquely identifies an event instance using its stream,
    sequence number, and associated temporal marker.

    Args:
        event: The event to compute a dedup key for

    Returns:
        Hex digest string of the hash
    """
    # Identity key: stream_id + seq + version (see engine.ini dedup_fields)
    raw_key = f"{event.stream_id}:{event.seq}:{event.timestamp}"
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def deduplicate_events(
    events: List[Event],
    metrics: ProcessingMetrics,
    cache_size: int = DEFAULT_CACHE_MAX_SIZE,
) -> List[Event]:
    """
    Remove duplicate events from the event list.

    Uses hash-based deduplication with an LRU cache for efficient
    lookup. Events are processed in order and the first occurrence
    of each unique event is kept.

    Args:
        events: List of events potentially containing duplicates
        metrics: Metrics collector for tracking dedup statistics
        cache_size: Maximum size of the dedup cache

    Returns:
        List of unique events in original order
    """
    cache = LRUDedupCache(max_size=cache_size)
    unique_events: List[Event] = []
    duplicate_count = 0

    logger.info("Starting deduplication of %d events", len(events))

    for event in events:
        dedup_key = compute_dedup_key(event)

        if cache.contains(dedup_key):
            duplicate_count += 1
            logger.debug(
                "Duplicate detected: stream=%s seq=%d version=%d",
                event.stream_id, event.seq, event.version
            )
            continue

        cache.add(dedup_key)
        unique_events.append(event)

    metrics.events_after_dedup = len(unique_events)

    cache_stats = cache.stats
    logger.info(
        "Deduplication complete: %d events in, %d unique, %d duplicates removed",
        len(events), len(unique_events), duplicate_count
    )
    logger.info(
        "Cache stats: size=%d, hits=%d, misses=%d, hit_rate=%d%%",
        cache_stats["size"], cache_stats["hits"],
        cache_stats["misses"], cache_stats["hit_rate_pct"]
    )

    return unique_events
