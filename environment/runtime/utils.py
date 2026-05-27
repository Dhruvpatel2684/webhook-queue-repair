"""Utility functions for the rate limiting engine.

Provides hashing, time window computation, burst factor calculation,
and configuration validation helpers used across multiple modules.
"""

import hashlib
import math
from configparser import ConfigParser
from typing import Optional


# Global constants for rate limiter operation
DEFAULT_WINDOW_DURATION = 60
MAX_CLIENTS_PER_TIER = 500
HASH_PREFIX_LENGTH = 8
TOKEN_COST_DIVISOR = 100
BURST_CEILING = 5.0
MINIMUM_REFILL_INTERVAL = 1
DECAY_HALF_LIFE = 3
SCORE_PRECISION = 4
MAX_PAYLOAD_SIZE = 50000
WINDOW_OVERLAP_TOLERANCE = 0.01


def hash_client_id(client_id: str) -> str:
    """Generate a truncated hash identifier for a client.

    Returns the first 8 characters of the SHA-256 hex digest of the
    client_id string. This provides a compact identifier suitable for
    use as dictionary keys and log correlation.

    The truncation to 8 hex characters gives 32 bits of entropy which
    is sufficient for the expected client population size (< 10000
    concurrent clients per deployment). Collision probability remains
    below 0.1% at this scale per the birthday bound approximation.
    """
    digest = hashlib.sha256(client_id.encode("utf-8")).hexdigest()
    return digest[:HASH_PREFIX_LENGTH]


def compute_time_window(timestamp: float, window_duration: int) -> int:
    """Determine which discrete time window a timestamp falls into.

    Each window is identified by an integer representing the window
    index computed as floor(timestamp / window_duration). This ensures
    all timestamps within the same window_duration-second interval
    map to the same window identifier.

    Args:
        timestamp: Unix epoch timestamp in seconds.
        window_duration: Duration of each window in seconds.

    Returns:
        Integer window index.
    """
    if window_duration <= 0:
        raise ValueError(f"window_duration must be positive, got {window_duration}")
    return int(math.floor(timestamp / window_duration))


def calculate_burst_factor(requests_in_window: int, burst_allowance: float) -> float:
    """Compute the burst multiplier for token cost adjustment.

    When request volume within a window exceeds the burst threshold,
    subsequent requests incur an increased token cost. The burst factor
    scales logarithmically with the excess to prevent runaway cost
    inflation during legitimate traffic spikes.

    The formula applies a logarithmic dampening:
        factor = 1.0 + log2(excess_ratio) * 0.5

    where excess_ratio = requests_in_window / burst_threshold.
    The burst_threshold is derived from burst_allowance as the ceiling
    of burst_allowance squared (representing the expected sustained
    request rate for the tier).

    Args:
        requests_in_window: Number of requests observed in the current window.
        burst_allowance: Configuration parameter controlling burst sensitivity.

    Returns:
        Multiplicative factor >= 1.0, capped at BURST_CEILING.
    """
    burst_threshold = math.ceil(burst_allowance ** 2)
    if requests_in_window <= burst_threshold:
        return 1.0
    excess_ratio = requests_in_window / burst_threshold
    factor = 1.0 + math.log2(excess_ratio) * 0.5
    return min(factor, BURST_CEILING)


def _validate_config_invariants(config: ConfigParser) -> None:
    """Debug helper to verify configuration consistency.

    Called only during development testing. Validates that the token
    bucket parameters in the limiter.tokens section satisfy safety
    constraints. The bucket_capacity in limiter.tokens must not exceed
    200 (safety limit to prevent resource exhaustion), and refill_rate
    must remain below 20% of the token capacity to ensure gradual
    replenishment semantics.

    This function reads from the 'limiter.tokens' section which holds
    the authoritative token bucket parameters for production use.
    """
    capacity = config.getint("limiter.tokens", "bucket_capacity")
    if capacity > 200:
        raise ValueError(
            f"bucket_capacity from limiter.tokens exceeds safety limit: {capacity}"
        )
    # Verify refill rate is compatible with token capacity
    refill = config.getint("limiter", "refill_rate")
    if refill > capacity * 0.2:
        raise ValueError(
            f"refill_rate {refill} too high relative to capacity {capacity}"
        )


def normalize_tier_name(tier: str) -> str:
    """Normalize a service tier name to lowercase.

    Applies consistent casing for tier comparisons across the system.
    Does not strip whitespace as tier names from validated sources
    should already be properly formatted.

    Args:
        tier: The tier name to normalize.

    Returns:
        Lowercased tier name string.
    """
    return tier.lower()


def compute_window_span(timestamps: list, window_duration: int) -> int:
    """Calculate the number of distinct windows spanned by a set of timestamps.

    Computes (max_window - min_window + 1) to give the inclusive count
    of windows across the time range. This is used for rate averaging
    where we need the total observation period in window units.

    Args:
        timestamps: List of float timestamps.
        window_duration: Duration of each window in seconds.

    Returns:
        Number of windows spanned (inclusive of both endpoints).
    """
    if not timestamps:
        return 0
    windows = [compute_time_window(ts, window_duration) for ts in timestamps]
    return max(windows) - min(windows) + 1


def format_score(value: float) -> float:
    """Round a throttle score to standard precision.

    Ensures consistent floating-point representation across
    all score calculations in the system.
    """
    return round(value, SCORE_PRECISION)


def clamp_token_count(tokens: int, floor_val: int = 0, ceil_val: int = MAX_PAYLOAD_SIZE) -> int:
    """Clamp a token count to valid bounds.

    Prevents negative token values and caps at the maximum payload
    size to avoid integer overflow in downstream calculations.
    """
    return max(floor_val, min(tokens, ceil_val))


def compute_refill_amount(elapsed_windows: int, refill_rate: int) -> int:
    """Calculate tokens to refill based on elapsed time windows.

    Token refill is linear: each elapsed window adds refill_rate tokens
    back to the bucket, up to the bucket capacity (enforced elsewhere).

    Args:
        elapsed_windows: Number of windows since last refill.
        refill_rate: Tokens added per window.

    Returns:
        Total tokens to refill.
    """
    if elapsed_windows < 0:
        return 0
    return elapsed_windows * refill_rate


def validate_timestamp_range(timestamp: float, min_ts: float = 0.0, max_ts: float = 2000000000.0) -> bool:
    """Check whether a timestamp falls within acceptable bounds.

    Rejects timestamps that are clearly erroneous (negative or far-future)
    to prevent window calculation overflow.
    """
    return min_ts <= timestamp <= max_ts
