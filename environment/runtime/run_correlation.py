"""
Geospatial Sensor Correlation Engine - Main Entry Point
Processes sensor readings from multiple geographic clusters, identifies
cross-zone correlations, and produces summary reports.

Usage: python3 -m runtime.run_correlation

Reads: sensors_north.csv, sensors_south.csv, sensors_east.csv, engine.ini
Produces:
  - output/correlations.json (cross-zone correlation pairs)
  - output/zone_summary.json (per-zone aggregated statistics)
"""

import os
import sys

RUNTIME_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(RUNTIME_DIR))

from runtime.data_loader import load_all_readings
from runtime.correlation_engine import load_config, compute_correlations
from runtime.zone_aggregator import compute_window_snapshots, aggregate_zone_summaries
from runtime.report_writer import write_correlations, write_zone_summary


def main():
    """Main execution: load data, compute correlations, write reports."""
    readings = load_all_readings()
    print(f"Loaded {len(readings)} sensor readings")

    config = load_config()

    # Compute cross-zone correlations
    correlations = compute_correlations(readings, config)
    print(f"Found {len(correlations)} correlation pairs")

    # Compute zone summaries from windowed aggregation
    snapshots = compute_window_snapshots(readings, config)
    zone_summaries = aggregate_zone_summaries(snapshots)
    print(f"Aggregated {len(zone_summaries)} zone summaries")

    # Write output files
    corr_path = write_correlations(correlations)
    summary_path = write_zone_summary(zone_summaries, correlations, len(readings))

    print(f"Output written:")
    print(f"  - {corr_path}")
    print(f"  - {summary_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
