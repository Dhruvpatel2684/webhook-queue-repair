"""
Tests for webhook-queue-repair task.
Validates the webhook delivery replayer output files.
"""

import json
import os


RUNTIME_DIR = "/app/runtime"
JSONL_PATH = os.path.join(RUNTIME_DIR, "webhook_status.jsonl")
REPORT_PATH = os.path.join(RUNTIME_DIR, "delivery_report.json")


def load_webhook_status():
    """Load webhook_status.jsonl and return list of webhook records."""
    records = []
    with open(JSONL_PATH, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def load_report():
    """Load delivery_report.json and return dict."""
    with open(REPORT_PATH, "r") as f:
        return json.load(f)


# ============================================================
# TIER 1: Basic structure (pass even with buggy code)
# ============================================================

def test_output_files_exist():
    """Both output files must be created."""
    assert os.path.exists(JSONL_PATH), "webhook_status.jsonl not found"
    assert os.path.exists(REPORT_PATH), "delivery_report.json not found"


def test_correct_webhook_count():
    """Output must contain exactly 8 webhook records."""
    records = load_webhook_status()
    assert len(records) == 8, f"Expected 8 webhooks, got {len(records)}"


def test_webhook_ids_present():
    """All expected webhook IDs must be in output."""
    records = load_webhook_status()
    ids = {r["webhook_id"] for r in records}
    expected = {f"wh-00{i}" for i in range(1, 9)}
    assert ids == expected, f"Missing webhooks: {expected - ids}"


def test_total_webhooks_field():
    """Report must have total_webhooks=8."""
    report = load_report()
    assert report["total_webhooks"] == 8


def test_delivered_count():
    """5 webhooks were successfully delivered."""
    report = load_report()
    assert report["delivered"] == 5, f"Expected 5, got {report['delivered']}"


def test_dead_letter_count():
    """3 webhooks ended up in dead letter queue."""
    report = load_report()
    assert report["dead_lettered"] == 3, f"Expected 3, got {report['dead_lettered']}"


def test_pending_count():
    """No webhooks should be in pending state after full replay."""
    report = load_report()
    assert report["pending"] == 0, f"Expected 0 pending, got {report['pending']}"


# ============================================================
# TIER 2: Attempt counting (requires fixing overcounting bugs)
# ============================================================

def test_total_attempts_count():
    """total_attempts must equal 17 (actual ATTEMPT events in log)."""
    report = load_report()
    assert report["total_attempts"] == 17, (
        f"Expected 17, got {report['total_attempts']}"
    )


def test_webhook_attempt_counts():
    """Each webhook must have the correct number of attempts."""
    records = load_webhook_status()
    expected = {
        "wh-001": 1, "wh-002": 4, "wh-003": 2, "wh-004": 1,
        "wh-005": 3, "wh-006": 2, "wh-007": 1, "wh-008": 3,
    }
    for r in records:
        wh_id = r["webhook_id"]
        assert r["attempts"] == expected[wh_id], (
            f"{wh_id}: expected {expected[wh_id]} attempts, got {r['attempts']}"
        )


# ============================================================
# TIER 3: Derived metrics (requires fixing rate and latency)
# ============================================================

def test_delivery_rate():
    """delivery_rate must be 0.625 (5 delivered / 8 total webhooks)."""
    report = load_report()
    assert report["delivery_rate"] == 0.625, (
        f"Expected 0.625, got {report['delivery_rate']}"
    )


def test_mean_latency():
    """mean_latency_ms must be 1168 (average of delivered webhook durations only)."""
    report = load_report()
    assert report["mean_latency_ms"] == 1168, (
        f"Expected 1168, got {report['mean_latency_ms']}"
    )


# ============================================================
# TIER 4: Fingerprint integrity (requires ALL bugs fixed)
# ============================================================

def test_queue_fingerprint():
    """Queue fingerprint must match expected deterministic value."""
    report = load_report()
    assert report["queue_fingerprint"] == "26b5e8b9efbc94aa", (
        f"Expected '26b5e8b9efbc94aa', got '{report['queue_fingerprint']}'"
    )


def test_webhook_status_sorted():
    """webhook_status.jsonl records must be sorted by webhook_id."""
    records = load_webhook_status()
    ids = [r["webhook_id"] for r in records]
    assert ids == sorted(ids), "Records not sorted by webhook_id"


def test_delivered_webhook_timestamps():
    """Delivered webhooks must have correct delivered_at timestamps."""
    records = load_webhook_status()
    expected_delivered = {
        "wh-001": 1716000005,
        "wh-003": 1716000019,
        "wh-004": 1716000042,
        "wh-006": 1716000113,
        "wh-007": 1716000122,
    }
    for r in records:
        if r["status"] == "delivered":
            assert r["delivered_at"] == expected_delivered[r["webhook_id"]], (
                f"{r['webhook_id']}: wrong delivered_at"
            )
