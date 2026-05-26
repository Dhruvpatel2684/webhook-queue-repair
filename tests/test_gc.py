"""
Tests for the MVCC Garbage Collector.

Validates that the GC system correctly identifies version candidates
for garbage collection based on MVCC visibility rules and active
transaction snapshots.
"""

import json
import os
import pytest


OUTPUT_FILE = os.environ.get("GC_OUTPUT_FILE", "/app/runtime/gc_output.json")


@pytest.fixture(scope="session")
def gc_output():
    """Load the GC output file."""
    with open(OUTPUT_FILE, "r") as f:
        return json.load(f)


# ============================================================
# Tier 1: Structural tests (pass regardless of bugs)
# ============================================================


def test_output_file_exists():
    """Verify the GC output file was created."""
    assert os.path.exists(OUTPUT_FILE), (
        "gc_output.json was not created by the process"
    )


def test_state_has_required_fields(gc_output):
    """Verify state section contains all required fields."""
    state = gc_output["state"]
    required = ["total_keys", "total_versions", "active_transactions", "watermark"]
    for field in required:
        assert field in state, f"Missing state field: {field}"


def test_gc_plan_has_required_fields(gc_output):
    """Verify gc_plan section contains all required fields."""
    plan = gc_output["gc_plan"]
    required = [
        "total_reclaimable_versions",
        "estimated_space_savings_bytes",
        "batches",
        "batch_count",
        "keys_affected",
        "bytes_per_version_used",
    ]
    for field in required:
        assert field in plan, f"Missing gc_plan field: {field}"


def test_total_keys_in_store(gc_output):
    """Verify the correct number of keys were loaded from version store."""
    assert gc_output["state"]["total_keys"] == 17


def test_total_versions_loaded(gc_output):
    """Verify the correct number of versions were loaded."""
    assert gc_output["state"]["total_versions"] == 85


def test_active_transactions_loaded(gc_output):
    """Verify the correct number of active transactions."""
    assert gc_output["state"]["active_transactions"] == 5


def test_gc_plan_is_dict(gc_output):
    """Verify the gc_plan is a properly structured dict."""
    plan = gc_output["gc_plan"]
    assert isinstance(plan, dict)
    assert isinstance(plan["batches"], list)
    assert isinstance(plan["keys_affected"], list)
    assert isinstance(plan["total_reclaimable_versions"], int)


# ============================================================
# Tier 2: Watermark and snapshot protection tests
# ============================================================


def test_watermark_value(gc_output):
    """Verify the GC watermark is computed correctly."""
    assert gc_output["state"]["watermark"] == 150


def test_active_txn_snapshot_respected(gc_output):
    """Verify versions visible to active transactions are not collected."""
    candidates = gc_output["gc_candidates"]["by_key"]
    if "users/1002" in candidates:
        assert "v-008" not in candidates["users/1002"]["version_ids"], (
            "v-008 (commit_ts=175) should be protected"
        )


def test_version_protected_at_watermark(gc_output):
    """Verify versions at exactly the watermark boundary are protected."""
    candidates = gc_output["gc_candidates"]["by_key"]
    if "inventory/7002" in candidates:
        assert "v-037" not in candidates["inventory/7002"]["version_ids"], (
            "v-037 (commit_ts=150) should be protected"
        )


# ============================================================
# Tier 3: Version chain and candidate identification tests
# ============================================================


def test_oldest_version_collected(gc_output):
    """Verify the oldest superseded version is identified for collection."""
    candidates = gc_output["gc_candidates"]["by_key"]
    assert "users/1001" in candidates, (
        "users/1001 should have GC candidates"
    )
    assert "v-001" in candidates["users/1001"]["version_ids"], (
        "v-001 (commit_ts=50) should be collected"
    )


def test_total_candidate_versions(gc_output):
    """Verify the total number of GC candidate versions identified."""
    assert gc_output["gc_candidates"]["total_candidate_versions"] == 34


def test_correct_candidates_for_key(gc_output):
    """Verify the exact set of candidates for a specific key."""
    candidates = gc_output["gc_candidates"]["by_key"]
    assert "users/1001" in candidates
    version_ids = set(candidates["users/1001"]["version_ids"])
    expected = {"v-001", "v-002", "v-003"}
    assert version_ids == expected, (
        f"Expected candidates {expected} for users/1001, got {version_ids}"
    )


# ============================================================
# Tier 4: Aggregate correctness tests (require all fixes)
# ============================================================


def test_space_savings_estimate(gc_output):
    """Verify the estimated space savings calculation."""
    plan = gc_output["gc_plan"]
    assert plan["estimated_space_savings_bytes"] == 3808, (
        f"Expected 3808 bytes, got {plan['estimated_space_savings_bytes']}"
    )


def test_gc_plan_digest(gc_output):
    """Verify the integrity digest of the complete GC plan."""
    expected_digest = "57b2276872219dce7e1eb19af24f3723db72f04d7ae16ba57a91535beaf5d01d"
    assert gc_output["digest"] == expected_digest, (
        f"Plan digest mismatch"
    )
