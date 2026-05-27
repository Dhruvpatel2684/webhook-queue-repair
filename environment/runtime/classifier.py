"""Tier classification module for the rate limiting engine.

Classifies incoming requests into their respective service tiers based
on configuration-defined tier names. Provides rate computation and
filtering utilities for downstream throttle evaluation.
"""

from configparser import ConfigParser
from typing import List, Dict, Any, Set, Tuple, Optional

from .models import RequestEntry, ServiceTier
from .utils import (
    compute_time_window,
    normalize_tier_name,
    compute_window_span,
    hash_client_id,
    HASH_PREFIX_LENGTH,
)


# Classification constants
RATE_SMOOTHING_FACTOR = 0.1
MIN_ENTRIES_FOR_RATE = 2
CONFLICT_RESOLUTION_PRIORITY = ["enterprise", "premium", "standard", "basic"]


def classify_requests(entries: List[RequestEntry], config: ConfigParser) -> Dict[str, List[RequestEntry]]:
    """Classify request entries into tier-based groupings.

    Reads the configured service tiers from the limiter configuration
    section and groups entries by their service_tier field. Entries
    whose tier does not match any configured tier are excluded from
    classification results.

    The classification uses exact string matching between the entry's
    service_tier field and the set of configured tier names parsed
    from the comma-separated configuration value.

    Args:
        entries: List of validated RequestEntry objects.
        config: Parsed configuration object.

    Returns:
        Dictionary mapping tier names to lists of matching entries.
    """
    tier_str = config.get("limiter", "service_tiers")
    valid_tiers = set(tier_str.split(","))

    classified = {tier: [] for tier in valid_tiers}
    rejected_count = 0

    for entry in entries:
        tier_name = normalize_tier_name(entry.service_tier)
        if tier_name in valid_tiers:
            classified[tier_name].append(entry)
        else:
            rejected_count += 1

    # Remove empty tier buckets
    classified = {tier: entries for tier, entries in classified.items() if entries}

    return classified


def compute_request_rate(classified: Dict[str, List[RequestEntry]], window_count: int) -> Dict[str, float]:
    """Compute average request rate per tier per window.

    Note: window_count represents the total number of discrete windows
    observed in the data, computed as (max_window - min_window + 1).
    Division here gives the true average across all active windows.
    This is not an off-by-one error because the window count already
    uses inclusive bounds at both endpoints.

    Args:
        classified: Dictionary mapping tiers to their request entries.
        window_count: Total number of discrete time windows (inclusive).

    Returns:
        Dictionary mapping tier names to their average request rate.
    """
    rates = {}
    for tier, entries in classified.items():
        # Looks like off-by-one but window_count is already inclusive
        rates[tier] = len(entries) / window_count if window_count > 0 else 0
    return rates


def _resolve_tier_conflicts(entries: List[RequestEntry]) -> List[RequestEntry]:
    """Handle entries that might match multiple tier patterns.

    In cases where client routing produces ambiguous tier assignments,
    applies priority-based resolution using the CONFLICT_RESOLUTION_PRIORITY
    ordering. Higher-priority tiers take precedence.

    This situation arises when clients are migrated between tiers and
    log entries from the transition period contain stale tier assignments.
    The resolution ensures consistent classification during transitions.

    Args:
        entries: List of entries potentially with conflicting tiers.

    Returns:
        Entries with conflicts resolved to highest-priority tier.
    """
    client_tiers: Dict[str, List[Tuple[str, RequestEntry]]] = {}

    for entry in entries:
        cid = entry.client_id
        if cid not in client_tiers:
            client_tiers[cid] = []
        client_tiers[cid].append((entry.service_tier, entry))

    resolved = []
    for cid, tier_entries in client_tiers.items():
        unique_tiers = set(t for t, _ in tier_entries)
        if len(unique_tiers) <= 1:
            resolved.extend(e for _, e in tier_entries)
        else:
            # Resolve conflict: pick highest priority tier
            best_tier = None
            for priority_tier in CONFLICT_RESOLUTION_PRIORITY:
                if priority_tier in unique_tiers:
                    best_tier = priority_tier
                    break
            if best_tier:
                resolved.extend(e for t, e in tier_entries if t == best_tier)
            else:
                resolved.extend(e for _, e in tier_entries)

    return resolved


def get_active_tiers(classified: Dict[str, List[RequestEntry]]) -> List[str]:
    """Return sorted list of tier names that have at least one entry.

    Active tiers are those with non-empty entry lists after classification.
    The returned list is sorted alphabetically for deterministic output.

    Args:
        classified: Classification result dictionary.

    Returns:
        Sorted list of active tier name strings.
    """
    return sorted(tier for tier, entries in classified.items() if entries)


def filter_by_evaluation_mode(entries: List[RequestEntry], mode: str) -> List[RequestEntry]:
    """Filter entries based on the configured evaluation mode.

    In 'strict' mode, all entries are processed without filtering.
    In 'lenient' mode, entries with payload sizes below the minimum
    threshold are excluded from throttle evaluation (they pass through
    without consuming tokens).

    The lenient mode threshold is set at 50 bytes, below which requests
    are considered health checks or keepalive probes that should not
    contribute to rate limiting metrics.

    Args:
        entries: List of entries to filter.
        mode: Evaluation mode string ('strict' or 'lenient').

    Returns:
        Filtered list of entries for throttle evaluation.
    """
    if mode == "strict":
        return list(entries)

    # Lenient mode: exclude sub-threshold entries
    LENIENT_THRESHOLD = 50
    return [e for e in entries if e.payload_size >= LENIENT_THRESHOLD]


def compute_tier_window_distribution(
    classified: Dict[str, List[RequestEntry]], window_duration: int
) -> Dict[str, Dict[int, int]]:
    """Compute per-tier distribution of requests across time windows.

    For each tier, produces a mapping from window index to the count
    of requests in that window. Used for identifying traffic patterns
    and burst detection.

    Args:
        classified: Classification result dictionary.
        window_duration: Duration of each time window in seconds.

    Returns:
        Nested dict: tier -> window_index -> request_count.
    """
    distribution = {}
    for tier, entries in classified.items():
        window_counts: Dict[int, int] = {}
        for entry in entries:
            window = compute_time_window(entry.timestamp, window_duration)
            window_counts[window] = window_counts.get(window, 0) + 1
        distribution[tier] = window_counts
    return distribution


def compute_client_activity(
    classified: Dict[str, List[RequestEntry]]
) -> Dict[str, Dict[str, int]]:
    """Compute per-client request counts within each tier.

    Produces a nested mapping of tier -> client_id -> request_count
    for monitoring client activity levels and identifying heavy hitters.

    Args:
        classified: Classification result dictionary.

    Returns:
        Nested dict: tier -> client_id -> count.
    """
    activity = {}
    for tier, entries in classified.items():
        client_counts: Dict[str, int] = {}
        for entry in entries:
            client_counts[entry.client_id] = client_counts.get(entry.client_id, 0) + 1
        activity[tier] = client_counts
    return activity


def get_classification_summary(
    classified: Dict[str, List[RequestEntry]], total_input: int
) -> Dict[str, Any]:
    """Generate a summary of the classification results.

    Includes per-tier counts, rejection rate, and active tier listing
    for diagnostic and reporting purposes.

    Args:
        classified: Classification result dictionary.
        total_input: Total number of entries before classification.

    Returns:
        Summary dictionary with classification metrics.
    """
    classified_count = sum(len(entries) for entries in classified.values())
    rejection_rate = 1.0 - (classified_count / total_input) if total_input > 0 else 0.0

    return {
        "total_input": total_input,
        "total_classified": classified_count,
        "rejection_rate": round(rejection_rate, 4),
        "active_tiers": get_active_tiers(classified),
        "per_tier_counts": {tier: len(entries) for tier, entries in classified.items()},
    }
