#!/usr/bin/env python3
"""
Repair script for spatial-index-repair task.
Patches bugs in correlation_engine.py and zone_aggregator.py, then re-runs.

Fixes applied:
1. correlation_engine.py get_active_zones(): strip whitespace from zone names
   after splitting on comma (fixes zone_delta being stored as " zone_delta")
2. correlation_engine.py get_correlation_threshold(): read from [correlation.tuned]
   section instead of [correlation] for the production-calibrated threshold
3. zone_aggregator.py aggregate_zone_summaries(): use last-write-wins instead of
   accumulating reading_count/total_value/total_quality across window snapshots
4. correlation_engine.py compute_correlations(): sort by (timestamp, zone_id, sensor_id)
   instead of (timestamp, sensor_id) for deterministic ordering at equal timestamps
"""

import os
import sys


def patch_correlation_engine():
    """Fix bugs in correlation_engine.py."""
    path = "/app/runtime/correlation_engine.py"
    with open(path, "r") as f:
        content = f.read()

    # Fix Bug A: strip whitespace from zone names in comma split
    content = content.replace(
        'return set(raw_zones.split(","))',
        'return set(item.strip() for item in raw_zones.split(","))'
    )

    # Fix Bug B: read threshold from correlation.tuned section
    content = content.replace(
        'return config.getint("correlation", "correlation_threshold")',
        'return config.getint("correlation.tuned", "correlation_threshold")'
    )

    # Fix Bug D: sort tiebreaker should use zone_id, not sensor_id
    content = content.replace(
        'type_readings.sort(key=lambda r: (r["timestamp"], r["sensor_id"]))',
        'type_readings.sort(key=lambda r: (r["timestamp"], r["zone_id"], r["sensor_id"]))'
    )

    with open(path, "w") as f:
        f.write(content)


def patch_zone_aggregator_zones():
    """Fix Bug A in zone_aggregator.py: strip whitespace from zone names."""
    path = "/app/runtime/zone_aggregator.py"
    with open(path, "r") as f:
        content = f.read()

    content = content.replace(
        'return set(raw_zones.split(","))',
        'return set(item.strip() for item in raw_zones.split(","))'
    )

    with open(path, "w") as f:
        f.write(content)


def patch_zone_aggregator():
    """Fix Bug C in zone_aggregator.py: use last-write-wins instead of accumulation."""
    path = "/app/runtime/zone_aggregator.py"
    with open(path, "r") as f:
        content = f.read()

    # Replace the accumulation logic with last-write-wins
    old_code = '''            # Accumulate snapshot values into running totals
            zone_summaries[zone_id]["reading_count"] += stats["reading_count"]
            zone_summaries[zone_id]["total_value"] += stats["total_value"]
            zone_summaries[zone_id]["total_quality"] += stats["total_quality"]'''

    new_code = '''            # Last-write-wins: use most recent window snapshot values
            zone_summaries[zone_id]["reading_count"] = stats["reading_count"]
            zone_summaries[zone_id]["total_value"] = stats["total_value"]
            zone_summaries[zone_id]["total_quality"] = stats["total_quality"]'''

    content = content.replace(old_code, new_code)

    with open(path, "w") as f:
        f.write(content)


def main():
    patch_correlation_engine()
    patch_zone_aggregator_zones()
    patch_zone_aggregator()

    # Re-run with fixed code
    sys.path.insert(0, "/app")

    # Clear cached modules
    for key in list(sys.modules.keys()):
        if key.startswith("runtime"):
            del sys.modules[key]

    from runtime.run_correlation import main as run_main
    run_main()


if __name__ == "__main__":
    main()
