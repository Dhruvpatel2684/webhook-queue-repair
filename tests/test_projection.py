"""
Tests for the CQRS event projection system.

Verifies correctness of materialized views produced by the projection engine.
Tests are organized by difficulty: easy tests pass even with bugs present,
medium tests require 1-2 fixes, and hard tests require most or all fixes.
"""

import json
import os

import pytest

OUTPUT_DIR = "/app/runtime/output"
PROJECTIONS_FILE = os.path.join(OUTPUT_DIR, "projections.json")
METADATA_FILE = os.path.join(OUTPUT_DIR, "metadata.json")


@pytest.fixture(scope="module")
def projections():
    """Load the projections output file."""
    with open(PROJECTIONS_FILE, "r") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def metadata():
    """Load the metadata output file."""
    with open(METADATA_FILE, "r") as f:
        return json.load(f)


# =============================================================================
# EASY TESTS (4) - Pass even with all bugs present
# =============================================================================


class TestBasicOutput:
    """Basic structural tests that pass regardless of bug presence."""

    def test_output_files_exist(self):
        """Verify that both output files were created successfully."""
        assert os.path.isfile(PROJECTIONS_FILE), (
            f"Projections file not found at {PROJECTIONS_FILE}"
        )
        assert os.path.isfile(METADATA_FILE), (
            f"Metadata file not found at {METADATA_FILE}"
        )

    def test_projection_structure(self, projections):
        """Verify each projection record contains all required fields."""
        required_fields = {
            "view_key", "field", "value", "merge_mode",
            "priority", "source_stream", "source_event_type",
            "last_updated_seq", "update_count"
        }
        for key, record in projections.items():
            missing = required_fields - set(record.keys())
            assert not missing, (
                f"Projection '{key}' missing fields: {missing}"
            )
            assert isinstance(record["value"], (int, float)), (
                f"Projection '{key}' value must be numeric"
            )

    def test_event_count_loaded(self, metadata):
        """Verify that the system loaded a reasonable number of events."""
        assert metadata["total_events_loaded"] >= 60, (
            f"Expected at least 60 events loaded, got {metadata['total_events_loaded']}"
        )

    def test_stream_names_present(self, metadata):
        """Verify all 5 event streams were processed."""
        expected_streams = {"inventory", "orders", "payments", "returns", "shipments"}
        actual_streams = set(metadata["streams_processed"])
        assert expected_streams == actual_streams, (
            f"Expected streams {expected_streams}, got {actual_streams}"
        )


# =============================================================================
# MEDIUM TESTS (4) - Require 1-2 bug fixes to pass
# =============================================================================


class TestDataIntegrity:
    """Tests requiring partial fixes to pass."""

    def test_dedup_preserves_versions(self, metadata):
        """
        Verify that events with different versions are treated as distinct.

        The payment stream contains events with the same stream_id and
        sequence number but different version numbers. These represent
        legitimate re-processed events and must all be preserved by the
        deduplication stage.
        """
        # With Bug B fixed: all 80 events are unique (different versions = different events)
        # With Bug B present: 2 events incorrectly deduped, leaving 78
        assert metadata["events_after_dedup"] == 80, (
            f"Expected 80 events after dedup (no true duplicates exist), "
            f"got {metadata['events_after_dedup']}. Check dedup key composition "
            f"in dedup_engine.py - events with same coordinates but different "
            f"versions should be treated as distinct"
        )

    def test_last_write_not_max(self, projections):
        """
        Verify that the last_write merge mode returns the most recent value,
        not the maximum value seen.

        For last_write fields, the final value should reflect the last event
        processed in sequence order, regardless of whether earlier events
        had higher values.
        """
        # payment_adjusted events (in seq order): seq 6: 210.50, seq 10: 300.00, seq 15: 185.00
        # With Bug C fixed (last_write = new_value), final = 185.00
        # With Bug C present (last_write = max), final = 300.00
        adjustment = projections.get("payment_ledger:last_adjustment", {})
        assert adjustment.get("value") == pytest.approx(185.0, abs=0.01), (
            f"payment_ledger:last_adjustment should be 185.00 (last written value), "
            f"got {adjustment.get('value')}"
        )

    def test_inventory_current_stock(self, projections):
        """
        Verify the current stock level reflects the most recent inventory event,
        not the highest stock level ever recorded.

        The inventory_added events write to current_stock using last_write mode.
        The final value should be from the last inventory_added event processed.
        """
        # inventory_added events by seq: 1:500, 2:350, 5:200, 7:300, 10:150, 13:120, 14:90
        # With Bug C fixed: last value = 90.0
        # With Bug C present: max value = 500.0
        inv_stock = projections.get("inventory_status:current_stock", {})
        assert inv_stock.get("value") == pytest.approx(90.0, abs=0.01), (
            f"inventory_status:current_stock should be 90.0 (last added), "
            f"got {inv_stock.get('value')}"
        )

    def test_shipping_weight_no_duplicates(self, projections):
        """
        Verify shipping total weight is computed without double-counting
        events at window boundaries.

        With correct window boundaries, each delivered shipment event
        contributes exactly once to the total weight.
        """
        # shipment_delivered events: seq 5:2.5, seq 8:5.0, seq 11:8.0, seq 14:3.2
        # Total = 18.7
        # With Bug A: seq 11 counted twice = 26.7
        shipping = projections.get("shipping_overview:total_weight", {})
        assert shipping.get("value") == pytest.approx(18.7, abs=0.01), (
            f"shipping_overview:total_weight should be 18.7, got {shipping.get('value')}"
        )


# =============================================================================
# HARD TESTS (4) - Require 3-5 bug fixes to pass
# =============================================================================


class TestProjectionAccuracy:
    """Tests requiring most or all bug fixes to pass."""

    def test_priority_resolution(self, projections):
        """
        Verify that higher priority projections win in conflict resolution.

        The fulfillment_score:delivery_metric view is targeted by both
        shipment_delivered (priority 40) and return_processed (priority 50).
        Higher priority should win, so the returns data should be used.
        """
        fulfillment = projections.get("fulfillment_score:delivery_metric", {})
        # With Bug E fixed: priority 50 (returns) wins over priority 40 (shipments)
        # return_processed amounts: 50 + 89.99 + 125 + 200 = 464.99
        assert fulfillment.get("source_stream") == "returns", (
            f"fulfillment_score should come from 'returns' (priority 50), "
            f"got '{fulfillment.get('source_stream')}'"
        )
        assert fulfillment.get("priority") == 50, (
            f"fulfillment_score priority should be 50, got {fulfillment.get('priority')}"
        )
        assert fulfillment.get("value") == pytest.approx(464.99, abs=0.01), (
            f"fulfillment_score:delivery_metric should be 464.99, "
            f"got {fulfillment.get('value')}"
        )

    def test_payment_received_total(self, projections):
        """
        Verify that payment received total correctly includes all version
        variants and counts each event exactly once.

        This requires both correct deduplication (preserving different versions)
        and correct window boundaries (no double-counting).
        """
        # payment_received events (all versions):
        # seq 1:150, seq 2:230.50, seq 3:89.99, seq 5v1:312.75, seq 5v2:325.00,
        # seq 7:67.25, seq 9:199.00, seq 11:445.00, seq 13:128.50, seq 14:95.00, seq 16:550.00
        # Total = 2592.99
        received = projections.get("payment_ledger:received_total", {})
        assert received.get("value") == pytest.approx(2592.99, abs=0.01), (
            f"payment_ledger:received_total expected 2592.99, got {received.get('value')}"
        )

    def test_order_completed_total(self, projections):
        """
        Verify that the completed order total is accurate with no
        boundary-related double counting.

        This value is affected by window boundary correctness since
        order_completed events exist at the boundary sequence number.
        """
        # order_completed events: seq 5:175.00, seq 8:275.50, seq 11:104.99,
        # seq 14:362.75, seq 17:97.25, seq 20:219.00
        # Total = 1234.49
        # With Bug A: seq 11 event double-counted = 1339.48
        completed = projections.get("order_summary:completed_total", {})
        assert completed.get("value") == pytest.approx(1234.49, abs=0.01), (
            f"order_summary:completed_total expected 1234.49, got {completed.get('value')}"
        )

    def test_complete_system_integrity(self, metadata, projections):
        """
        Comprehensive verification of the entire output state.
        Only passes when all 5 bugs are fixed correctly.
        """
        # Metadata checks
        assert metadata["total_events_loaded"] == 80
        assert metadata["events_after_dedup"] == 80, (
            "Dedup should preserve all 80 events (reprocessed events with "
            "different versions are distinct)"
        )
        assert metadata["projections_created"] == 13
        assert metadata["windows_processed"] == 2
        assert len(metadata["streams_processed"]) == 5

        # All key projection values must be exact
        expected_values = {
            "order_summary:total_amount": 1807.99,
            "order_summary:completed_total": 1234.49,
            "payment_ledger:received_total": 2592.99,
            "payment_ledger:refund_total": 207.24,
            "payment_ledger:last_adjustment": 185.0,
            "inventory_status:current_stock": 90.0,
            "inventory_status:removed_total": 310.0,
            "inventory_status:adjustment_max": 480.0,
            "shipping_overview:total_weight": 18.7,
            "returns_summary:return_total": 464.99,
            "returns_summary:processed_amount": 464.99,
            "fulfillment_score:delivery_metric": 464.99,
        }

        for key, expected in expected_values.items():
            actual = projections.get(key, {}).get("value")
            assert actual is not None, f"Missing projection: {key}"
            assert actual == pytest.approx(expected, abs=0.01), (
                f"{key}: expected {expected}, got {actual}"
            )

        # Verify fulfillment comes from returns (priority 50 > 40)
        assert projections["fulfillment_score:delivery_metric"]["source_stream"] == "returns"
        assert projections["fulfillment_score:delivery_metric"]["priority"] == 50
