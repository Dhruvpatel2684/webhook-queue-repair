"""
Tests for the MVCC Garbage Collector.

Validates that the GC pipeline correctly identifies version candidates
for garbage collection based on MVCC visibility rules and active
transaction snapshots.
"""

import json
import os
import subprocess
import pytest


RUNTIME_DIR = os.path.join(
    os.path.dirname(__file__), "..", "environment", "runtime"
)
OUTPUT_FILE = os.path.join(RUNTIME_DIR, "gc_output.json")


@pytest.fixture(scope="session", autouse=True)
def run_gc_pipeline():
    """Run the GC pipeline once before all tests."""
    result = subprocess.run(
        ["python3", "run_gc.py"],
        cwd=RUNTIME_DIR,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"GC pipeline failed: {result.stderr}"
    yield


@pytest.fixture(scope="session")
def gc_output():
    """Load the GC output file."""
    with open(OUTPUT_FILE, "r") as f:
        return json.load(f)


# ============================================================
# Tier 1: Structural tests (pass regardless of bugs)
# ============================================================


class TestStructure:
    """Basic structural validation of GC output."""

    def test_output_file_exists(self, run_gc_pipeline):
        """Verify the GC output file was created."""
        assert os.path.exists(OUTPUT_FILE), (
            "gc_output.json was not created by the pipeline"
        )

    def test_state_has_required_fields(self, gc_output):
        """Verify state section contains all required fields."""
        state = gc_output["state"]
        required = ["total_keys", "total_versions", "active_transactions", "watermark"]
        for field in required:
            assert field in state, f"Missing state field: {field}"

    def test_gc_plan_has_required_fields(self, gc_output):
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

    def test_total_keys_in_store(self, gc_output):
        """Verify the correct number of keys were loaded from version store."""
        assert gc_output["state"]["total_keys"] == 17

    def test_total_versions_loaded(self, gc_output):
        """Verify the correct number of versions were loaded."""
        assert gc_output["state"]["total_versions"] == 85

    def test_active_transactions_loaded(self, gc_output):
        """Verify the correct number of active transactions."""
        assert gc_output["state"]["active_transactions"] == 5

    def test_gc_plan_is_dict(self, gc_output):
        """Verify the gc_plan is a properly structured dict."""
        plan = gc_output["gc_plan"]
        assert isinstance(plan, dict)
        assert isinstance(plan["batches"], list)
        assert isinstance(plan["keys_affected"], list)
        assert isinstance(plan["total_reclaimable_versions"], int)


# ============================================================
# Tier 2: Watermark and snapshot protection tests
# ============================================================


class TestWatermark:
    """Tests for correct watermark computation and snapshot protection."""

    def test_watermark_value(self, gc_output):
        """Verify the GC watermark is computed correctly.

        The watermark must be the minimum snapshot timestamp across all
        transactions that could still be reading data. This includes both
        committed and in-progress (active) transactions.
        """
        assert gc_output["state"]["watermark"] == 150

    def test_active_txn_snapshot_respected(self, gc_output):
        """Verify versions visible to active transactions are not collected.

        Version v-008 (users/1002, commit_ts=175) is visible to the active
        transaction txn-104 (snapshot_ts=180). It must not be collected.
        """
        candidates = gc_output["gc_candidates"]["by_key"]
        if "users/1002" in candidates:
            assert "v-008" not in candidates["users/1002"]["version_ids"], (
                "v-008 (commit_ts=175) should be protected - it is above the "
                "watermark and visible to active transactions"
            )

    def test_version_protected_at_watermark(self, gc_output):
        """Verify versions at exactly the watermark boundary are protected.

        Version v-037 (inventory/7002, commit_ts=150) has commit_ts equal
        to the watermark. It must not be collected because the transaction
        that established the watermark can still see it.
        """
        candidates = gc_output["gc_candidates"]["by_key"]
        if "inventory/7002" in candidates:
            assert "v-037" not in candidates["inventory/7002"]["version_ids"], (
                "v-037 (commit_ts=150) should be protected - versions at "
                "exactly the watermark boundary must not be collected"
            )


# ============================================================
# Tier 3: Version chain and candidate identification tests
# ============================================================


class TestVersionChains:
    """Tests for correct version chain ordering and candidate finding."""

    def test_oldest_version_collected(self, gc_output):
        """Verify the oldest superseded version is identified for collection.

        Version v-001 (users/1001, commit_ts=50) is the oldest version and
        has multiple newer versions. Since 50 < watermark, it should be
        collected. This requires correct chain ordering to not skip it.
        """
        candidates = gc_output["gc_candidates"]["by_key"]
        assert "users/1001" in candidates, (
            "users/1001 should have GC candidates"
        )
        assert "v-001" in candidates["users/1001"]["version_ids"], (
            "v-001 (commit_ts=50) should be collected - it is the oldest "
            "version with newer successors and below the watermark"
        )

    def test_total_candidate_versions(self, gc_output):
        """Verify the total number of GC candidate versions identified.

        With correct watermark (150), correct chain ordering (descending),
        and correct boundary check (strict less-than), exactly 34 versions
        across all keys should be identified for collection.
        """
        assert gc_output["gc_candidates"]["total_candidate_versions"] == 34

    def test_correct_candidates_for_key(self, gc_output):
        """Verify the exact set of candidates for a specific key.

        For users/1001 with versions at timestamps [50, 95, 140, 200, 310]:
        - v-005 (310) is current, never collected
        - v-004 (200) is above watermark (150), protected
        - v-003 (140) is below watermark with newer version, collected
        - v-002 (95) is below watermark with newer version, collected
        - v-001 (50) is below watermark with newer version, collected
        """
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


class TestAggregates:
    """Tests for correct aggregate statistics in the GC plan."""

    def test_space_savings_estimate(self, gc_output):
        """Verify the estimated space savings calculation.

        Space savings should be: total_reclaimable_versions * bytes_per_version
        where bytes_per_version comes from the [gc.measured] config section
        (112 bytes, the actual measured average) and total_reclaimable is
        the sum of all candidate version counts (34).

        Expected: 34 * 112 = 3808 bytes
        """
        plan = gc_output["gc_plan"]
        assert plan["estimated_space_savings_bytes"] == 3808, (
            f"Expected space savings of 3808 bytes (34 versions * 112 bytes), "
            f"got {plan['estimated_space_savings_bytes']}"
        )

    def test_gc_plan_digest(self, gc_output):
        """Verify the integrity digest of the complete GC plan.

        The digest is a SHA-256 hash of the plan's key fields. It validates
        that watermark, reclaimable count, space savings, and affected keys
        are all correct simultaneously.
        """
        expected_digest = "57b2276872219dce7e1eb19af24f3723db72f04d7ae16ba57a91535beaf5d01d"
        assert gc_output["digest"] == expected_digest, (
            f"Plan digest mismatch - one or more plan fields are incorrect"
        )
