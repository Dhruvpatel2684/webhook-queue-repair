"""
Correlation Engine Module
Identifies cross-zone correlations in sensor readings.
Two readings are correlated if they share the same reading_type,
occur within max_time_gap seconds, and originate from different zones.

Correlation strength is computed as:
  strength = (1 - time_delta / max_time_gap) * avg_quality * 100

Only correlations above the configured threshold are included.
"""

import configparser
import os

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "engine.ini")


def load_config():
    """Load engine configuration."""
    config = configparser.ConfigParser()
    config.read(CONFIG_PATH)
    return config


def get_active_zones(config):
    """
    Retrieve the set of zones that should be included in correlation.
    Zones not in this set are excluded from all processing.
    """
    raw_zones = config.get("correlation", "active_zones")
    return set(raw_zones.split(","))


def get_correlation_threshold(config):
    """
    Retrieve the minimum correlation strength threshold.
    Readings below this threshold are not included in output.
    """
    return config.getint("correlation", "correlation_threshold")


def compute_correlations(readings, config):
    """
    Find all cross-zone correlations in the reading stream.

    A correlation pair consists of two readings from different zones with the
    same reading_type within max_time_gap seconds. Each pair is scored by
    temporal proximity and data quality.

    Results are sorted by strength descending, then by timestamp ascending.
    Note: seq ordering is local to each source cluster.
    """
    active_zones = get_active_zones(config)
    threshold = get_correlation_threshold(config)
    max_gap = config.getint("correlation", "max_time_gap")

    # Filter to active zones only
    filtered = [r for r in readings if r["zone_id"] in active_zones]

    # Group by reading_type for efficient pair finding
    by_type = {}
    for r in filtered:
        rtype = r["reading_type"]
        if rtype not in by_type:
            by_type[rtype] = []
        by_type[rtype].append(r)

    correlations = []
    for rtype, type_readings in by_type.items():
        # Sort by timestamp within each type
        type_readings.sort(key=lambda r: (r["timestamp"], r["sensor_id"]))

        for i in range(len(type_readings)):
            for j in range(i + 1, len(type_readings)):
                r1 = type_readings[i]
                r2 = type_readings[j]

                # Must be different zones
                if r1["zone_id"] == r2["zone_id"]:
                    continue

                time_delta = abs(r2["timestamp"] - r1["timestamp"])
                if time_delta > max_gap:
                    break  # sorted by time, no more pairs possible

                # Compute correlation strength
                avg_quality = (r1["quality"] + r2["quality"]) / 2
                strength = round((1 - time_delta / max_gap) * avg_quality * 100, 2)

                if strength >= threshold:
                    correlations.append({
                        "reading_type": rtype,
                        "zone_a": r1["zone_id"],
                        "zone_b": r2["zone_id"],
                        "sensor_a": r1["sensor_id"],
                        "sensor_b": r2["sensor_id"],
                        "timestamp_a": r1["timestamp"],
                        "timestamp_b": r2["timestamp"],
                        "time_delta": time_delta,
                        "strength": strength,
                        "source_a": r1["source"],
                        "source_b": r2["source"],
                    })

    # Sort: strongest first, then by earliest timestamp for ties
    correlations.sort(key=lambda c: (-c["strength"], c["timestamp_a"]))
    return correlations
