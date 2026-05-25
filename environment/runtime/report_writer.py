"""
Report Writer Module
Produces output files from correlation results and zone summaries.

Output files:
  - correlations.json: list of correlation pairs with scores
  - zone_summary.json: per-zone aggregated statistics and metadata
"""

import json
import hashlib
import os

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")


def compute_report_digest(correlations, zone_summaries, total_readings):
    """
    Compute a deterministic digest of the report for integrity verification.
    Iterates zones in sorted order and includes correlation count and
    total reading count for a stable hash.
    """
    digest_input = ""
    for zone_id in sorted(zone_summaries.keys()):
        zs = zone_summaries[zone_id]
        digest_input += f"{zone_id}:{zs['reading_count']}:{zs['mean_quality']}|"
    digest_input += f"corr:{len(correlations)}:readings:{total_readings}"
    return hashlib.sha256(digest_input.encode()).hexdigest()[:16]


def write_correlations(correlations):
    """Write correlation pairs to output JSON file."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    outpath = os.path.join(OUTPUT_DIR, "correlations.json")

    output = {
        "correlation_count": len(correlations),
        "pairs": correlations,
    }

    with open(outpath, "w") as f:
        json.dump(output, f, indent=2)
    return outpath


def write_zone_summary(zone_summaries, correlations, total_readings):
    """Write zone summary statistics to output JSON file."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    outpath = os.path.join(OUTPUT_DIR, "zone_summary.json")

    digest = compute_report_digest(correlations, zone_summaries, total_readings)

    # Build zone list sorted by zone_id
    zones_list = []
    for zone_id in sorted(zone_summaries.keys()):
        zones_list.append(zone_summaries[zone_id])

    output = {
        "total_zones": len(zone_summaries),
        "total_readings_processed": total_readings,
        "total_correlations": len(correlations),
        "report_digest": digest,
        "zones": zones_list,
    }

    with open(outpath, "w") as f:
        json.dump(output, f, indent=2)
    return outpath
