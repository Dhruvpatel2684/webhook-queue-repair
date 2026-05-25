"""Tests for WAL Replay Recovery Engine output correctness."""

import json
import os

OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "/app/runtime/output")


def load_recovered_state():
    path = os.path.join(OUTPUT_DIR, "recovered_state.json")
    with open(path) as f:
        return json.load(f)


def load_recovery_report():
    path = os.path.join(OUTPUT_DIR, "recovery_report.json")
    with open(path) as f:
        return json.load(f)


# ============================================================
# Tier 1: Structural tests (pass with bugs)
# ============================================================


def test_output_files_exist():
    assert os.path.isfile(os.path.join(OUTPUT_DIR, "recovered_state.json")), \
        "recovered_state.json not found"
    assert os.path.isfile(os.path.join(OUTPUT_DIR, "recovery_report.json")), \
        "recovery_report.json not found"


def test_recovered_state_structure():
    state = load_recovered_state()
    required = ["pages", "committed_txns", "replayed_writes",
                "recovery_lsn_start", "recovery_lsn_end", "state_digest"]
    for field in required:
        assert field in state, f"Missing field: {field}"


def test_recovery_report_structure():
    report = load_recovery_report()
    required = ["total_records_processed", "transactions", "checkpoint_lsn",
                "pages_recovered", "high_conflict_pages"]
    for field in required:
        assert field in report, f"Missing field: {field}"


def test_total_records_count():
    report = load_recovery_report()
    assert report["total_records_processed"] == 60, \
        f"Expected 60 total records, got {report['total_records_processed']}"


def test_pages_are_strings():
    state = load_recovered_state()
    for page_id, value in state["pages"].items():
        assert isinstance(value, str), f"{page_id} value is not a string"


def test_committed_txns_is_list():
    state = load_recovered_state()
    assert isinstance(state["committed_txns"], list), \
        "committed_txns should be a list"
    assert len(state["committed_txns"]) > 0, \
        "committed_txns should not be empty"


def test_recovery_report_has_transactions():
    report = load_recovery_report()
    assert isinstance(report["transactions"], dict), \
        "transactions should be a dict"
    assert len(report["transactions"]) > 0, \
        "transactions should not be empty"


# ============================================================
# Tier 2: Require Bugs 1+4 fixed
# ============================================================


def test_no_in_progress_pages():
    state = load_recovered_state()
    in_progress_pages = ["page-21", "page-22", "page-23", "page-24", "page-25", "page-26"]
    for page_id in in_progress_pages:
        assert page_id not in state["pages"], \
            f"In-progress transaction page '{page_id}' should not appear in recovered state"


def test_page_07_value():
    state = load_recovered_state()
    assert "page-07" in state["pages"], "page-07 missing from recovered pages"
    assert state["pages"]["page-07"] == "final_data_07", \
        f"page-07 should be 'final_data_07', got '{state['pages']['page-07']}'"


def test_recovery_lsn_end():
    state = load_recovered_state()
    assert state["recovery_lsn_end"] == 1000, \
        f"recovery_lsn_end should be 1000, got {state['recovery_lsn_end']}"


# ============================================================
# Tier 3: Require Bugs 2+3+5 fixed
# ============================================================


def test_replayed_writes_count():
    state = load_recovered_state()
    assert state["replayed_writes"] == 31, \
        f"Expected 31 replayed writes, got {state['replayed_writes']}"


def test_page_values_not_stale():
    state = load_recovered_state()
    pages = state["pages"]
    checks = {
        "page-03": "final_data_03",
        "page-06": "final_data_06",
        "page-09": "final_data_09",
    }
    for page_id, expected_val in checks.items():
        assert page_id in pages, f"{page_id} missing from recovered pages"
        assert pages[page_id] == expected_val, \
            f"{page_id} has stale value '{pages[page_id]}', expected '{expected_val}'"


def test_recovery_lsn_start():
    state = load_recovered_state()
    assert state["recovery_lsn_start"] == 501, \
        f"recovery_lsn_start should be 501 (after checkpoint), got {state['recovery_lsn_start']}"


# ============================================================
# Tier 4: Require ALL bugs fixed
# ============================================================


def test_state_digest():
    state = load_recovered_state()
    assert state["state_digest"] == "46107dfbefe5dfa0", \
        f"State digest mismatch: expected '46107dfbefe5dfa0', got '{state['state_digest']}'"


def test_combined_correctness():
    state = load_recovered_state()
    assert state["pages"]["page-07"] == "final_data_07", \
        f"page-07 incorrect: '{state['pages']['page-07']}'"
    assert sorted(state["committed_txns"]) == sorted(["txn-001", "txn-002", "txn-003", "txn-004", "txn-005"]), \
        f"Committed set incorrect: {state['committed_txns']}"
    assert state["replayed_writes"] == 31, \
        f"Replayed writes incorrect: {state['replayed_writes']}"
    assert state["recovery_lsn_end"] == 1000, \
        f"Recovery LSN end should be 1000, got {state['recovery_lsn_end']}"
    in_progress_pages = ["page-21", "page-22", "page-23", "page-24", "page-25", "page-26"]
    for p in in_progress_pages:
        assert p not in state["pages"], \
            f"In-progress page {p} should not be in recovered state"
