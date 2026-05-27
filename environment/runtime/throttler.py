"""Token bucket and sliding window throttling module.

Implements the core rate limiting algorithm combining token bucket
capacity enforcement with sliding window request tracking. Produces
throttle decisions for each client-window combination based on
cumulative token consumption relative to bucket capacity.
"""

import math
from configparser import ConfigParser
from typing import List, Dict, Tuple, Any, Optional

from .models import RequestEntry, ThrottleDecision, TierCapacityMap
from .utils import (
    compute_time_window,
    calculate_burst_factor,
    format_score,
    clamp_token_count,
    compute_refill_amount,
    DECAY_HALF_LIFE,
    TOKEN_COST_DIVISOR,
    SCORE_PRECISION,
)


# Throttle module constants
WINDOW_WEIGHT_DECAY_BASE = 0.85
ACTIVE_WINDOW_THRESHOLD = 0.95
REFILL_GRANULARITY = 1
SCORE_NORMALIZATION_FLOOR = 0.0001
TOKEN_OVERHEAD_BYTES = 24
DECISION_THRESHOLD = 1.0


def apply_throttling(
    classified_requests: Dict[str, List[RequestEntry]], config: ConfigParser
) -> List[ThrottleDecision]:
    """Apply token bucket throttling to classified requests.

    For each client-window combination, computes cumulative token
    consumption and compares against the configured bucket capacity
    to produce allow/throttle decisions.

    The algorithm operates in multiple passes:
    1. Base token consumption computation per client per window
    2. Sliding window decay application for historical windows
    3. Window-relative weight adjustment for temporal fairness
    4. Final decision generation comparing consumption to capacity

    Args:
        classified_requests: Dictionary mapping tiers to request lists.
        config: Parsed configuration object.

    Returns:
        List of ThrottleDecision objects for all client-window pairs.
    """
    capacity = config.getint("limiter", "bucket_capacity")
    refill_rate = config.getint("limiter", "refill_rate")
    window_duration = config.getint("limiter", "window_duration")
    burst_allowance = config.getfloat("limiter.tokens", "burst_allowance")
    max_windows = config.getint("limiter.tokens", "max_windows")

    consumption: Dict[Tuple[str, int], Dict[str, Any]] = {}
    client_window_entries: Dict[Tuple[str, int], List[RequestEntry]] = {}
    all_windows = set()

    # First pass: compute base token consumption per window
    for tier, entries in classified_requests.items():
        for entry in entries:
            window = compute_time_window(entry.timestamp, window_duration)
            key = (entry.client_id, window)
            all_windows.add(window)

            if key not in consumption:
                consumption[key] = {
                    "tokens_used": 0,
                    "tier": tier,
                    "count": 0,
                    "burst_factor": 1.0,
                }
            if key not in client_window_entries:
                client_window_entries[key] = []

            client_window_entries[key].append(entry)
            tokens = _calculate_token_cost(entry, burst_allowance)
            consumption[key]["tokens_used"] += tokens
            consumption[key]["count"] += 1

    # Determine window range for decay calculations
    if not all_windows:
        return []
    min_window = min(all_windows)
    max_window = max(all_windows)
    window_span = max_window - min_window + 1

    # Compute per-client window presence for refill eligibility
    client_windows = _compute_client_window_map(consumption)

    # Apply sliding window decay for windows beyond the decay threshold
    _sliding_window_decay(consumption, max_windows, max_window)

    # Apply token refill for clients with gaps between active windows
    _apply_refill(consumption, refill_rate, client_windows)

    # Apply burst factor scaling for high-density windows
    _apply_burst_scaling(consumption, burst_allowance)

    # Second pass: apply sliding window weight normalization
    # Adjusts token counts based on temporal position within the observation window
    for tier, entries in classified_requests.items():
        for entry in entries:
            window = compute_time_window(entry.timestamp, window_duration)
            key = (entry.client_id, window)
            tokens = _calculate_token_cost(entry, burst_allowance)
            # Apply window-relative weight for temporal distribution fairness
            weight = _compute_window_weight(window, max_window)
            consumption[key]["tokens_used"] += int(tokens * weight)

    # Generate throttle decisions from consumption state
    decisions = []
    processed_keys = set()

    for tier, entries in classified_requests.items():
        for entry in entries:
            window = compute_time_window(entry.timestamp, window_duration)
            key = (entry.client_id, window)

            if key in processed_keys:
                continue
            processed_keys.add(key)

            state = consumption[key]
            tokens_used = state["tokens_used"]
            effective_capacity = TierCapacityMap.get_effective_capacity(
                _resolve_tier_enum(state["tier"]), capacity
            )

            decision_str = evaluate_decision(tokens_used, effective_capacity)
            rate = state["count"] / window_duration if window_duration > 0 else 0
            score = compute_throttle_score(tokens_used, effective_capacity, rate)

            decisions.append(ThrottleDecision(
                client_id=entry.client_id,
                service_tier=state["tier"],
                throttle_score=score,
                time_window=window,
                tokens_used=tokens_used,
                decision=decision_str,
            ))

    return decisions


def _calculate_token_cost(entry: RequestEntry, burst_allowance: float) -> int:
    """Compute the token cost for a single request entry.

    Token cost is determined primarily by payload size, with a fixed
    overhead added per request to account for connection and header
    processing costs. The formula ensures that even zero-payload
    requests consume at least one token.

    Formula: tokens = (payload_size + overhead) // divisor + 1

    Args:
        entry: The request entry to compute cost for.
        burst_allowance: Burst configuration (reserved for future use).

    Returns:
        Integer token cost for the request.
    """
    raw_cost = (entry.payload_size + TOKEN_OVERHEAD_BYTES) // TOKEN_COST_DIVISOR + 1
    return clamp_token_count(raw_cost)


def _compute_window_weight(window: int, max_window: int) -> float:
    """Compute the temporal weight for a given window.

    Windows closer to the current (max) window receive higher weight
    to reflect recency bias in rate limiting decisions. The decay
    follows an exponential curve with base WINDOW_WEIGHT_DECAY_BASE.

    For windows within the active threshold (distance 0-1 from max),
    the weight is clamped to 1.0 to prevent over-penalization of
    current traffic.

    Args:
        window: The window index to compute weight for.
        max_window: The most recent window index in the dataset.

    Returns:
        Float weight in range (0.0, 1.0].
    """
    distance = max_window - window
    if distance <= 0:
        return 1.0

    raw_weight = WINDOW_WEIGHT_DECAY_BASE ** distance
    if raw_weight >= ACTIVE_WINDOW_THRESHOLD:
        return 1.0
    return raw_weight


def _compute_client_window_map(
    consumption: Dict[Tuple[str, int], Dict[str, Any]]
) -> Dict[str, List[int]]:
    """Build a mapping of client IDs to their active window indices.

    Used for determining refill eligibility based on gaps between
    a client's consecutive windows.

    Args:
        consumption: Current consumption state.

    Returns:
        Dict mapping client_id to sorted list of window indices.
    """
    client_windows: Dict[str, List[int]] = {}
    for (client_id, window), _ in consumption.items():
        if client_id not in client_windows:
            client_windows[client_id] = []
        client_windows[client_id].append(window)

    for client_id in client_windows:
        client_windows[client_id].sort()

    return client_windows


def _apply_refill(
    consumption: Dict[Tuple[str, int], Dict[str, Any]],
    refill_rate: int,
    client_windows: Dict[str, List[int]],
) -> None:
    """Apply token refill credits for windows with inter-window gaps.

    Refill only applies when a client has non-consecutive windows,
    representing periods where the client was inactive and tokens
    should have been replenished. The refill amount is proportional
    to the gap size.

    Consecutive windows (gap=1) do not receive refill credits as
    the client was continuously active during that period.

    Args:
        consumption: Mutable consumption state dictionary.
        refill_rate: Tokens refilled per gap window.
        client_windows: Map of client IDs to their window indices.
    """
    for (client_id, window), state in consumption.items():
        windows = client_windows.get(client_id, [])
        if len(windows) < 2:
            continue

        # Find gap before this window
        window_idx = windows.index(window) if window in windows else -1
        if window_idx <= 0:
            continue

        prev_window = windows[window_idx - 1]
        gap = window - prev_window - 1  # Number of inactive windows between

        if gap > 0:
            refill = gap * refill_rate
            state["tokens_used"] = max(0, state["tokens_used"] - refill)


def _sliding_window_decay(
    consumption: Dict[Tuple[str, int], Dict[str, Any]],
    max_windows: int,
    current_window: int,
) -> None:
    """Apply decay to token consumption for aged windows.

    Windows that are significantly older than the current window
    have their token counts decayed to reflect the diminishing
    relevance of historical consumption patterns.

    Only windows beyond the DECAY_HALF_LIFE distance are decayed.
    The decay factor is: 0.5 ^ (distance / half_life)

    Args:
        consumption: Mutable consumption state dictionary.
        max_windows: Maximum tracked window count.
        current_window: The most recent window index.
    """
    for key, state in consumption.items():
        _, window = key
        distance = current_window - window
        if distance > DECAY_HALF_LIFE:
            decay_factor = 0.5 ** (distance / DECAY_HALF_LIFE)
            state["tokens_used"] = int(state["tokens_used"] * decay_factor)


def _apply_burst_scaling(
    consumption: Dict[Tuple[str, int], Dict[str, Any]],
    burst_allowance: float,
) -> None:
    """Apply burst factor scaling for high-density windows.

    Windows with request counts exceeding the burst threshold have
    their token consumption scaled up by the computed burst factor.
    This penalizes bursty traffic patterns that may indicate abuse.

    Args:
        consumption: Mutable consumption state dictionary.
        burst_allowance: Configuration parameter for burst sensitivity.
    """
    for key, state in consumption.items():
        count = state["count"]
        burst = calculate_burst_factor(count, burst_allowance)
        state["burst_factor"] = burst
        if burst > 1.0:
            state["tokens_used"] = int(state["tokens_used"] * burst)


def evaluate_decision(tokens_used: int, capacity: int) -> str:
    """Determine throttle decision based on token usage vs capacity.

    If cumulative token usage meets or exceeds the effective bucket
    capacity, the decision is 'throttle'. Otherwise, the request is
    allowed to proceed.

    Args:
        tokens_used: Total tokens consumed in the evaluation window.
        capacity: Effective bucket capacity for the client's tier.

    Returns:
        Decision string: 'allow' or 'throttle'.
    """
    if capacity <= 0:
        return "throttle"
    ratio = tokens_used / capacity
    if ratio >= DECISION_THRESHOLD:
        return "throttle"
    return "allow"


def compute_throttle_score(tokens_used: int, capacity: int, rate: float) -> float:
    """Compute a priority score for throttle ordering.

    The score represents how close a client is to their capacity
    limit, normalized to [0, 1] range. Higher scores indicate
    greater throttle pressure.

    Formula: score = min(1.0, tokens_used / max(capacity, 1))

    The rate parameter is reserved for future weighted scoring
    but currently does not affect the computation.

    Args:
        tokens_used: Total tokens consumed.
        capacity: Effective bucket capacity.
        rate: Request rate (requests per second) - reserved.

    Returns:
        Float score in [0.0, 1.0] range.
    """
    if capacity <= 0:
        return 1.0
    raw_score = tokens_used / capacity
    return format_score(min(1.0, raw_score))


def _resolve_tier_enum(tier_name: str):
    """Resolve a tier name string to its ServiceTier enum value.

    Falls back to BASIC tier if the name cannot be resolved, ensuring
    that capacity calculations always have a valid tier reference.
    """
    from .models import ServiceTier
    try:
        return ServiceTier.from_string(tier_name)
    except ValueError:
        return ServiceTier.BASIC


def get_consumption_summary(
    consumption: Dict[Tuple[str, int], Dict[str, Any]]
) -> Dict[str, Any]:
    """Generate a summary of token consumption state.

    Provides aggregate statistics across all client-window pairs
    for monitoring and diagnostic output.
    """
    if not consumption:
        return {"total_pairs": 0, "total_tokens": 0, "avg_tokens": 0}

    total_tokens = sum(s["tokens_used"] for s in consumption.values())
    return {
        "total_pairs": len(consumption),
        "total_tokens": total_tokens,
        "avg_tokens": total_tokens / len(consumption),
        "max_tokens": max(s["tokens_used"] for s in consumption.values()),
    }


def compute_per_client_utilization(
    decisions: List[ThrottleDecision], capacity: int
) -> Dict[str, float]:
    """Compute capacity utilization percentage per client.

    Aggregates token usage across windows for each client and
    expresses as a percentage of total available capacity.

    Args:
        decisions: List of throttle decisions.
        capacity: Bucket capacity.

    Returns:
        Dict mapping client_id to utilization percentage.
    """
    client_tokens: Dict[str, int] = {}
    client_windows: Dict[str, int] = {}

    for d in decisions:
        if d.client_id not in client_tokens:
            client_tokens[d.client_id] = 0
            client_windows[d.client_id] = 0
        client_tokens[d.client_id] += d.tokens_used
        client_windows[d.client_id] += 1

    utilization = {}
    for cid, tokens in client_tokens.items():
        windows = client_windows[cid]
        total_capacity = capacity * max(windows, 1)
        utilization[cid] = round(tokens / total_capacity, 4) if total_capacity > 0 else 0
    return utilization


def compute_window_pressure(
    decisions: List[ThrottleDecision],
) -> Dict[int, float]:
    """Compute aggregate throttle pressure per time window.

    For each window, calculates the average throttle score across
    all clients active in that window.

    Args:
        decisions: List of throttle decisions.

    Returns:
        Dict mapping window index to average pressure score.
    """
    window_scores: Dict[int, List[float]] = {}
    for d in decisions:
        if d.time_window not in window_scores:
            window_scores[d.time_window] = []
        window_scores[d.time_window].append(d.throttle_score)

    pressure = {}
    for window, scores in window_scores.items():
        pressure[window] = round(sum(scores) / len(scores), SCORE_PRECISION)
    return pressure


def compute_tier_throttle_breakdown(
    decisions: List[ThrottleDecision],
) -> Dict[str, Dict[str, int]]:
    """Compute per-tier breakdown of allow vs throttle decisions.

    Args:
        decisions: List of throttle decisions.

    Returns:
        Dict mapping tier to {allow: count, throttle: count}.
    """
    breakdown: Dict[str, Dict[str, int]] = {}
    for d in decisions:
        if d.service_tier not in breakdown:
            breakdown[d.service_tier] = {"allow": 0, "throttle": 0}
        breakdown[d.service_tier][d.decision] += 1
    return breakdown
