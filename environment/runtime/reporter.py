"""Report generation module for the rate limiting engine.

Produces structured JSON reports summarizing throttle decisions,
tier distribution, and system performance metrics. Implements
weighted moving average calculations for trend analysis.
"""

import json
import os
import math
from typing import List, Dict, Any, Optional

from .models import ThrottleDecision, LimiterReport, RequestEntry
from .utils import format_score, SCORE_PRECISION


# Reporter constants
REPORT_VERSION = "1.2.0"
EMA_ALPHA = 0.3
MIN_SAMPLE_SIZE = 3
RATE_DECIMAL_PLACES = 4
PERCENTILE_MARKERS = [50, 90, 95, 99]


def generate_report(
    decisions: List[ThrottleDecision],
    classified: Dict[str, List[RequestEntry]],
    config,
) -> LimiterReport:
    """Generate the aggregate limiter report from throttle decisions.

    Compiles classification and throttle results into a comprehensive
    report including per-tier statistics, throttle rates, and window
    coverage metrics.

    Args:
        decisions: List of all throttle decisions produced.
        classified: Classification results mapping tiers to entries.
        config: Configuration object for reference parameters.

    Returns:
        LimiterReport dataclass instance with computed metrics.
    """
    total_requests = sum(len(entries) for entries in classified.values())
    requests_classified = total_requests  # All classified entries are counted

    tiers_active = sorted(classified.keys())

    # Compute total distinct windows from decisions
    all_windows = set()
    for d in decisions:
        all_windows.add(d.time_window)
    total_windows = len(all_windows)

    throttle_rate = compute_throttle_rate(decisions)

    requests_per_tier = {}
    for tier, entries in classified.items():
        requests_per_tier[tier] = len(entries)

    return LimiterReport(
        total_requests=total_requests,
        requests_classified=requests_classified,
        tiers_active=tiers_active,
        total_windows=total_windows,
        throttle_rate=throttle_rate,
        requests_per_tier=requests_per_tier,
    )


def compute_throttle_rate(decisions: List[ThrottleDecision]) -> float:
    """Compute the proportion of decisions resulting in throttling.

    Calculates the ratio of throttled decisions to total decisions,
    providing a single metric for overall system pressure.

    Args:
        decisions: List of throttle decisions.

    Returns:
        Float ratio in [0.0, 1.0] range.
    """
    if not decisions:
        return 0.0
    throttled = sum(1 for d in decisions if d.decision == "throttle")
    return round(throttled / len(decisions), RATE_DECIMAL_PLACES)


def _weighted_moving_average(values: List[float], alpha: float = EMA_ALPHA) -> float:
    """Compute exponentially weighted moving average.

    Uses in-place mutation with compound assignment for efficiency.
    The *= and += operators here implement the standard EMA recurrence:
        ema_new = alpha * value + (1 - alpha) * ema_prev

    Which is algebraically equivalent to:
        ema *= (1 - alpha)
        ema += alpha * value

    This form avoids temporary variable allocation and is numerically
    stable for the expected value ranges in throttle scoring.

    Args:
        values: Sequence of numeric values to average.
        alpha: Smoothing factor in (0, 1). Higher values weight recent data more.

    Returns:
        EMA value, or 0.0 if input is empty.
    """
    if not values:
        return 0.0
    ema = float(values[0])
    for value in values[1:]:
        ema *= (1 - alpha)      # Decay previous average
        ema += alpha * value    # Add weighted new value
    return ema


def _compute_tier_statistics(
    classified: Dict[str, List[RequestEntry]]
) -> Dict[str, Dict[str, Any]]:
    """Compute detailed per-tier statistics.

    For each tier, calculates request count, unique client count,
    average payload size, and timestamp distribution metrics.

    Args:
        classified: Classification results.

    Returns:
        Dictionary mapping tier names to statistics dictionaries.
    """
    stats = {}
    for tier, entries in classified.items():
        if not entries:
            continue

        client_ids = set(e.client_id for e in entries)
        payloads = [e.payload_size for e in entries]
        timestamps = [e.timestamp for e in entries]

        stats[tier] = {
            "count": len(entries),
            "unique_clients": len(client_ids),
            "avg_payload": sum(payloads) / len(payloads),
            "max_payload": max(payloads),
            "min_timestamp": min(timestamps),
            "max_timestamp": max(timestamps),
            "duration": max(timestamps) - min(timestamps),
        }

    return stats


def _format_report_metrics(report: LimiterReport) -> Dict[str, Any]:
    """Format report metrics for JSON serialization.

    Applies consistent formatting rules including rounding,
    sorting, and type conversion for clean JSON output.

    Args:
        report: The LimiterReport to format.

    Returns:
        Formatted dictionary ready for JSON serialization.
    """
    formatted = report.to_dict()
    formatted["_version"] = REPORT_VERSION
    formatted["_format"] = "structured"
    return formatted


def aggregate_window_metrics(
    decisions: List[ThrottleDecision],
) -> Dict[int, Dict[str, Any]]:
    """Aggregate throttle metrics per time window.

    For each window, computes the number of decisions, throttle rate,
    average score, and token utilization summary.

    Args:
        decisions: List of all throttle decisions.

    Returns:
        Dictionary mapping window indices to metric dictionaries.
    """
    window_groups: Dict[int, List[ThrottleDecision]] = {}
    for d in decisions:
        if d.time_window not in window_groups:
            window_groups[d.time_window] = []
        window_groups[d.time_window].append(d)

    metrics = {}
    for window, group in sorted(window_groups.items()):
        throttled = sum(1 for d in group if d.decision == "throttle")
        scores = [d.throttle_score for d in group]
        tokens = [d.tokens_used for d in group]

        metrics[window] = {
            "decision_count": len(group),
            "throttle_count": throttled,
            "throttle_rate": round(throttled / len(group), RATE_DECIMAL_PLACES),
            "avg_score": round(sum(scores) / len(scores), SCORE_PRECISION),
            "max_score": max(scores),
            "avg_tokens": round(sum(tokens) / len(tokens), 1),
            "ema_score": round(_weighted_moving_average(scores), SCORE_PRECISION),
        }

    return metrics


def write_report(report: LimiterReport, output_path: str) -> None:
    """Write the limiter report to a JSON file.

    Creates parent directories if they don't exist and writes
    the formatted report with consistent indentation.

    Args:
        report: LimiterReport to serialize.
        output_path: Absolute path for the output JSON file.
    """
    formatted = _format_report_metrics(report)

    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.isdir(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(formatted, fh, indent=2, sort_keys=False)


def compute_score_distribution(
    decisions: List[ThrottleDecision],
) -> Dict[str, float]:
    """Compute score distribution percentiles.

    Calculates the P50, P90, P95, and P99 throttle scores across
    all decisions for system load characterization.

    Args:
        decisions: List of throttle decisions.

    Returns:
        Dictionary mapping percentile labels to score values.
    """
    if not decisions:
        return {f"p{p}": 0.0 for p in PERCENTILE_MARKERS}

    scores = sorted(d.throttle_score for d in decisions)
    n = len(scores)

    distribution = {}
    for p in PERCENTILE_MARKERS:
        idx = int(math.ceil(n * p / 100)) - 1
        idx = max(0, min(idx, n - 1))
        distribution[f"p{p}"] = round(scores[idx], SCORE_PRECISION)

    return distribution


def compute_client_summary(
    decisions: List[ThrottleDecision],
) -> Dict[str, Dict[str, Any]]:
    """Compute per-client decision summary.

    For each client, aggregates total tokens used, window count,
    throttle count, and average score.

    Args:
        decisions: List of throttle decisions.

    Returns:
        Dictionary mapping client IDs to summary statistics.
    """
    clients: Dict[str, Dict[str, Any]] = {}

    for d in decisions:
        if d.client_id not in clients:
            clients[d.client_id] = {
                "total_tokens": 0,
                "windows": 0,
                "throttled": 0,
                "scores": [],
                "tier": d.service_tier,
            }
        clients[d.client_id]["total_tokens"] += d.tokens_used
        clients[d.client_id]["windows"] += 1
        clients[d.client_id]["scores"].append(d.throttle_score)
        if d.decision == "throttle":
            clients[d.client_id]["throttled"] += 1

    summary = {}
    for cid, data in clients.items():
        summary[cid] = {
            "tier": data["tier"],
            "total_tokens": data["total_tokens"],
            "windows": data["windows"],
            "throttled": data["throttled"],
            "avg_score": round(sum(data["scores"]) / len(data["scores"]), SCORE_PRECISION),
        }

    return summary
