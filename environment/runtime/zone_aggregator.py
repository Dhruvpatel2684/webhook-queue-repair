"""
Zone Aggregator Module
Computes per-zone statistics from sensor readings using time windows.

Processing divides the observation period into fixed-size windows.
For each zone, each window produces a snapshot with:
  - reading_count for that window
  - sum of values for that window
  - sum of quality scores for that window
  - set of reading types observed

Final zone summaries combine window snapshots:
  - reading_count: total count from the last window snapshot only
    (represents the most recent observation density for that zone)
  - mean_value: total_value / reading_count from the last snapshot
  - mean_quality: total_quality / reading_count from the last snapshot
  - distinct_types: union of all types seen across all windows
"""

import configparser
import os

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "engine.ini")
WINDOW_SIZE = 120  # seconds per time window


def load_config():
    """Load engine configuration."""
    config = configparser.ConfigParser()
    config.read(CONFIG_PATH)
    return config


def get_active_zones(config):
    """Retrieve active zones from configuration."""
    raw_zones = config.get("correlation", "active_zones")
    return set(raw_zones.split(","))


def compute_window_snapshots(readings, config):
    """
    Divide readings into time windows and compute per-zone snapshots.
    Returns a list of window snapshots, each containing zone stats.
    """
    active_zones = get_active_zones(config)
    filtered = [r for r in readings if r["zone_id"] in active_zones]

    if not filtered:
        return []

    min_ts = filtered[0]["timestamp"]
    max_ts = filtered[-1]["timestamp"]

    snapshots = []
    window_start = min_ts

    while window_start <= max_ts:
        window_end = window_start + WINDOW_SIZE
        window_readings = [
            r for r in filtered
            if window_start <= r["timestamp"] < window_end
        ]

        zone_stats = {}
        for r in window_readings:
            zone = r["zone_id"]
            if zone not in zone_stats:
                zone_stats[zone] = {
                    "reading_count": 0,
                    "total_value": 0.0,
                    "total_quality": 0.0,
                    "types_seen": set(),
                }
            zone_stats[zone]["reading_count"] += 1
            zone_stats[zone]["total_value"] += r["value"]
            zone_stats[zone]["total_quality"] += r["quality"]
            zone_stats[zone]["types_seen"].add(r["reading_type"])

        if zone_stats:
            snapshots.append({
                "window_start": window_start,
                "window_end": window_end,
                "zones": zone_stats,
            })

        window_start = window_end

    return snapshots


def aggregate_zone_summaries(snapshots):
    """
    Produce final per-zone summaries from window snapshots.

    The final summary for each zone uses the values from its last window
    snapshot (the most recent observation period). This represents the
    current state of sensor density and quality in each zone.
    Types seen are accumulated across all windows for completeness.
    """
    zone_summaries = {}

    for snapshot in snapshots:
        for zone_id, stats in snapshot["zones"].items():
            if zone_id not in zone_summaries:
                zone_summaries[zone_id] = {
                    "zone_id": zone_id,
                    "reading_count": 0,
                    "total_value": 0.0,
                    "total_quality": 0.0,
                    "types_seen": set(),
                }
            # Accumulate snapshot values into running totals
            zone_summaries[zone_id]["reading_count"] += stats["reading_count"]
            zone_summaries[zone_id]["total_value"] += stats["total_value"]
            zone_summaries[zone_id]["total_quality"] += stats["total_quality"]
            zone_summaries[zone_id]["types_seen"].update(stats["types_seen"])

    # Finalize: compute averages from accumulated totals
    result = {}
    for zone_id, summary in zone_summaries.items():
        count = summary["reading_count"]
        result[zone_id] = {
            "zone_id": zone_id,
            "reading_count": count,
            "mean_value": round(summary["total_value"] / count, 2) if count > 0 else 0.0,
            "mean_quality": round(summary["total_quality"] / count, 4) if count > 0 else 0.0,
            "distinct_types": len(summary["types_seen"]),
        }

    return result
