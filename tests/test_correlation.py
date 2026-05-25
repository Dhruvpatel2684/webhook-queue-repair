"""
Tests for spatial-index-repair task.
Validates the geospatial sensor correlation engine output files.

Test tiers:
  - Tier 1 (basic): Structure checks that pass even with buggy code
  - Tier 2 (medium): Require fixing zone filtering (Bug A)
  - Tier 3 (hard): Require fixing threshold + aggregation (Bugs B + C)
  - Tier 4 (hardest): Require all bugs fixed simultaneously
"""

import json
import os


OUTPUT_DIR = "/app/runtime/output"
CORRELATIONS_PATH = os.path.join(OUTPUT_DIR, "correlations.json")
ZONE_SUMMARY_PATH = os.path.join(OUTPUT_DIR, "zone_summary.json")


def load_correlations():
    """Load correlations.json output file."""
    with open(CORRELATIONS_PATH, "r") as f:
        return json.load(f)


def load_zone_summary():
    """Load zone_summary.json output file."""
    with open(ZONE_SUMMARY_PATH, "r") as f:
        return json.load(f)


# ============================================================
# TIER 1: Basic structure (pass even with buggy code)
# ============================================================

def test_output_files_exist():
    """Both output files must be created in /app/runtime/output/ directory."""
    assert os.path.exists(CORRELATIONS_PATH), (
        f"correlations.json not found at {CORRELATIONS_PATH}"
    )
    assert os.path.exists(ZONE_SUMMARY_PATH), (
        f"zone_summary.json not found at {ZONE_SUMMARY_PATH}"
    )


def test_correlations_has_required_fields():
    """Correlations output must have correlation_count and pairs fields."""
    data = load_correlations()
    assert "correlation_count" in data, "Missing 'correlation_count' field"
    assert "pairs" in data, "Missing 'pairs' field"
    assert isinstance(data["pairs"], list), "'pairs' must be a list"
    assert data["correlation_count"] == len(data["pairs"]), (
        "correlation_count must equal length of pairs array"
    )


def test_zone_summary_has_required_fields():
    """Zone summary must have all required top-level fields."""
    data = load_zone_summary()
    required = ["total_zones", "total_readings_processed", "total_correlations",
                "report_digest", "zones"]
    for field in required:
        assert field in data, f"Missing required field '{field}' in zone_summary.json"


def test_total_readings_processed():
    """System must process all 54 sensor readings from 3 CSV files."""
    data = load_zone_summary()
    assert data["total_readings_processed"] == 54, (
        f"Expected 54 total readings, got {data['total_readings_processed']}"
    )


def test_correlation_pair_structure():
    """Each correlation pair must have all required fields with correct types."""
    data = load_correlations()
    required_fields = ["reading_type", "zone_a", "zone_b", "sensor_a", "sensor_b",
                       "timestamp_a", "timestamp_b", "time_delta", "strength",
                       "source_a", "source_b"]
    for pair in data["pairs"][:3]:  # Check first 3 pairs
        for field in required_fields:
            assert field in pair, f"Correlation pair missing field '{field}'"


def test_correlations_sorted_by_strength():
    """Correlation pairs must be sorted by strength descending."""
    data = load_correlations()
    strengths = [p["strength"] for p in data["pairs"]]
    assert strengths == sorted(strengths, reverse=True), (
        "Correlation pairs not sorted by strength descending"
    )


def test_zone_summary_zones_sorted():
    """Zone summary list must be sorted by zone_id alphabetically."""
    data = load_zone_summary()
    zone_ids = [z["zone_id"] for z in data["zones"]]
    assert zone_ids == sorted(zone_ids), (
        "Zones not sorted alphabetically by zone_id"
    )


# ============================================================
# TIER 2: Medium (requires fixing Bug A - zone filtering)
# ============================================================

def test_total_zones_count():
    """All 4 active zones must appear in the summary.
    Check that active_zones config parsing includes all zones correctly.
    The engine.ini file lists zone_alpha, zone_beta, zone_gamma, and zone_delta."""
    data = load_zone_summary()
    assert data["total_zones"] == 4, (
        f"Expected 4 zones, got {data['total_zones']}. "
        f"Check how active_zones are parsed from engine.ini — "
        f"whitespace handling in the comma-separated list may be dropping a zone."
    )


def test_zone_delta_present():
    """zone_delta must be present in the zone summary output.
    If missing, check how the active_zones config value is split and
    whether zone names are being trimmed of whitespace."""
    data = load_zone_summary()
    zone_ids = {z["zone_id"] for z in data["zones"]}
    assert "zone_delta" in zone_ids, (
        f"zone_delta missing from output. Found zones: {sorted(zone_ids)}. "
        f"Look at how get_active_zones() in correlation_engine.py parses the "
        f"comma-separated zone list from engine.ini."
    )


def test_zone_delta_in_correlations():
    """zone_delta must appear in at least one correlation pair."""
    data = load_correlations()
    has_delta = any(
        p["zone_a"] == "zone_delta" or p["zone_b"] == "zone_delta"
        for p in data["pairs"]
    )
    assert has_delta, (
        "zone_delta not found in any correlation pair. "
        "The zone filtering is likely excluding it."
    )


# ============================================================
# TIER 3: Hard (requires fixing Bugs B + C)
# ============================================================

def test_correlation_count():
    """Engine must find exactly 33 correlation pairs with correct threshold.
    The production-calibrated threshold from the [correlation.tuned] section
    of engine.ini should be used for scoring correlations."""
    data = load_correlations()
    assert data["correlation_count"] == 33, (
        f"Expected 33 correlations, got {data['correlation_count']}. "
        f"Check which config section the threshold is read from — "
        f"the [correlation.tuned] section has the calibrated value."
    )


def test_zone_reading_counts_last_window():
    """Zone reading_count must reflect the most recent observation window.
    The zone summary reading_count represents sensor density in the
    current time window, not a historical total."""
    data = load_zone_summary()
    zones = {z["zone_id"]: z for z in data["zones"]}

    # Most recent window has very few readings per zone (1-2 each)
    for zone_id, zone_data in zones.items():
        assert zone_data["reading_count"] <= 3, (
            f"{zone_id}: reading_count={zone_data['reading_count']} is too high. "
            f"Expected 1-2 readings per zone in the final observation window. "
            f"Review how window snapshots are combined in zone_aggregator.py."
        )


def test_strongest_correlation_value():
    """The strongest correlation must have strength 93.5."""
    data = load_correlations()
    assert len(data["pairs"]) > 0, "No correlations found"
    assert data["pairs"][0]["strength"] == 93.5, (
        f"Expected strongest correlation 93.5, got {data['pairs'][0]['strength']}"
    )


# ============================================================
# TIER 4: Hardest (requires ALL bugs fixed for correct digest)
# ============================================================

def test_report_digest():
    """Report digest must match the expected deterministic value.
    This requires all bugs to be fixed: zone filtering, threshold,
    aggregation mode, and sort ordering must all be correct."""
    data = load_zone_summary()
    assert data["report_digest"] == "b5d7f0206464a54e", (
        f"Expected digest 'b5d7f0206464a54e', got '{data['report_digest']}'. "
        f"The digest depends on zone counts, quality scores, correlation count, "
        f"and total readings — all upstream bugs must be fixed first."
    )


def test_correlation_sort_tiebreaker():
    """When two readings share the same timestamp, zone_a must be the
    alphabetically earlier zone_id. At timestamp 1700000145, three zones
    have temperature readings. The pair with strength 92.0 should show
    zone_beta as zone_a and zone_delta as zone_b.
    Check the sort key in compute_correlations() for deterministic ordering."""
    data = load_correlations()
    # Find the 92.0 strength pair at timestamp 1700000145
    target_pair = None
    for p in data["pairs"]:
        if (p["strength"] == 92.0 and
            p["timestamp_a"] == 1700000145 and
            p["timestamp_b"] == 1700000145):
            target_pair = p
            break
    assert target_pair is not None, (
        "Could not find correlation pair with strength 92.0 at timestamp 1700000145. "
        "Ensure zone_delta is included and the scoring threshold is correct."
    )
    assert target_pair["zone_a"] == "zone_beta", (
        f"Expected zone_a='zone_beta' for the 92.0 pair, got '{target_pair['zone_a']}'. "
        f"The sort tiebreaker for same-timestamp readings should produce "
        f"alphabetical zone ordering in correlation pairs."
    )
    assert target_pair["zone_b"] == "zone_delta", (
        f"Expected zone_b='zone_delta' for the 92.0 pair, got '{target_pair['zone_b']}'"
    )
