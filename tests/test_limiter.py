import json
import pytest
import os

THROTTLE_PLAN_PATH = "/app/runtime/output/throttle_plan.json"
REPORT_PATH = "/app/runtime/output/limiter_report.json"


class TestEasyBasicOutput:
    """Basic structural validation - these pass even with bugs."""

    def test_output_files_exist(self):
        assert os.path.isfile(THROTTLE_PLAN_PATH), "throttle_plan.json not found"
        assert os.path.isfile(REPORT_PATH), "limiter_report.json not found"

    def test_throttle_plan_structure(self):
        with open(THROTTLE_PLAN_PATH) as f:
            data = json.load(f)
        assert isinstance(data, list), "throttle_plan must be a list"
        assert len(data) > 0, "throttle_plan must not be empty"

    def test_decision_fields(self):
        with open(THROTTLE_PLAN_PATH) as f:
            data = json.load(f)
        required = {"client_id", "service_tier", "throttle_score", "time_window", "tokens_used", "decision"}
        for entry in data:
            assert required.issubset(entry.keys()), f"Missing fields in entry: {required - set(entry.keys())}"

    def test_minimum_decisions(self):
        with open(THROTTLE_PLAN_PATH) as f:
            data = json.load(f)
        assert len(data) >= 35, f"Expected at least 35 decisions, got {len(data)}"


class TestMediumCorrectness:
    """Correctness checks requiring 1-2 bug fixes."""

    def test_enterprise_tier_present(self):
        """Enterprise requests must be classified and included."""
        with open(THROTTLE_PLAN_PATH) as f:
            data = json.load(f)
        tiers = {entry["service_tier"] for entry in data}
        assert "enterprise" in tiers, (
            "No enterprise tier decisions found in output. "
            "Verify tier classification handles all configured tiers."
        )

    def test_tokens_within_capacity(self):
        """Token consumption must reflect correct bucket capacity."""
        with open(THROTTLE_PLAN_PATH) as f:
            data = json.load(f)
        for entry in data:
            assert entry["tokens_used"] <= 200, (
                f"tokens_used={entry['tokens_used']} exceeds maximum "
                f"expected capacity bounds for client {entry['client_id']}"
            )

    def test_throttle_rate_range(self):
        """Throttle rate must be within expected bounds for correct capacity."""
        with open(REPORT_PATH) as f:
            report = json.load(f)
        rate = report["throttle_rate"]
        assert 0.25 <= rate <= 0.65, (
            f"throttle_rate={rate:.4f} outside expected range [0.25, 0.65]. "
            f"Verify token bucket parameters are correctly sourced."
        )


class TestHardComprehensive:
    """Comprehensive checks requiring all bugs fixed."""

    def test_sort_ordering(self):
        """Results must be sorted by (throttle_score, service_tier, client_id)."""
        with open(THROTTLE_PLAN_PATH) as f:
            data = json.load(f)
        sort_keys = [(e["throttle_score"], e["service_tier"], e["client_id"]) for e in data]
        assert sort_keys == sorted(sort_keys), (
            "Results must be sorted by (throttle_score, service_tier, client_id)"
        )

    def test_all_requests_classified(self):
        """All 60 input requests must be classified and produce decisions."""
        with open(REPORT_PATH) as f:
            report = json.load(f)
        assert report["requests_classified"] == 60, (
            f"Expected 60 classified requests, got {report['requests_classified']}. "
            f"All input requests across all tiers must be processed."
        )

    def test_complete_accuracy(self):
        """Verify exact throttle statistics match expected values."""
        with open(REPORT_PATH) as f:
            report = json.load(f)
        assert report["total_requests"] == 60, (
            f"total_requests={report['total_requests']}, expected 60"
        )
        assert set(report["tiers_active"]) == {"basic", "standard", "premium", "enterprise"}, (
            f"tiers_active={report['tiers_active']}, expected all four tiers"
        )
        per_tier = report["requests_per_tier"]
        assert per_tier.get("enterprise", 0) == 5, (
            f"enterprise count={per_tier.get('enterprise', 0)}, expected 5"
        )
        # Throttle rate must be in expected bounds when all parameters are correct
        rate = report["throttle_rate"]
        assert 0.20 <= rate <= 0.65, (
            f"throttle_rate={rate:.4f} not in expected range [0.20, 0.65] "
            f"for correctly configured system"
        )
